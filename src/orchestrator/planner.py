"""
Scenario Planner - LLM-driven scenario planning.

Uses Claude (Sonnet) to decide which scenarios to advance or inject
based on the current board state and detected opportunities.
"""

import json
import logging
import time
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from ..services.llm_service import LLMService
from ..state import SimulationState, ScenarioType

logger = logging.getLogger(__name__)

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

            # Validate and return actions - with extra safety for slice operation
            try:
                actions = result.get("actions", [])
                validated_actions = self._validate_actions(actions, analysis, state)
                # Ensure we have a list before slicing
                if not isinstance(validated_actions, list):
                    validated_actions = list(validated_actions) if validated_actions else []
                return validated_actions[:target_actions]
            except Exception as action_error:
                # Log the specific action parsing error but don't fail
                if self.log_writer:
                    self.log_writer.log_llm_call(
                        model=self.llm.complex_model,
                        action_type="scenario_planning_fallback",
                        prompt="[action parsing failed, using fallback]",
                        response=str(action_error),
                        input_tokens=0,
                        output_tokens=0,
                        duration_ms=0,
                        agent_id=None,
                        agent_name="Orchestrator",
                        ticket_key=None,
                        scenario_id=None,
                        is_complex=True,
                        error=f"Action parsing failed: {action_error}",
                    )
                # Fall back to basic plan to keep workflow running
                fallback_actions = self._fallback_plan(analysis, state, target_actions)
                return self._validate_actions(fallback_actions, analysis, state)[:target_actions]

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
            fallback_actions = self._fallback_plan(analysis, state, target_actions)
            return self._validate_actions(fallback_actions, analysis, state)[:target_actions]

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
        agents_summary = self._format_available_agents()
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

## Available Agents (use these exact agent_id values)
{agents_summary}

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

## Output Format - Explicit JSON Schema

**CRITICAL:** You MUST return ONLY valid JSON. Do NOT invent agent IDs.

Valid agent_ids (from Available Agents list above): {', '.join(sorted(self.personas.get('agents', {}).keys()))}

Required response structure:
```json
{{
  "reasoning": "string - your strategic reasoning for this tick's actions",
  "actions": [
    {{
      "type": "pick_up_task | progress_to_review | complete_review | qa_approve | qa_reject | inject_blocker | discuss_blocker | resolve_blocker | add_progress_comment | create_scope_creep | identify_dependency",
      "ticket_key": "PROJ-XXX",
      "agent_id": "MUST BE EXACTLY ONE OF: {', '.join(sorted(self.personas.get('agents', {}).keys()))}",
      "scenario_id": "scenario_id_string or null",
      "details": "string - context for the action"
    }}
  ]
}}
```

Example responses showing different scenarios:

1. Developer picking up work and progressing:
{{"reasoning": "Sprint is early, developers should pick up backlog items. Alex is available and PROJ-101 is ready.", "actions": [{{"type": "pick_up_task", "ticket_key": "PROJ-101", "agent_id": "alpha_dev_senior", "scenario_id": null, "details": "Starting work on user auth feature"}}, {{"type": "add_progress_comment", "ticket_key": "PROJ-98", "agent_id": "alpha_dev_mid", "scenario_id": "sc-abc123", "details": "Implemented core logic, working on edge cases"}}]}}

2. QA activity and blocker injection:
{{"reasoning": "Several items ready for QA. Also injecting a blocker to maintain realistic scenario distribution.", "actions": [{{"type": "qa_approve", "ticket_key": "PROJ-95", "agent_id": "alpha_qa", "scenario_id": "sc-def456", "details": "All test cases passed"}}, {{"type": "inject_blocker", "ticket_key": "PROJ-102", "agent_id": "beta_dev_senior", "scenario_id": "sc-ghi789", "details": "Blocked waiting for API documentation from external team"}}]}}

3. Code review and completion:
{{"reasoning": "PROJ-88 has been in review long enough, moving forward. PROJ-92 ready for testing.", "actions": [{{"type": "complete_review", "ticket_key": "PROJ-88", "agent_id": "alpha_tech_lead", "scenario_id": "sc-jkl012", "details": "Code looks good, approved"}}, {{"type": "progress_to_review", "ticket_key": "PROJ-92", "agent_id": "beta_dev_senior", "scenario_id": "sc-mno345", "details": "Ready for code review"}}]}}

