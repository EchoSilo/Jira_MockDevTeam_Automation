"""
Scenario Planner - LLM-driven scenario planning.

Uses Claude (Sonnet) to decide which scenarios to advance or inject
based on the current board state and detected opportunities.

Now also supports sprint-level scenarios via ScriptExecutor.
"""

import json
import logging
import time
from datetime import datetime
from typing import Optional, TYPE_CHECKING

import litellm

from ..services.llm_service import LLMService
from ..state import SimulationState, ScenarioType, PlannedAction, ReleaseDirective
from ..scenarios import ScriptExecutor, SprintScenario

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

        # Map action types to their target Jira status for transition validation
        self.action_target_status = {
            "pick_up_task": "In Progress",
            "progress_to_review": "Code Review",
            "complete_review": "Testing",
            "qa_approve": "Done",
            "qa_reject": "In Progress",
            "resolve_blocker": "In Progress",
            "inject_blocker": "Blocked",
        }

    def plan_tick(
        self,
        analysis: dict,
        state: SimulationState,
        intensity: str = "normal",
    ) -> list[dict]:
        """
        Plan actions for this simulation tick.

        Planning is now script-aware:
        1. First, get actions from scenario scripts that are ready
        2. Then, use LLM to fill remaining slots with new work

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

        # Phase 0: Convert Release Manager directives to PM actions (highest priority)
        # Use ALL pending directives from state, not just new ones from this tick
        release_directives = state.release_state.get_pending_directives()
        directive_actions = self._convert_directives_to_actions(release_directives, state)

        # Track agents used by directive actions
        directive_agent_ids = {a.get("agent_id") for a in directive_actions if a.get("agent_id")}

        # If directives filled all slots, return those
        if len(directive_actions) >= target_actions:
            logger.info(f"Release directives filled all {len(directive_actions)} action slots")
            return directive_actions[:target_actions]

        # Phase 0.5: Force-execute CRITICAL priority opportunities
        # These MUST be done - don't leave to LLM discretion
        critical_actions = []
        critical_opps = [
            o for o in analysis.get("opportunities", [])
            if o.get("priority") == "critical"
        ]
        for opp in critical_opps:
            agent_id = opp.get("pm_id") or opp.get("agent_id")
            if agent_id and agent_id not in directive_agent_ids:
                critical_actions.append({
                    "type": opp.get("type"),
                    "pm_id": opp.get("pm_id"),
                    "agent_id": agent_id,
                    "sprint_id": opp.get("sprint_id"),
                    "sprint_name": opp.get("sprint_name"),
                    "scenario_reason": opp.get("scenario_reason"),
                    "ticket_key": opp.get("ticket_key"),
                    "details": opp.get("description"),
                })
                directive_agent_ids.add(agent_id)
                logger.info(f"Force-adding critical action: {opp.get('type')}")

        # Combine with directive actions
        directive_actions = directive_actions + critical_actions

        # If directives + critical filled all slots, return those
        if len(directive_actions) >= target_actions:
            logger.info(f"Directives + critical actions filled all slots")
            return self._validate_actions(
                directive_actions, analysis, state
            )[:target_actions]

        # Phase 1: Get script-based actions (exclude agents already used by directives)
        script_actions = self._get_script_based_actions(state)
        # Filter out script actions that would use directive agents
        script_actions = [a for a in script_actions if a.get("agent_id") not in directive_agent_ids]

        # Track agents used by script actions
        script_agent_ids = {a.get("agent_id") for a in script_actions if a.get("agent_id")}

        # Combine directive and script agent exclusions
        all_excluded_agents = directive_agent_ids | script_agent_ids

        # Calculate slots used by directives and scripts
        pre_planned_actions = directive_actions + script_actions

        # If directives + scripts filled all slots, return those
        if len(pre_planned_actions) >= target_actions:
            logger.info(f"Directives ({len(directive_actions)}) + scripts ({len(script_actions)}) filled all action slots")
            return self._validate_actions(pre_planned_actions, analysis, state)[:target_actions]

        # Phase 2: Use LLM for remaining slots
        remaining_slots = target_actions - len(pre_planned_actions)

        # Build the planning prompt (exclude agents used by directives and scripts)
        prompt = self._build_planning_prompt(
            analysis, state, remaining_slots, all_excluded_agents
        )

        try:
            # Call LLM with timing
            start_time = time.time()
            model = self.llm.complex_model  # Use Sonnet for planning

            # Prepare completion arguments
            thinking_enabled = self.settings.get("llm", {}).get("orchestrator_thinking")
            completion_kwargs = {
                "model": model,
                # When thinking is enabled, max_tokens includes BOTH thinking AND output
                # We need 16000 for thinking budget + ~2000 for the actual JSON response
                "max_tokens": 20000 if thinking_enabled else 2000,
                "messages": [{"role": "user", "content": prompt}],
            }

            # Add thinking parameter if enabled
            if thinking_enabled:
                completion_kwargs["thinking"] = {"type": "enabled", "budget_tokens": 16000}

            response = litellm.completion(**completion_kwargs)

            duration_ms = int((time.time() - start_time) * 1000)

            raw_response = response.choices[0].message.content.strip()
            self.last_raw_response = raw_response

            # Log the LLM call
            if self.log_writer:
                self.log_writer.log_llm_call(
                    model=model,
                    action_type="scenario_planning",
                    prompt=prompt,
                    response=raw_response,
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=response.usage.completion_tokens,
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
                llm_actions = result.get("actions", [])
                validated_llm_actions = self._validate_actions(llm_actions, analysis, state)
                # Ensure we have a list before slicing
                if not isinstance(validated_llm_actions, list):
                    validated_llm_actions = list(validated_llm_actions) if validated_llm_actions else []

                # Combine: directive actions (highest priority) + script actions + LLM actions
                all_actions = directive_actions + script_actions + validated_llm_actions[:remaining_slots]
                return all_actions[:target_actions]
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
                fallback_actions = self._fallback_plan(analysis, state, remaining_slots)
                validated_fallback = self._validate_actions(fallback_actions, analysis, state)
                # Combine: directive actions + script actions + fallback
                all_actions = directive_actions + script_actions + validated_fallback[:remaining_slots]
                return all_actions[:target_actions]

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
            fallback_actions = self._fallback_plan(analysis, state, remaining_slots)
            validated_fallback = self._validate_actions(fallback_actions, analysis, state)
            # Combine: directive actions + script actions + fallback
            all_actions = directive_actions + script_actions + validated_fallback[:remaining_slots]
            return all_actions[:target_actions]

    def _build_planning_prompt(
        self,
        analysis: dict,
        state: SimulationState,
        target_actions: int,
        excluded_agent_ids: set = None,
    ) -> str:
        """Build the LLM prompt for scenario planning."""
        excluded_agent_ids = excluded_agent_ids or set()

        board_snapshot = analysis.get("board_snapshot", {})
        board_summary = self._format_board_snapshot(board_snapshot)
        workflow_context = self._format_workflow_context(board_snapshot)
        scenarios_summary = self._format_active_scenarios(state)
        opportunities_summary = self._format_opportunities(analysis.get("opportunities", []))
        recent_summary = self._format_recent_actions(state.recent_actions[-10:])
        agents_summary = self._format_available_agents(state)
        fairness_guidance = self._format_fairness_guidance(state)
        metrics = analysis.get("metrics", {})

        # Calculate advancement requirements
        advancement_summary = self._get_advancement_summary(state, analysis)
        ready_count = advancement_summary["ready_count"]
        min_advancements = min(ready_count, max(1, int(target_actions * 0.6))) if ready_count > 0 else 0

        # Build mandatory requirements section if there are ready scenarios
        mandatory_section = ""
        if ready_count > 0:
            mandatory_section = f"""
