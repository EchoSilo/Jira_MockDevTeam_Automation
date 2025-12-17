"""
Scenario Planner - LLM-driven scenario planning.

Uses Claude (Sonnet) to decide which scenarios to advance or inject
based on the current board state and detected opportunities.
"""

import json
import time
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from ..services.llm_service import LLMService
from ..state import SimulationState, ScenarioType

if TYPE_CHECKING:
    from ..logging import AsyncLogWriter


class ScenarioPlanner:
    """
    LLM-driven scenario planning.

    Takes analysis results and decides what actions to execute this tick.
    Uses Sonnet for intelligent, contextual decision making.
    """

    def __init__(self, llm_service: LLMService, settings: dict, personas: dict = None):
        self.llm = llm_service
        self.settings = settings
        self.personas = personas or {}

        # Optional log writer - injected by orchestrator
        self.log_writer: "AsyncLogWriter | None" = None

        # Planning configuration
        self.max_actions_per_tick = settings.get("scenarios", {}).get(
            "limits", {}
        ).get("max_actions_per_tick", 5)

        # Issue type permissions by role
        self.issue_type_permissions = settings.get("issue_type_permissions", {
            "pm": {"can_act_on": ["Epic", "Story", "Bug", "Task"]},
            "developer": {"can_act_on": ["Story", "Bug", "Task"]},
            "qa": {"can_act_on": ["Story", "Bug", "Task"]},
            "tech_lead": {"can_act_on": ["Story", "Bug", "Task"]},
        })

        # Store last reasoning for debugging
        self.last_reasoning = ""
        self.last_raw_response = ""

    def plan_tick(
        self,
        analysis: dict,
        state: SimulationState,
        intensity: str = "normal",
    ) -> list[dict]:
        """
        Plan actions for this simulation tick.

        Args:
            analysis: Analysis dict from ScenarioAnalyzer
            state: Current simulation state
            intensity: Tick intensity ("light", "normal", "busy")

        Returns:
            List of action dicts to execute
        """
        # Adjust action count by intensity
        intensity_multipliers = {
            "light": 0.5,
            "normal": 1.0,
            "busy": 1.5,
        }
        multiplier = intensity_multipliers.get(intensity, 1.0)
        target_actions = max(2, int(self.max_actions_per_tick * multiplier))

        # Build the planning prompt
        prompt = self._build_planning_prompt(analysis, state, target_actions)

        try:
            # Call LLM with timing
            start_time = time.time()
            model = self.llm.complex_model  # Use Sonnet for planning

            response = self.llm.client.messages.create(
                model=model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )

            duration_ms = int((time.time() - start_time) * 1000)
            raw_response = response.content[0].text.strip()
            self.last_raw_response = raw_response

            # Log the LLM call
            if self.log_writer:
                self.log_writer.log_llm_call(
                    model=model,
                    action_type="scenario_planning",
                    prompt=prompt,
                    response=raw_response,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    duration_ms=duration_ms,
                    agent_id=None,
                    agent_name="Orchestrator",
                    ticket_key=None,
                    scenario_id=None,
                    is_complex=True,
                )

            # Parse the JSON response
            result = self._parse_response(raw_response)

            # Store reasoning
            self.last_reasoning = result.get("reasoning", "")

            # Validate and return actions
            actions = result.get("actions", [])
            validated_actions = self._validate_actions(actions, analysis, state)

            return validated_actions[:target_actions]

        except Exception as e:
            # Log failed LLM call
            if self.log_writer:
                duration_ms = int((time.time() - start_time) * 1000) if 'start_time' in dir() else 0
                self.log_writer.log_llm_call(
                    model=self.llm.complex_model,
                    action_type="scenario_planning",
                    prompt=prompt,
                    response="",
                    input_tokens=0,
                    output_tokens=0,
                    duration_ms=duration_ms,
                    agent_id=None,
                    agent_name="Orchestrator",
                    ticket_key=None,
                    scenario_id=None,
                    is_complex=True,
                    error=str(e),
                )
            # On error, fall back to basic actions
            return self._fallback_plan(analysis, state, target_actions)

    def _build_planning_prompt(
        self,
        analysis: dict,
        state: SimulationState,
        target_actions: int,
    ) -> str:
        """Build the LLM prompt for scenario planning."""

        board_summary = self._format_board_snapshot(analysis.get("board_snapshot", {}))
        scenarios_summary = self._format_active_scenarios(state)
        opportunities_summary = self._format_opportunities(analysis.get("opportunities", []))
        recent_summary = self._format_recent_actions(state.recent_actions[-10:])
        metrics = analysis.get("metrics", {})

        return f"""You are the Scenario Orchestrator for a Jira team simulation.
Your job is to plan realistic team activity that creates meaningful patterns in the data.

## Current Board State
{board_summary}

## Active Scenarios ({len(state.active_scenarios)} total)
{scenarios_summary}

## Detected Opportunities
{opportunities_summary}

## Recent Actions (last 10)
{recent_summary}

## Current Metrics
- Sprint Day: {metrics.get('sprint_day', 1)} / 14
- Scenarios ready to advance: {metrics.get('scenarios_ready_to_advance', 0)}
- Backlog size: {metrics.get('backlog_size', 0)}
- In Progress: {metrics.get('in_progress_count', 0)}
- In Review: {metrics.get('in_review_count', 0)}
- In Testing: {metrics.get('in_testing_count', 0)}
- Scenario Distribution: {json.dumps(metrics.get('scenario_distribution', {}))}

## Target Scenario Distribution
- Normal flow: 60%
- Blockers: 15%
- Rework (QA rejection): 15%
- Scope creep: 5%
- Dependencies: 5%

## Your Task
Plan {target_actions} actions for this tick. Consider:

1. **Priority order:**
   - Advance scenarios that are ready (high priority opportunities)
   - Inject new scenarios to maintain balance (medium priority)
   - Pick up backlog items if developers are available

2. **Realism:**
   - Don't rush tickets through too fast (realistic cycle times)
   - Vary the types of actions (not all the same)
   - Consider the time of sprint (early = more pickup, late = more completion)

3. **Avoid:**
   - Same agent acting multiple times
   - Repetitive actions (check recent actions)
   - Unrealistic patterns (5 blockers at once, etc.)

## Cycle Time Guidelines
- Bugs: 1-3 days total
- Stories: 3-7 days total
- Complex features: 7-14 days total

## Output Format
Return ONLY valid JSON in this format:
```json
{{
  "reasoning": "Brief explanation of your planning logic (2-3 sentences)",
  "actions": [
    {{
      "type": "progress_to_review|complete_review|qa_approve|qa_reject|inject_blocker|discuss_blocker|resolve_blocker|pick_up_task|add_progress_comment|create_scope_creep|identify_dependency",
      "scenario_id": "existing scenario ID or null for new scenarios",
      "ticket_key": "PROJ-123",
      "agent_id": "alpha_dev_senior",
      "details": "Any specific context for this action"
    }}
  ]
}}
```

Important:
- Return ONLY the JSON, no markdown code blocks, no other text
- Each action must have type, ticket_key (if applicable), and agent_id
- Use scenario_id when advancing existing scenarios
- Details field is for context like blocker reasons, rejection reasons, etc.
"""

    def _format_board_snapshot(self, snapshot: dict) -> str:
        """Format board snapshot for prompt."""
        lines = []

        for status, tickets in snapshot.items():
            if not tickets:
                lines.append(f"**{status.title()}:** (empty)")
                continue

            lines.append(f"**{status.title()}:** ({len(tickets)} items)")
            for t in tickets[:5]:  # Limit per status
                assignee = t.get("assignee", "Unassigned")
                lines.append(f"  - {t['key']}: {t['summary'][:50]}... [{assignee}]")
            if len(tickets) > 5:
                lines.append(f"  ... and {len(tickets) - 5} more")

        return "\n".join(lines)

    def _format_active_scenarios(self, state: SimulationState) -> str:
        """Format active scenarios for prompt."""
        if not state.active_scenarios:
            return "No active scenarios"

        lines = []
        for scenario in list(state.active_scenarios.values())[:15]:  # Limit to 15
            ready = "✓ READY" if scenario.is_phase_ready_to_advance() else ""
            lines.append(
                f"- {scenario.ticket_key} ({scenario.scenario_type.value}): "
                f"{scenario.current_phase.value} "
                f"[{scenario.get_days_in_current_phase():.1f}d in phase] "
                f"Agent: {scenario.assigned_agent or 'unassigned'} {ready}"
            )

        if len(state.active_scenarios) > 15:
            lines.append(f"... and {len(state.active_scenarios) - 15} more scenarios")

        return "\n".join(lines)

    def _format_opportunities(self, opportunities: list) -> str:
        """Format opportunities for prompt."""
        if not opportunities:
            return "No specific opportunities detected"

        # Group by priority
        high = [o for o in opportunities if o.get("priority") == "high"]
        medium = [o for o in opportunities if o.get("priority") == "medium"]
        low = [o for o in opportunities if o.get("priority") == "low"]

        lines = []

        if high:
            lines.append("**High Priority:**")
            for o in high[:5]:
                lines.append(f"  - [{o['type']}] {o['description']}")

        if medium:
            lines.append("**Medium Priority:**")
            for o in medium[:5]:
                lines.append(f"  - [{o['type']}] {o['description']}")

        if low:
            lines.append("**Low Priority:**")
            for o in low[:3]:
                lines.append(f"  - [{o['type']}] {o['description']}")

        return "\n".join(lines)

    def _format_recent_actions(self, actions: list) -> str:
        """Format recent actions for prompt."""
        if not actions:
            return "No recent actions"

        lines = []
        for a in actions:
            lines.append(
                f"- {a.agent_name}: {a.action_type} on {a.ticket_key or 'N/A'}"
            )

        return "\n".join(lines)

    def _parse_response(self, raw_response: str) -> dict:
        """Parse LLM response, handling various formats."""
        # Try to find JSON in the response
        text = raw_response.strip()

        # Remove markdown code blocks if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last line if they're code block markers
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        # Try to parse as JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass

        # Return empty result on parse failure
        return {"reasoning": "Failed to parse LLM response", "actions": []}

    def _get_agent_role(self, agent_id: str) -> str:
        """Get the role for an agent."""
        agent_config = self.personas.get("agents", {}).get(agent_id, {})
        return agent_config.get("role", "developer")

    def _can_agent_act_on_issue_type(self, agent_id: str, issue_type: str) -> bool:
        """Check if an agent can act on a specific issue type based on role."""
        role = self._get_agent_role(agent_id)
        role_permissions = self.issue_type_permissions.get(role, {})
        allowed_types = role_permissions.get("can_act_on", ["Story", "Bug", "Task"])
        return issue_type in allowed_types

    def _get_ticket_type_from_analysis(
        self, ticket_key: str, analysis: dict
    ) -> str | None:
        """Look up issue type from board snapshot."""
        board_snapshot = analysis.get("board_snapshot", {})
        for status, tickets in board_snapshot.items():
            for ticket in tickets:
                if ticket.get("key") == ticket_key:
                    return ticket.get("type")
        return None

    def _validate_actions(
        self,
        actions: list,
        analysis: dict,
        state: SimulationState,
    ) -> list[dict]:
        """Validate and clean up planned actions."""
        validated = []
        used_agents = set()

        for action in actions:
            # Must have a type
            if not action.get("type"):
                continue

            # Agent can only act once per tick
            agent_id = action.get("agent_id")
            if agent_id and agent_id in used_agents:
                continue

            # Validate issue type permissions
            ticket_key = action.get("ticket_key")
            if agent_id and ticket_key:
                issue_type = self._get_ticket_type_from_analysis(ticket_key, analysis)
                if issue_type and not self._can_agent_act_on_issue_type(
                    agent_id, issue_type
                ):
                    # Skip action - agent role cannot act on this issue type
                    continue

            # Validate ticket exists in scenario if scenario_id provided
            scenario_id = action.get("scenario_id")
            if scenario_id and scenario_id not in state.active_scenarios:
                # Clear invalid scenario_id
                action["scenario_id"] = None

            validated.append(action)

            if agent_id:
                used_agents.add(agent_id)

        return validated

    def _fallback_plan(
        self,
        analysis: dict,
        state: SimulationState,
        target_actions: int,
    ) -> list[dict]:
        """Create a basic fallback plan when LLM fails."""
        actions = []
        opportunities = analysis.get("opportunities", [])

        # Sort by priority
        high_priority = [o for o in opportunities if o.get("priority") == "high"]

        # Take high priority opportunities
        for opp in high_priority[:target_actions]:
            action = {
                "type": opp.get("suggested_action", opp.get("type", "unknown")),
                "scenario_id": opp.get("scenario_id"),
                "ticket_key": opp.get("ticket_key"),
                "agent_id": opp.get("agent_id"),
                "details": opp.get("description", ""),
            }
            actions.append(action)

        return actions