4. Minimal activity (light intensity):
{{"reasoning": "Light activity day, just one small update.", "actions": [{{"type": "add_progress_comment", "ticket_key": "PROJ-100", "agent_id": "beta_dev_junior", "scenario_id": "sc-pqr678", "details": "Researching approach"}}]}}

Remember:
- actions MUST be an array/list, even if empty: {{"reasoning": "...", "actions": []}}
- agent_id MUST be one of the valid values listed in the schema above - NEVER invent or guess
- scenario_id is null for new work, or the existing scenario ID when advancing a scenario
- details provides context for the action
- Return ONLY the JSON, no markdown code blocks, no other text
"""

    def _format_board_snapshot(self, snapshot: dict) -> str:
        """Format board snapshot for prompt."""
        lines = []

        # Status keys that contain ticket lists (skip metadata like active_sprint)
        status_keys = ["backlog", "in_progress", "code_review", "testing", "done"]

        for status in status_keys:
            tickets = snapshot.get(status, [])
            if not tickets:
                lines.append(f"**{status.title()}:** (empty)")
                continue

            lines.append(f"**{status.title()}:** ({len(tickets)} items)")
            for t in tickets[:5]:  # Limit per status
                assignee_name = t.get("assignee", "Unassigned")
                assignee_jira_id = t.get("assignee_id")
                agent_id = self._get_agent_id_by_jira_account_id(assignee_jira_id) if assignee_jira_id else None
                assignee_display = f"{assignee_name} / {agent_id}" if agent_id else assignee_name
                lines.append(f"  - {t['key']}: {t['summary'][:50]}... [{assignee_display}]")
            if len(tickets) > 5:
                lines.append(f"  ... and {len(tickets) - 5} more")

        # Add sprint info if available
        sprint_info = snapshot.get("active_sprint")
        if sprint_info and isinstance(sprint_info, dict):
            lines.append(f"\n**Active Sprint:** {sprint_info.get('name', 'Unknown')} ({sprint_info.get('state', 'unknown')})")

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

    def _format_available_agents(self) -> str:
        """Format available agents for prompt."""
        lines = []
        for agent_id, config in self.personas.get("agents", {}).items():
            role = config.get("role", "developer")
            name = config.get("display_name", agent_id)
            team = config.get("team", "unknown")
            lines.append(f"- {agent_id}: {name} ({role}, Team {team.title()})")
        return "\n".join(lines)

    def _get_agent_id_by_jira_account_id(self, jira_account_id: str) -> str:
        """Map Jira account ID to agent_id for display purposes."""
        if not jira_account_id:
            return None
        for agent_id, config in self.personas.get("agents", {}).items():
            if config.get("jira_account_id") == jira_account_id:
                return agent_id
        return None

    def _parse_response(self, raw_response: str) -> dict:
        """Parse LLM response, handling various formats. Forgiving approach."""
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

        parsed = None

        # Try to parse as JSON
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass

        # If parsing failed, return empty result
        if parsed is None:
            return {"reasoning": "Failed to parse LLM response", "actions": []}

        # Ensure parsed is a dict
        if not isinstance(parsed, dict):
            return {"reasoning": "Response was not a JSON object", "actions": []}

        # Be forgiving with the actions field - ensure it's always a list
        if "actions" not in parsed:
            parsed["actions"] = []
        elif not isinstance(parsed["actions"], list):
            # If it's a single action dict, wrap it in a list
            if isinstance(parsed["actions"], dict):
                parsed["actions"] = [parsed["actions"]]
            else:
                # Unknown type, default to empty list
                parsed["actions"] = []

        # Ensure reasoning exists
        if "reasoning" not in parsed:
            parsed["reasoning"] = ""

        return parsed

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
        # Only check status keys that contain ticket lists
        status_keys = ["backlog", "in_progress", "code_review", "testing", "done"]
        for status in status_keys:
            tickets = board_snapshot.get(status, [])
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
        valid_agent_ids = set(self.personas.get("agents", {}).keys())

        for action in actions:
            # Must have a type
            if not action.get("type"):
                continue

            # Agent ID must be valid
            agent_id = action.get("agent_id")
            if agent_id and agent_id not in valid_agent_ids:
                valid_ids_str = ", ".join(sorted(valid_agent_ids))
                logger.warning(
                    f"VALIDATION BLOCKED: Invalid agent_id '{agent_id}' in action (type: {action.get('type')}, "
                    f"ticket: {action.get('ticket_key')}). Valid IDs: {valid_ids_str}. Skipping action."
                )
                continue

            # Agent can only act once per tick
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