## MANDATORY REQUIREMENTS (YOU MUST FOLLOW THESE)

There are {ready_count} scenarios OVERDUE and past their target completion time.

**These tickets MUST be advanced THIS tick:**
{self._format_required_advancements(advancement_summary["ready_scenarios"])}

**BINDING RULES:**
1. At least {min_advancements} of your {target_actions} actions MUST be advancement actions
2. Advancement actions include: complete_review, qa_approve, verify_fix, progress_to_review
3. DO NOT plan "pick_up_task" when the above items are waiting for review or QA
4. If you choose "pick_up_task" over advancing overdue items, your plan is INVALID

"""

        # Build warning if items are overdue
        overdue_warning = ""
        if ready_count > 0:
            overdue_warning = f"**WARNING:** {ready_count} items are OVERDUE and MUST be prioritized over new work!\n\n"

        return f"""You are the Scenario Orchestrator for a Jira team simulation.
Your job is to plan realistic team activity that creates meaningful patterns in the data.

## Current Board State
{board_summary}

{workflow_context}

## Active Scenarios ({len(state.active_scenarios)} total)
{scenarios_summary}

## Detected Opportunities
{opportunities_summary}

## Recent Actions (last 10)
{recent_summary}

## Available Agents (use these exact agent_id values)
{agents_summary}
{f"NOTE: These agents are already busy with script-based work and CANNOT be used: {', '.join(sorted(excluded_agent_ids))}" if excluded_agent_ids else ""}

## Workload Fairness (IMPORTANT)
{fairness_guidance}

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
{mandatory_section}
## Your Task
Plan {target_actions} actions for this tick.

{overdue_warning}**Action Selection Priority (STRICTLY FOLLOW THIS ORDER):**
1. **FIRST**: {"Advance the " + str(ready_count) + " overdue scenarios listed above" if ready_count > 0 else "Advance scenarios that are ready (high priority)"}
2. **SECOND**: Inject new scenarios to maintain balance (medium priority)
3. **LAST**: Pick up backlog items ONLY if no items need advancement

**Realism Considerations:**
- Don't rush tickets through too fast (respect cycle times)
- Vary the types of actions (not all the same)
- Consider the time of sprint (early = more pickup, late = more completion)

**Avoid:**
- Same agent acting multiple times
- Repetitive actions (check recent actions)
- Unrealistic patterns (5 blockers at once, etc.)
- {"Picking up new work when " + str(ready_count) + " items are waiting for advancement!" if ready_count > 0 else ""}

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

        # Group by priority (include critical!)
        critical = [o for o in opportunities if o.get("priority") == "critical"]
        high = [o for o in opportunities if o.get("priority") == "high"]
        medium = [o for o in opportunities if o.get("priority") == "medium"]
        low = [o for o in opportunities if o.get("priority") == "low"]

        lines = []

        if critical:
            lines.append("**CRITICAL - MUST DO FIRST:**")
            for o in critical:
                lines.append(f"  - [{o['type']}] {o['description']}")
            lines.append("")

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

    def _format_available_agents(self, state: SimulationState = None) -> str:
        """Format available agents with workload information for prompt."""
        lines = []

        # Get workload stats if state available
        workload_stats = {}
        if state:
            workload_stats = state.get_developer_workload_stats(self.personas)

        for agent_id, config in self.personas.get("agents", {}).items():
            role = config.get("role", "developer")
            name = config.get("display_name", agent_id)
            team = config.get("team") or "unknown"  # Handle null team values

            # Base info
            line = f"- {agent_id}: {name} ({role}, Team {team.title()})"

            # Add workload info for developers
            if role == "developer" and agent_id in workload_stats:
                stats = workload_stats[agent_id]
                workload = stats["current_workload"]
                sprint_assigns = stats["sprint_assignments"]
                seniority = stats["seniority"]

                # Add workload indicator
                if sprint_assigns == 0:
                    workload_indicator = "** NO ASSIGNMENTS THIS SPRINT **"
                elif workload >= 4:
                    workload_indicator = f"[{workload} tickets - BUSY]"
                elif workload == 0:
                    workload_indicator = "[Available]"
                else:
                    workload_indicator = f"[{workload} tickets]"

                line += f" - {seniority} - Sprint: {sprint_assigns} assigned {workload_indicator}"

            lines.append(line)

        return "\n".join(lines)

    def _format_fairness_guidance(self, state: SimulationState) -> str:
        """Format workload fairness guidance for the prompt."""
        workload_stats = state.get_developer_workload_stats(self.personas)

        if not workload_stats:
            return ""

        lines = []

        # Identify developers needing work
        zero_assignments = [
            f"{s['display_name']} ({agent_id})"
            for agent_id, s in workload_stats.items()
            if s["sprint_assignments"] == 0
        ]

        underloaded = [
            f"{s['display_name']} ({agent_id}) - {s['sprint_assignments']} assignments"
            for agent_id, s in workload_stats.items()
            if 0 < s["sprint_assignments"] <= 2 and s["current_workload"] < 3
        ]

        if zero_assignments:
            lines.append("**PRIORITY - These developers have ZERO assignments this sprint:**")
            for dev in zero_assignments:
                lines.append(f"  - {dev}")
            lines.append("")
            lines.append("When selecting agents for 'pick_up_task', STRONGLY PREFER these developers.")
            lines.append("")

        if underloaded:
            lines.append("**Underloaded developers (prefer for new work):**")
            for dev in underloaded:
                lines.append(f"  - {dev}")
            lines.append("")

        # Add guidance
        lines.append("**Fairness Rules:**")
        lines.append("1. Every developer should get at least 1 assignment per sprint")
        lines.append("2. When picking up tasks, prefer developers with fewer sprint assignments")
        lines.append("3. Don't completely block high-performers - they can still be selected")
        lines.append("4. Consider current workload (busy developers may not need more work)")

        return "\n".join(lines)

    def _format_workflow_context(self, board_snapshot: dict) -> str:
        """Format available transitions for planner to ensure valid action selection."""
        lines = ["## Available Jira Transitions (MUST RESPECT THESE)"]
        lines.append("")
        lines.append("Each ticket can only transition to specific statuses based on its current state.")
        lines.append("Actions will FAIL if the target transition is not available.")
        lines.append("")

        # Track unique transition patterns to avoid redundancy
        status_transitions = {}

        for category in ["backlog", "in_progress", "code_review", "testing"]:
            for ticket in board_snapshot.get(category, []):
                transitions = ticket.get("available_transitions", [])
                if transitions:
                    # Build list of target statuses
                    targets = [t.get("to", t.get("name", "")) for t in transitions]
                    targets_str = ", ".join(targets) if targets else "none"

                    # Track by current status for summary
                    current_status = ticket.get("status", "Unknown")
                    if current_status not in status_transitions:
                        status_transitions[current_status] = set()
                    for t in targets:
                        status_transitions[current_status].add(t)

                    lines.append(f"- {ticket['key']} ({current_status}): can go to [{targets_str}]")

        # Add summary of typical workflow
        if status_transitions:
            lines.append("")
            lines.append("**Workflow Summary:**")
            for status, targets in sorted(status_transitions.items()):
                lines.append(f"  - From '{status}': can transition to {sorted(targets)}")

        lines.append("")
        lines.append("**CRITICAL:** Do NOT suggest actions that require unavailable transitions!")
        lines.append("  - Example: If ticket is in 'To Do', you cannot skip to 'Code Review' - must go through 'In Progress' first")

        return "\n".join(lines)

    def _get_agent_id_by_jira_account_id(self, jira_account_id: str) -> str:
        """Map Jira account ID to agent_id for display purposes."""
        if not jira_account_id:
            return None
        for agent_id, config in self.personas.get("agents", {}).items():
            if config.get("jira_account_id") == jira_account_id:
                return agent_id
        return None

    def _get_advancement_summary(self, state: SimulationState, analysis: dict) -> dict:
        """Get summary of scenarios ready for advancement with specific actions needed."""
        summary = {
            "ready_count": 0,
            "ready_scenarios": [],
            "by_action": {}
        }

        opportunities = analysis.get("opportunities", [])
        phase_advancements = [
            o for o in opportunities
            if o.get("type") == "phase_advancement"
            and o.get("priority") == "high"
        ]

        for opp in phase_advancements:
            action = opp.get("suggested_action", "unknown")
            summary["ready_count"] += 1
            summary["ready_scenarios"].append({
                "ticket_key": opp.get("ticket_key"),
                "action": action,
                "agent_id": opp.get("agent_id"),
                "days_waiting": opp.get("days_in_phase", 0),
                "scenario_id": opp.get("scenario_id")
            })
            summary["by_action"][action] = summary["by_action"].get(action, 0) + 1

        return summary

    def _format_required_advancements(self, ready_scenarios: list) -> str:
        """Format the list of required advancement actions."""
        if not ready_scenarios:
            return "None currently"

        lines = []
        for s in ready_scenarios[:5]:  # Limit to 5 most urgent
            lines.append(
                f"  - {s['ticket_key']}: Needs '{s['action']}' by {s['agent_id']} "
                f"(waiting {s['days_waiting']:.1f} days)"
            )

        if len(ready_scenarios) > 5:
            lines.append(f"  ... and {len(ready_scenarios) - 5} more")

        return "\n".join(lines)

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
            logger.error(f"Failed to parse LLM response. Raw text (first 500 chars): {text[:500]}")
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

    def _find_ticket_in_snapshot(
        self, ticket_key: str, board_snapshot: dict
    ) -> dict | None:
        """Find a ticket in the board snapshot by key."""
        status_keys = ["backlog", "in_progress", "code_review", "testing", "done"]
        for status in status_keys:
            tickets = board_snapshot.get(status, [])
            for ticket in tickets:
                if ticket.get("key") == ticket_key:
                    return ticket
        return None

    def _is_transition_valid(
        self, action: dict, board_snapshot: dict
    ) -> bool:
        """
        Check if an action's target transition is available from Jira API data.

        Returns True if:
        - Ticket not found (can't validate, allow)
        - No transition info (allow)
        - Not a status-transition action (allow)
        - Target status is in available transitions (allow)

        Returns False if:
        - Target status is NOT in available transitions (block)
        """
        ticket_key = action.get("ticket_key")
        action_type = action.get("type")

        if not ticket_key or not action_type:
            return True  # Can't validate, allow

        # Find ticket in snapshot
        ticket = self._find_ticket_in_snapshot(ticket_key, board_snapshot)
        if not ticket:
            return True  # Ticket not in snapshot, can't validate

        available_transitions = ticket.get("available_transitions", [])
        if not available_transitions:
            return True  # No transition info from API, allow

        # Get target status for this action type
        target_status = self.action_target_status.get(action_type)
        if not target_status:
            return True  # Not a status-transition action (e.g., add_comment)

        # Check if any available transition leads to target status (fuzzy match)
        for t in available_transitions:
            to_status = t.get("to", "").lower()
            name = t.get("name", "").lower()
            target_lower = target_status.lower()

            # Match if target is contained in "to" status or transition name
            if target_lower in to_status or target_lower in name:
                return True
            # Also check if the transition name/to contains our target words
            if to_status in target_lower or name in target_lower:
                return True

        # No matching transition found
        logger.warning(
            f"Transition validation failed: {action_type} on {ticket_key} "
            f"(current: {ticket.get('status')}) - target '{target_status}' "
            f"not in available transitions: {[t.get('to') for t in available_transitions]}"
        )
        return False

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
        board_snapshot = analysis.get("board_snapshot", {})

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

            # Validate Jira transition is available (API-based)
            # Skip validation for script-based actions - they're pre-validated by pathfinder
            if not action.get("from_script") and not self._is_transition_valid(action, board_snapshot):
                logger.warning(
                    f"VALIDATION BLOCKED: Transition not available for {action.get('type')} "
                    f"on {action.get('ticket_key')}. Skipping action."
                )
                continue

            # Validate ticket exists in scenario if scenario_id provided
            scenario_id = action.get("scenario_id")
            if scenario_id and scenario_id not in state.active_scenarios:
                # Clear invalid scenario_id
                action["scenario_id"] = None

            validated.append(action)

            if agent_id:
                used_agents.add(agent_id)

        # Safety net: Ensure at least one phase advancement if any are available
        advancement_action_types = {
            "complete_review", "qa_approve", "verify_fix",
            "progress_to_review", "resolve_blocker", "complete_fix"
        }
        has_advancement = any(a.get("type") in advancement_action_types for a in validated)

        if not has_advancement:
            # Check if there are ready-to-advance scenarios we should inject
            phase_advancements = [
                o for o in analysis.get("opportunities", [])
                if o.get("type") == "phase_advancement"
                and o.get("priority") == "high"
                and o.get("agent_id") not in used_agents
            ]

            if phase_advancements:
                # Inject the most urgent one at the front of the action list
                opp = phase_advancements[0]
                injected_action = {
                    "type": opp.get("suggested_action", "unknown"),
                    "scenario_id": opp.get("scenario_id"),
                    "ticket_key": opp.get("ticket_key"),
                    "agent_id": opp.get("agent_id"),
                    "details": "Validator-injected: overdue item prioritized",
                }
                validated.insert(0, injected_action)
                used_agents.add(opp.get("agent_id"))
                logger.info(
                    f"Validator injected advancement for {opp.get('ticket_key')} - "
                    f"planner overlooked {len(phase_advancements)} ready scenarios"
                )

        return validated

    def _fallback_plan(
        self,
        analysis: dict,
        state: SimulationState,
        target_actions: int,
    ) -> list[dict]:
        """Create a fallback plan with guaranteed minimum phase advancements."""
        actions = []
        used_agents = set()
        opportunities = analysis.get("opportunities", [])

        # PRIORITY 1: Phase advancements (at least 60% of actions when available)
        phase_advancements = [
            o for o in opportunities
            if o.get("type") == "phase_advancement"
            and o.get("priority") == "high"
        ]

        # Calculate minimum advancements: 60% of target, or all available, whichever is less
        min_advancements = min(
            len(phase_advancements),
            max(1, int(target_actions * 0.6))
        ) if phase_advancements else 0

        for opp in phase_advancements[:min_advancements]:
            agent_id = opp.get("agent_id")
            if agent_id and agent_id not in used_agents:
                actions.append({
                    "type": opp.get("suggested_action", "unknown"),
                    "scenario_id": opp.get("scenario_id"),
                    "ticket_key": opp.get("ticket_key"),
                    "agent_id": agent_id,
                    "details": f"Fallback: advancing {opp.get('ticket_key')} from {opp.get('current_phase', 'unknown')}",
                })
                used_agents.add(agent_id)

        # PRIORITY 2: Other high priority opportunities (violations, sprints, etc.)
        remaining_slots = target_actions - len(actions)
        other_high = [
            o for o in opportunities
            if o.get("priority") == "high"
            and o.get("type") != "phase_advancement"
            and o.get("agent_id") not in used_agents
        ]

        for opp in other_high[:remaining_slots]:
            agent_id = opp.get("agent_id") or opp.get("pm_id")
            if agent_id and agent_id not in used_agents:
                actions.append({
                    "type": opp.get("suggested_action", opp.get("type", "unknown")),
                    "scenario_id": opp.get("scenario_id"),
                    "ticket_key": opp.get("ticket_key") or opp.get("epic_key"),
                    "agent_id": agent_id,
                    "details": opp.get("description", ""),
                })
                used_agents.add(agent_id)

        # PRIORITY 3: Medium priority opportunities to fill remaining slots
        remaining_slots = target_actions - len(actions)
        if remaining_slots > 0:
            medium = [
                o for o in opportunities
                if o.get("priority") == "medium"
            ]
            for opp in medium[:remaining_slots]:
                agent_id = opp.get("agent_id") or opp.get("pm_id")
                if agent_id and agent_id not in used_agents:
                    actions.append({
                        "type": opp.get("suggested_action", opp.get("type", "unknown")),
                        "scenario_id": opp.get("scenario_id"),
                        "ticket_key": opp.get("ticket_key"),
                        "agent_id": agent_id,
                        "details": opp.get("description", ""),
                    })
                    used_agents.add(agent_id)

        logger.info(f"Fallback plan: {len(actions)} actions ({min_advancements} forced advancements)")
        return actions

    def _get_sprint_scenario_actions(
        self,
        state: SimulationState,
        max_actions: int = 5,
    ) -> list[dict]:
        """
        Get actions from the current sprint scenario script.

        Uses the new sprint-level scenario system instead of per-ticket scenarios.
        The ScriptExecutor converts script events into orchestrator actions.

        Args:
            state: Current simulation state
            max_actions: Maximum actions to return

        Returns:
            List of action dicts from the sprint scenario
        """
        sprint_scenario = state.get_sprint_scenario()
        if not sprint_scenario:
            logger.debug("No active sprint scenario")
            return []

        # Build agent list for the executor
        agents = []
        for agent_id, agent_config in self.personas.get("agents", {}).items():
            agents.append({
                "id": agent_id,
                "type": agent_config.get("role", "developer"),
                "team": agent_config.get("team", "alpha"),
                "name": agent_config.get("display_name", agent_id),
            })

        # Create executor and get actions
        executor = ScriptExecutor(agents)
        actions = executor.get_actions_for_tick(sprint_scenario, max_actions)

        if actions:
            logger.info(
                f"Sprint scenario '{sprint_scenario.archetype.value}' "
                f"day {sprint_scenario.current_day}: {len(actions)} scripted actions"
            )

        # Update the scenario in state (to persist event execution tracking)
        state.set_sprint_scenario(sprint_scenario)

        return actions

    def _get_script_based_actions(
        self,
        state: SimulationState,
    ) -> list[dict]:
        """
        Get actions from scenario scripts that are ready to execute.

        First checks for sprint-level scenario actions, then falls back
        to per-ticket scenario scripts (deprecated).

        Returns list of action dicts ready for execution.
        """
        # NEW: First try sprint-level scenario
        sprint_actions = self._get_sprint_scenario_actions(state)
        if sprint_actions:
            return sprint_actions

        # LEGACY: Fall back to per-ticket scenarios (deprecated)
        actions = []
        used_agents = set()

        for scenario in state.active_scenarios.values():
            # Skip if scenario doesn't have a script
            if not scenario.action_script:
                continue

            # Skip if phase isn't ready to advance
            if not scenario.is_phase_ready_to_advance():
                continue

            # Get next script action
            next_action = scenario.get_next_script_action()
            if not next_action:
                continue

            # Skip optional actions sometimes (50% chance)
            import random
            if next_action.optional and random.random() < 0.5:
                continue

            # Find agent for this action's role
            agent_id = self._find_agent_for_role(
                role=next_action.role,
                scenario=scenario,
                used_agents=used_agents,
            )

            if not agent_id:
                continue

            # Build action dict
            action = {
                "type": next_action.type,
                "ticket_key": scenario.ticket_key,
                "scenario_id": scenario.scenario_id,
                "agent_id": agent_id,
                "from_script": True,
                "details": f"Script action: {next_action.type}" + (
                    f" ({next_action.context})" if next_action.context else ""
                ),
            }

            actions.append(action)
            used_agents.add(agent_id)

        if actions:
            logger.info(f"Generated {len(actions)} script-based actions")

        return actions

    def _find_agent_for_role(
        self,
        role: str,
        scenario,
        used_agents: set,
    ) -> Optional[str]:
        """Find an available agent for a given role, preferring scenario's assigned agent."""
        # For developer actions, prefer the assigned agent
        if role == "developer" and scenario.assigned_agent:
            if scenario.assigned_agent not in used_agents:
                return scenario.assigned_agent

        # Get team from assigned agent's config
        team = None
        if scenario.assigned_agent:
            agent_config = self.personas.get("agents", {}).get(scenario.assigned_agent, {})
            team = agent_config.get("team")

        # Find any agent with matching role (prefer same team)
        candidates = []
        for agent_id, config in self.personas.get("agents", {}).items():
            if agent_id in used_agents:
                continue
            if config.get("role") == role:
                if team and config.get("team") == team:
                    candidates.insert(0, agent_id)  # Prefer same team
                else:
                    candidates.append(agent_id)

        return candidates[0] if candidates else None

    def _convert_directives_to_actions(
        self,
        directives: list[ReleaseDirective],
        state: SimulationState,
    ) -> list[dict]:
        """
        Convert Release Manager directives into PM actions.

        Directives are instructions from the Release Manager that need to be
        executed by PM agents. This method converts them to the action format
        used by the orchestrator's execute phase.

        Args:
            directives: List of ReleaseDirective objects from coordination phase
            state: Current simulation state

        Returns:
            List of action dicts ready for execution
        """
        actions = []

        for directive in directives:
            # Skip already executed directives
            if directive.executed:
                continue

            # Validate target PM exists
            if directive.target_pm_id not in self.personas.get("agents", {}):
                logger.warning(
                    f"Directive {directive.directive_id} targets unknown PM: {directive.target_pm_id}"
                )
                continue

            # Build action dict from directive
            action = {
                "type": directive.directive_type,
                "agent_id": directive.target_pm_id,
                "from_directive": True,
                "directive_id": directive.directive_id,
                "details": directive.parameters.get("reason", "Release Manager directive"),
            }

            # Add parameters based on directive type
            if directive.directive_type == "create_fix_version":
                action["version_name"] = directive.parameters.get("version_name")
                action["target_date"] = directive.parameters.get("target_date")

            elif directive.directive_type == "assign_fix_version":
                action["ticket_key"] = directive.parameters.get("ticket_key")
                action["version_name"] = directive.parameters.get("version_name")

            elif directive.directive_type == "release_reminder":
                action["version_name"] = directive.parameters.get("version_name")
                action["message"] = directive.parameters.get("message")

            elif directive.directive_type == "release_version":
                action["version_name"] = directive.parameters.get("version_name")
                action["transition_done_to_closed"] = directive.parameters.get(
                    "transition_done_to_closed", True
                )

            elif directive.directive_type == "rollover_items":
                action["from_version"] = directive.parameters.get("from_version")
                action["to_version"] = directive.parameters.get("to_version")

            actions.append(action)

            logger.info(
                f"Converted directive {directive.directive_id} ({directive.directive_type}) "
                f"to PM action for {directive.target_pm_id}"
            )

        if actions:
            logger.info(f"Converted {len(actions)} Release Manager directives to PM actions")

        return actions
