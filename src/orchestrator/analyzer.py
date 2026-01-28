"""
Scenario Analyzer - rules-based opportunity detection.

Analyzes the current board state and simulation state to identify
opportunities for scenario actions. This provides input to the
LLM planner.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
import random
import pendulum

logger = logging.getLogger(__name__)

from ..services.jira_client import JiraClient
from ..state import (
    SimulationState,
    ActiveScenario,
    ScenarioType,
    ScenarioPhase,
    TicketComplexity,
    ISSUE_TYPE_TO_COMPLEXITY,
)


class ScenarioAnalyzer:
    """
    Analyzes board and simulation state to detect opportunities.

    Opportunities are potential actions that could be taken to:
    1. Advance existing scenarios
    2. Inject new scenarios
    3. Maintain scenario balance
    """

    def __init__(
        self,
        jira_client: JiraClient,
        personas: dict,
        settings: dict,
    ):
        self.jira = jira_client
        self.personas = personas
        self.settings = settings

        # Get scenario settings
        self.scenario_config = settings.get("scenarios", {})
        self.distribution_targets = self.scenario_config.get("distribution_targets", {
            "normal_flow": 0.60,
            "blocker": 0.15,
            "rework": 0.15,
            "scope_creep": 0.05,
            "dependency": 0.05,
        })
        self.probabilities = self.scenario_config.get("probabilities", {
            "junior_rejection_rate": 0.30,
            "mid_rejection_rate": 0.15,
            "senior_rejection_rate": 0.05,
            "blocker_probability": 0.15,
            "dependency_probability": 0.10,
        })

        # Issue type permissions by role
        self.issue_type_permissions = settings.get("issue_type_permissions", {
            "pm": {"can_act_on": ["Epic", "Story", "Bug", "Task"], "can_create": ["Epic", "Story"]},
            "developer": {"can_act_on": ["Story", "Bug", "Task"], "can_create": ["Bug"]},
            "qa": {"can_act_on": ["Story", "Bug", "Task"], "can_create": ["Bug"]},
            "tech_lead": {"can_act_on": ["Story", "Bug", "Task"], "can_create": ["Bug"]},
        })

    def get_board_snapshot(self, sprint_only: bool = True) -> dict:
        """
        Get current state of the Jira board organized by status.

        Args:
            sprint_only: If True, only include items in the active sprint (default True)

        Returns:
            Dict mapping status names to lists of ticket info
        """
        snapshot = {
            "backlog": [],
            "in_progress": [],
            "code_review": [],
            "testing": [],
            "done": [],
            "active_sprint": None,
            "jira_versions": [],
        }

        try:
            # Get active sprint info
            active_sprint = self.jira.get_active_sprint()
            snapshot["active_sprint"] = active_sprint

            # Get fix versions from Jira for release management sync
            try:
                snapshot["jira_versions"] = self.jira.get_fix_versions()
            except Exception as e:
                logger.warning(f"Failed to get fix versions: {e}")
                snapshot["jira_versions"] = []

            # Get sprint issues directly if we only want sprint items
            if sprint_only and active_sprint:
                all_issues = self.jira.get_sprint_issues(active_sprint["id"])
            else:
                all_issues = self.jira.get_project_issues(max_results=100)

            for issue in all_issues:
                status = issue.fields.status.name.lower()
                assignee = issue.fields.assignee
                issue_type = issue.fields.issuetype.name

                # Get fix version info
                fix_versions = issue.fields.fixVersions or []
                fix_version = fix_versions[0].name if fix_versions else None
                fix_version_id = fix_versions[0].id if fix_versions else None

                ticket_info = {
                    "key": issue.key,
                    "summary": issue.fields.summary,
                    "status": issue.fields.status.name,
                    "type": issue_type,
                    "assignee": assignee.displayName if assignee else None,
                    "assignee_id": assignee.accountId if assignee else None,
                    "priority": (
                        issue.fields.priority.name if issue.fields.priority else "Medium"
                    ),
                    "created": str(issue.fields.created),
                    "in_active_sprint": True if sprint_only else self._is_in_active_sprint(issue.key),
                    "fix_version": fix_version,
                    "fix_version_id": fix_version_id,
                }

                # Fetch available transitions from Jira API (skip for done items)
                if status not in ["done", "closed", "resolved"]:
                    ticket_info["available_transitions"] = self._get_available_transitions(issue.key)
                else:
                    ticket_info["available_transitions"] = []

                # Map to our categories
                if status in ["to do", "backlog", "open"]:
                    snapshot["backlog"].append(ticket_info)
                elif status in ["in progress"]:
                    snapshot["in_progress"].append(ticket_info)
                elif status in ["code review", "in review", "review"]:
                    snapshot["code_review"].append(ticket_info)
                elif status in ["testing", "qa", "ready for qa", "in testing"]:
                    snapshot["testing"].append(ticket_info)
                elif status in ["done", "closed", "resolved"]:
                    snapshot["done"].append(ticket_info)

        except Exception as e:
            # Return empty snapshot on error
            logger.error(f"Failed to create board snapshot: {e}")

        return snapshot

    def _is_in_active_sprint(self, issue_key: str) -> bool:
        """Check if an issue is in the active sprint."""
        sprint_info = self.jira.get_issue_sprint_info(issue_key)
        return sprint_info is not None and sprint_info.get("state") == "active"

    def _get_available_transitions(self, issue_key: str) -> list[dict]:
        """
        Get available transitions for an issue from Jira API.

        Returns list of dicts with 'name' (transition name) and 'to' (target status).
        """
        try:
            transitions = self.jira.get_transitions(issue_key)
            return [
                {
                    "name": t.get("name", ""),
                    "to": t.get("to", {}).get("name", t.get("name", "")),
                }
                for t in transitions
            ]
        except Exception as e:
            logger.warning(f"Failed to get transitions for {issue_key}: {e}")
            return []

    def analyze(self, state: SimulationState) -> dict:
        """
        Perform full analysis of current state.

        Returns:
            Analysis dict with board_snapshot, opportunities, and metrics
        """
        board_snapshot = self.get_board_snapshot()
        opportunities = self.detect_opportunities(state, board_snapshot)
        metrics = self.calculate_metrics(state, board_snapshot)

        return {
            "board_snapshot": board_snapshot,
            "opportunities": opportunities,
            "metrics": metrics,
            "timestamp": pendulum.now("UTC").isoformat(),
        }

    def detect_opportunities(
        self,
        state: SimulationState,
        board_snapshot: dict,
    ) -> list[dict]:
        """
        Detect all opportunities for scenario actions.

        Returns:
            List of opportunity dicts with type, description, and relevant data
        """
        opportunities = []

        # 1. Check scenarios ready to advance
        opportunities.extend(self._detect_phase_advancements(state))

        # 2. Check for potential blockers to inject
        opportunities.extend(self._detect_blocker_opportunities(state))

        # 3. Check for potential rework scenarios
        opportunities.extend(self._detect_rework_opportunities(state))

        # 4. Check for dependency opportunities
        opportunities.extend(self._detect_dependency_opportunities(state, board_snapshot))

        # 5. Check for scope creep opportunities
        opportunities.extend(self._detect_scope_creep_opportunities(state, board_snapshot))

        # 6. Check for tickets needing pickup
        opportunities.extend(self._detect_pickup_opportunities(state, board_snapshot))

        # 7. Check scenario balance
        opportunities.extend(self._detect_balance_opportunities(state))

        # 8. Check for epic lifecycle issues
        opportunities.extend(self._detect_epic_lifecycle_opportunities())

        # 9. Check for unassigned epics
        opportunities.extend(self._detect_unassigned_epic_opportunities())

        # 10. Check for sprint planning opportunities
        opportunities.extend(
            self._detect_sprint_planning_opportunities(state, board_snapshot)
        )

        # 11. Check for process violations to fix (gradual cleanup)
        violations = self._detect_all_violations(state, board_snapshot)
        # Limit to 2 violations per tick for gradual cleanup
        opportunities.extend(violations[:2])

        return opportunities

    def _detect_phase_advancements(self, state: SimulationState) -> list[dict]:
        """Detect scenarios ready to advance to next phase."""
        opportunities = []

        for scenario in state.active_scenarios.values():
            if scenario.is_phase_ready_to_advance():
                # Determine what the next action should be
                next_action = self._get_next_action_for_phase(scenario)

                # Determine the appropriate agent based on the current phase
                # This ensures proper role-based workflow: Developer → Tech Lead → QA
                suggested_agent = self._get_agent_for_phase(scenario)

                # Only include opportunity if we have a valid agent
                valid_agent = self._get_valid_agent_id(suggested_agent)
                if valid_agent:
                    opportunities.append({
                        "type": "phase_advancement",
                        "priority": "high",
                        "scenario_id": scenario.scenario_id,
                        "ticket_key": scenario.ticket_key,
                        "current_phase": scenario.current_phase.value,
                        "suggested_action": next_action,
                        "agent_id": valid_agent,
                        "description": f"{scenario.ticket_key} ready to advance from {scenario.current_phase.value}",
                        "days_in_phase": round(scenario.get_days_in_current_phase(), 1),
                    })

        return opportunities

    def _get_agent_for_phase(self, scenario: ActiveScenario) -> Optional[str]:
        """
        Get the appropriate agent for the next phase action.

        Ensures proper role-based workflow:
        - Developer phases: assigned developer handles (backlog, in_progress, fixing)
        - Code review phases: tech lead reviews
        - Testing phases: QA tests
        """
        if not scenario.assigned_agent:
            return None

        # Get team from assigned developer
        dev_persona = self.personas.get("agents", {}).get(scenario.assigned_agent, {})
        team = dev_persona.get("team", "alpha")
        team_agents = self._get_team_agents(team)

        phase = scenario.current_phase

        # Developer-owned phases
        if phase in [
            ScenarioPhase.BACKLOG,
            ScenarioPhase.ASSIGNED,
            ScenarioPhase.IN_PROGRESS,
            ScenarioPhase.REJECTED,
            ScenarioPhase.FIXING,
            ScenarioPhase.BLOCKED,
            ScenarioPhase.BLOCKER_DISCUSSED,
        ]:
            return scenario.assigned_agent

        # Tech lead reviews code
        if phase in [ScenarioPhase.IN_REVIEW, ScenarioPhase.RE_REVIEW]:
            tech_lead = team_agents.get("tech_lead")
            return tech_lead if tech_lead else scenario.assigned_agent

        # QA tests
        if phase in [ScenarioPhase.IN_TESTING, ScenarioPhase.RE_TESTING]:
            qa = team_agents.get("qa")
            return qa if qa else scenario.assigned_agent

        # Default to assigned developer
        return scenario.assigned_agent

    def _get_next_action_for_phase(self, scenario: ActiveScenario) -> str:
        """Determine the next action based on current phase."""
        phase_transitions = {
            ScenarioPhase.BACKLOG: "pick_up_task",
            ScenarioPhase.ASSIGNED: "start_work",
            ScenarioPhase.IN_PROGRESS: "progress_to_review",
            ScenarioPhase.IN_REVIEW: "complete_review",
            ScenarioPhase.IN_TESTING: "qa_approve",  # Fixed: Use qa_approve instead of qa_test
            ScenarioPhase.BLOCKED: "discuss_blocker",
            ScenarioPhase.BLOCKER_DISCUSSED: "resolve_blocker",
            ScenarioPhase.REJECTED: "acknowledge_rejection",
            ScenarioPhase.FIXING: "complete_fix",
            ScenarioPhase.RE_REVIEW: "complete_review",
            ScenarioPhase.RE_TESTING: "verify_fix",
            ScenarioPhase.WAITING_ON_DEPENDENCY: "check_dependency",
        }
        return phase_transitions.get(scenario.current_phase, "unknown")

    def _detect_blocker_opportunities(self, state: SimulationState) -> list[dict]:
        """Detect opportunities to inject blocker scenarios."""
        opportunities = []

        # Only inject blockers if we're below target
        current_blocker_rate = self._get_scenario_rate(state, ScenarioType.BLOCKER)
        target_rate = self.distribution_targets.get("blocker", 0.15)

        if current_blocker_rate >= target_rate:
            return opportunities

        # Find in-progress scenarios that could become blocked
        for scenario in state.active_scenarios.values():
            if (
                scenario.scenario_type == ScenarioType.NORMAL_FLOW
                and scenario.current_phase == ScenarioPhase.IN_PROGRESS
                and scenario.get_days_in_current_phase() >= 1  # In progress for at least a day
            ):
                # Random chance based on config
                if random.random() < self.probabilities.get("blocker_probability", 0.15):
                    # Only include if we have a valid agent
                    valid_agent = self._get_valid_agent_id(scenario.assigned_agent)
                    if valid_agent:
                        opportunities.append({
                            "type": "inject_blocker",
                            "priority": "medium",
                            "scenario_id": scenario.scenario_id,
                            "ticket_key": scenario.ticket_key,
                            "description": f"Opportunity to inject blocker on {scenario.ticket_key}",
                            "agent_id": valid_agent,
                        })

        return opportunities

    def _detect_rework_opportunities(self, state: SimulationState) -> list[dict]:
        """Detect opportunities to inject rework (QA rejection) scenarios."""
        opportunities = []

        # Only inject rework if below target
        current_rework_rate = self._get_scenario_rate(state, ScenarioType.REWORK)
        target_rate = self.distribution_targets.get("rework", 0.15)

        if current_rework_rate >= target_rate:
            return opportunities

        # Find testing scenarios that could be rejected
        for scenario in state.active_scenarios.values():
            if (
                scenario.scenario_type == ScenarioType.NORMAL_FLOW
                and scenario.current_phase == ScenarioPhase.IN_TESTING
            ):
                # Get developer's seniority for rejection probability
                rejection_prob = self._get_rejection_probability(scenario.assigned_agent)

                if random.random() < rejection_prob:
                    # Only include if we have a valid agent
                    valid_agent = self._get_valid_agent_id(scenario.assigned_agent)
                    if valid_agent:
                        opportunities.append({
                            "type": "inject_rework",
                            "priority": "medium",
                            "scenario_id": scenario.scenario_id,
                            "ticket_key": scenario.ticket_key,
                            "description": f"Opportunity to reject {scenario.ticket_key} in QA",
                            "assigned_agent": valid_agent,
                        })

        return opportunities

    def _get_rejection_probability(self, agent_id: Optional[str]) -> float:
        """Get rejection probability based on developer seniority."""
        if not agent_id:
            return self.probabilities.get("mid_rejection_rate", 0.15)

        persona = self.personas.get("agents", {}).get(agent_id, {})
        seniority = persona.get("seniority", "mid")

        seniority_rates = {
            "junior": self.probabilities.get("junior_rejection_rate", 0.30),
            "mid": self.probabilities.get("mid_rejection_rate", 0.15),
            "senior": self.probabilities.get("senior_rejection_rate", 0.05),
        }

        return seniority_rates.get(seniority, 0.15)

    def _detect_dependency_opportunities(
        self,
        state: SimulationState,
        board_snapshot: dict,
    ) -> list[dict]:
        """Detect opportunities for cross-team dependency scenarios."""
        opportunities = []

        # Only if below target
        current_dep_rate = self._get_scenario_rate(state, ScenarioType.DEPENDENCY)
        if current_dep_rate >= self.distribution_targets.get("dependency", 0.05):
            return opportunities

        # Find in-progress tickets that could have cross-team dependencies
        for scenario in state.active_scenarios.values():
            if (
                scenario.scenario_type == ScenarioType.NORMAL_FLOW
                and scenario.current_phase == ScenarioPhase.IN_PROGRESS
                and random.random() < self.probabilities.get("dependency_probability", 0.10)
            ):
                # Find a ticket from another team to create dependency
                other_team_ticket = self._find_other_team_ticket(scenario, board_snapshot)
                if other_team_ticket:
                    opportunities.append({
                        "type": "inject_dependency",
                        "priority": "medium",
                        "scenario_id": scenario.scenario_id,
                        "ticket_key": scenario.ticket_key,
                        "dependency_ticket": other_team_ticket["key"],
                        "dependency_team": other_team_ticket.get("team", "beta"),
                        "description": f"Opportunity for {scenario.ticket_key} to depend on {other_team_ticket['key']}",
                    })

        return opportunities

    def _find_other_team_ticket(
        self,
        scenario: ActiveScenario,
        board_snapshot: dict,
    ) -> Optional[dict]:
        """Find a ticket from another team to create a dependency."""
        if not scenario.assigned_agent:
            return None

        # Get current agent's team
        persona = self.personas.get("agents", {}).get(scenario.assigned_agent, {})
        current_team = persona.get("team", "alpha")
        other_team = "beta" if current_team == "alpha" else "alpha"

        # Find an in-progress ticket from the other team
        for ticket in board_snapshot.get("in_progress", []):
            agent_id = self._find_agent_by_jira_account(ticket.get("assignee_id"))
            if agent_id:
                agent_persona = self.personas.get("agents", {}).get(agent_id, {})
                if agent_persona.get("team") == other_team:
                    ticket["team"] = other_team
                    return ticket

        return None

    def _find_agent_by_jira_account(self, account_id: Optional[str]) -> Optional[str]:
        """Find agent_id by Jira account ID."""
        if not account_id:
            return None
        for agent_id, config in self.personas.get("agents", {}).items():
            if config.get("jira_account_id") == account_id:
                return agent_id
        return None

    def _is_valid_agent_id(self, agent_id: Optional[str]) -> bool:
        """Check if an agent_id exists in personas config."""
        if not agent_id:
            return False
        return agent_id in self.personas.get("agents", {})

    def _get_valid_agent_id(self, agent_id: Optional[str]) -> Optional[str]:
        """Return agent_id only if it's valid, otherwise None."""
        if self._is_valid_agent_id(agent_id):
            return agent_id
        return None

    def _detect_scope_creep_opportunities(
        self,
        state: SimulationState,
        board_snapshot: dict,
    ) -> list[dict]:
        """Detect opportunities for mid-sprint scope creep."""
        opportunities = []

        # Only during mid-sprint
        if not state.sprint.is_mid_sprint():
            return opportunities

        # Check if we've already had enough scope creep this sprint
        scope_creep_count = state.scenario_distribution.scope_creep
        if scope_creep_count >= 2:  # Max 2 per sprint
            return opportunities

        # Determine which team should get scope creep
        for team in ["alpha", "beta"]:
            team_agents = self._get_team_agents(team)
            pm_id = team_agents.get("pm")
            if pm_id:
                opportunities.append({
                    "type": "scope_creep",
                    "priority": "low",
                    "team": team,
                    "pm_id": pm_id,
                    "description": f"Mid-sprint - Team {team.title()} could get an urgent story",
                })

        return opportunities

    def _get_allowed_issue_types(self, role: str) -> list[str]:
        """Get the issue types a role is allowed to act on."""
        role_permissions = self.issue_type_permissions.get(role, {})
        return role_permissions.get("can_act_on", ["Story", "Bug", "Task"])

    def _can_role_act_on_issue_type(self, role: str, issue_type: str) -> bool:
        """Check if a role can act on a specific issue type."""
        allowed_types = self._get_allowed_issue_types(role)
        return issue_type in allowed_types

    def _detect_pickup_opportunities(
        self,
        state: SimulationState,
        board_snapshot: dict,
    ) -> list[dict]:
        """Detect backlog items that should be picked up."""
        opportunities = []

        backlog = board_snapshot.get("backlog", [])
        if not backlog:
            return opportunities

        # Find available developers (workload < 5)
        for agent_id, agent in state.agents.items():
            if agent.is_overloaded:
                continue

            persona = self.personas.get("agents", {}).get(agent_id, {})
            if persona.get("role") != "developer":
                continue

            # Developer is available
            seniority = persona.get("seniority", "mid")
            # Get allowed issue types for developers
            allowed_types = self._get_allowed_issue_types("developer")

            # Find appropriate ticket for this developer
            for ticket in backlog:
                # Filter by issue type - developers can't act on Epics
                ticket_type = ticket.get("type", "Story")
                if ticket_type not in allowed_types:
                    continue

                # Items must be in active sprint to be picked up
                if not ticket.get("in_active_sprint"):
                    continue

                # Junior devs shouldn't take complex items
                if seniority == "junior":
                    if "complex" in ticket.get("summary", "").lower():
                        continue

                # Check if ticket already has a scenario
                existing = state.get_scenario_by_ticket(ticket["key"])
                if existing:
                    continue

                opportunities.append({
                    "type": "pick_up_backlog",
                    "priority": "medium",
                    "ticket_key": ticket["key"],
                    "ticket_summary": ticket["summary"],
                    "ticket_type": ticket_type,
                    "in_active_sprint": True,
                    "agent_id": agent_id,
                    "agent_name": persona.get("display_name"),
                    "description": (
                        f"{persona.get('display_name')} could pick up {ticket['key']}"
                    ),
                })
                break  # One ticket per developer

        return opportunities

    def _detect_balance_opportunities(self, state: SimulationState) -> list[dict]:
        """Detect when scenario types are unbalanced."""
        opportunities = []

        percentages = state.scenario_distribution.get_percentages()

        # Check each type against targets
        for scenario_type, target in self.distribution_targets.items():
            current = percentages.get(scenario_type, 0)
            if current < target * 0.5:  # More than 50% below target
                opportunities.append({
                    "type": "balance_adjustment",
                    "priority": "low",
                    "scenario_type": scenario_type,
                    "current_rate": round(current, 2),
                    "target_rate": target,
                    "description": f"{scenario_type} scenarios underrepresented ({current:.0%} vs {target:.0%} target)",
                })

        return opportunities

    def _get_scenario_rate(self, state: SimulationState, scenario_type: ScenarioType) -> float:
        """Get current rate of a scenario type."""
        percentages = state.scenario_distribution.get_percentages()
        return percentages.get(scenario_type.value, 0)

    def _get_team_agents(self, team: str) -> dict:
        """Get all agent IDs for a team, organized by role."""
        agents_by_role = {
            "pm": None,
            "tech_lead": None,
            "developer": [],
            "qa": None,
        }

        for agent_id, config in self.personas.get("agents", {}).items():
            if config.get("team") == team:
                role = config.get("role", "developer")
                if role in ["pm", "tech_lead", "qa"]:
                    agents_by_role[role] = agent_id
                else:
                    agents_by_role["developer"].append(agent_id)

        return agents_by_role

    def calculate_metrics(self, state: SimulationState, board_snapshot: dict) -> dict:
        """Calculate summary metrics for the analysis."""
        return {
            "total_active_scenarios": len(state.active_scenarios),
            "scenarios_ready_to_advance": len(state.get_scenarios_ready_to_advance()),
            "backlog_size": len(board_snapshot.get("backlog", [])),
            "in_progress_count": len(board_snapshot.get("in_progress", [])),
            "in_review_count": len(board_snapshot.get("code_review", [])),
            "in_testing_count": len(board_snapshot.get("testing", [])),
            "scenario_distribution": state.scenario_distribution.get_percentages(),
            "sprint_day": state.sprint.sprint_day,
            "is_mid_sprint": state.sprint.is_mid_sprint(),
        }

    # ==================== Epic Lifecycle Detection ====================

    def _detect_epic_lifecycle_opportunities(self) -> list[dict]:
        """Detect Epics that need status updates based on child issues."""
        opportunities = []

        try:
            epics_needing_update = self.jira.get_epics_needing_status_update()

            for epic_info in epics_needing_update:
                # Find appropriate PM for this epic based on team
                pm_id = self._find_pm_for_epic(epic_info["epic_key"])

                opportunities.append({
                    "type": "update_epic_status",
                    "priority": "medium",
                    "epic_key": epic_info["epic_key"],
                    "current_status": epic_info["current_status"],
                    "suggested_status": epic_info["suggested_status"],
                    "reason": epic_info["reason"],
                    "child_count": epic_info["child_count"],
                    "pm_id": pm_id,
                    "description": (
                        f"Epic {epic_info['epic_key']} should be "
                        f"'{epic_info['suggested_status']}' - {epic_info['reason']}"
                    ),
                })
        except Exception as e:
            logger.warning(f"Failed to detect epic sync opportunities: {e}")

        return opportunities

    def _detect_unassigned_epic_opportunities(self) -> list[dict]:
        """Detect Epics that are not assigned to a PM."""
        opportunities = []

        # PM account IDs (Sarah Chen and David Kim)
        pm_account_ids = set()
        for agent_id, config in self.personas.get("agents", {}).items():
            if config.get("role") == "pm":
                pm_account_ids.add(config.get("jira_account_id"))

        try:
            epics = self.jira.get_epics()

            for epic in epics:
                assignee = epic.fields.assignee
                assignee_id = assignee.accountId if assignee else None

                # Check if Epic is unassigned or assigned to non-PM
                if not assignee_id or assignee_id not in pm_account_ids:
                    # Find appropriate PM based on team hints
                    pm_id = self._find_pm_for_epic(epic.key)

                    opportunities.append({
                        "type": "assign_epic_to_pm",
                        "priority": "medium",
                        "epic_key": epic.key,
                        "epic_summary": epic.fields.summary,
                        "current_assignee": assignee.displayName if assignee else None,
                        "pm_id": pm_id,
                        "description": (
                            f"Epic {epic.key} should be assigned to PM "
                            f"for proper ownership"
                        ),
                    })
        except Exception as e:
            logger.warning(f"Failed to detect unassigned epic opportunities: {e}")

        return opportunities

    def _find_pm_for_epic(self, epic_key: str) -> Optional[str]:
        """
        Find the appropriate PM for an Epic.

        Tries to determine team from Epic content/labels, defaults to alpha PM.
        """
        try:
            epic = self.jira.get_issue(epic_key)
            summary = (epic.fields.summary or "").lower()
            labels = epic.fields.labels or []

            # Check for team hints in labels or summary
            if "beta" in labels or "beta" in summary or "ux" in summary:
                return self._get_team_agents("beta").get("pm")
            return self._get_team_agents("alpha").get("pm")
        except Exception as e:
            # Default to alpha PM
            logger.warning(f"Failed to find PM for epic {epic_key}: {e}")
            return self._get_team_agents("alpha").get("pm")

    # ==================== Sprint Planning Detection ====================

    def _detect_sprint_planning_opportunities(
        self,
        state: SimulationState,
        board_snapshot: dict,
    ) -> list[dict]:
        """
        Detect when sprint planning activities are needed.

        Triggers on:
        - No active sprint (need to start one) - checked always
        - Sprint completion day (day 7) - complete active sprint
        - Sprint planning day (Monday / day 1) - allocate items
        - When future sprints < 2
        """
        opportunities = []

        try:
            # Get sprint info from Jira (source of truth)
            active_sprint = board_snapshot.get("active_sprint")
            future_sprints = self.jira.get_future_sprints(max_results=4)

            # CRITICAL: Start sprint if no active sprint exists (check always)
            if not active_sprint and future_sprints:
                pm_id = self._get_team_agents("alpha").get("pm")
                if pm_id:
                    next_sprint = future_sprints[0]
                    opportunities.append({
                        "type": "start_sprint",
                        "priority": "critical",
                        "pm_id": pm_id,
                        "sprint_id": next_sprint["id"],
                        "sprint_name": next_sprint["name"],
                        "description": (
                            f"No active sprint - need to start {next_sprint['name']}"
                        ),
                    })

            # Complete sprint on last day (day 7)
            if state.sprint.is_sprint_complete_day() and active_sprint:
                pm_id = self._get_team_agents("alpha").get("pm")
                if pm_id:
                    # Include next_sprint_id so incomplete items roll over correctly
                    next_sprint_id = future_sprints[0].get("id") if future_sprints else None
                    opportunities.append({
                        "type": "complete_sprint",
                        "priority": "high",
                        "pm_id": pm_id,
                        "sprint_id": active_sprint.get("id"),
                        "sprint_name": active_sprint.get("name"),
                        "next_sprint_id": next_sprint_id,
                        "description": (
                            f"Sprint day 7 - time to complete "
                            f"{active_sprint.get('name')}"
                        ),
                    })

            # CRITICAL: Generate scenario if missing/stale for active sprint
            # This catches cases where sprint rolled over but no scenario exists
            # Note: Compare by name since scenario.sprint_id is number, not Jira internal ID
            if active_sprint:
                sprint_scenario = state.get_sprint_scenario()
                active_sprint_name = active_sprint.get("name")
                scenario_missing = sprint_scenario is None
                scenario_stale = (
                    sprint_scenario is not None
                    and sprint_scenario.sprint_name != active_sprint_name
                )

                if scenario_missing or scenario_stale:
                    pm_id = self._get_team_agents("alpha").get("pm")
                    if pm_id:
                        reason = "missing" if scenario_missing else "stale (different sprint)"
                        opportunities.append({
                            "type": "sprint_planning",
                            "priority": "critical",
                            "team": "alpha",
                            "pm_id": pm_id,
                            "sprint_id": active_sprint.get("id"),
                            "sprint_name": active_sprint.get("name"),
                            "unassigned_count": 0,
                            "scenario_reason": reason,
                            "description": (
                                f"Need to generate scenario for {active_sprint.get('name')} "
                                f"(scenario is {reason})"
                            ),
                        })
                        logger.info(
                            f"Detected {reason} scenario for sprint {active_sprint.get('name')} - "
                            f"triggering sprint_planning"
                        )
                        # Return immediately - this is critical priority
                        return opportunities

            # Only do regular planning activities on sprint planning day (day 1)
            if not state.sprint.is_sprint_planning_day():
                return opportunities

            # Get unassigned items (not in any sprint)
            unassigned_items = self.jira.get_issues_not_in_sprint(
                issue_types=["Story", "Bug", "Task"]
            )

            # Opportunity: Plan current sprint if there are unassigned items
            if active_sprint and unassigned_items:
                for team in ["alpha", "beta"]:
                    pm_id = self._get_team_agents(team).get("pm")
                    if pm_id:
                        opportunities.append({
                            "type": "sprint_planning",
                            "priority": "high",
                            "team": team,
                            "pm_id": pm_id,
                            "sprint_id": active_sprint.get("id"),
                            "sprint_name": active_sprint.get("name"),
                            "unassigned_count": len(unassigned_items),
                            "description": (
                                f"Sprint planning: {len(unassigned_items)} items "
                                f"need sprint assignment"
                            ),
                        })
                        break  # Only one PM needs to do planning

            # Opportunity: Create future sprints if < 2 exist
            future_sprint_count = len(future_sprints)
            target_future_sprints = self.settings.get("sprint", {}).get(
                "future_sprints_to_maintain", 2
            )

            if future_sprint_count < target_future_sprints:
                pm_id = self._get_team_agents("alpha").get("pm")
                if pm_id:
                    opportunities.append({
                        "type": "create_future_sprint",
                        "priority": "medium",
                        "pm_id": pm_id,
                        "current_sprint_number": state.sprint.sprint_number,
                        "existing_future_sprints": future_sprint_count,
                        "target_count": target_future_sprints,
                        "description": (
                            f"Need to create future sprints "
                            f"({future_sprint_count}/{target_future_sprints} exist)"
                        ),
                    })

        except Exception as e:
            logger.warning(f"Failed to detect sprint planning opportunities: {e}")

        return opportunities

    # ==================== Violation Detection ====================

    def _detect_all_violations(
        self,
        state: SimulationState,
        board_snapshot: dict,
    ) -> list[dict]:
        """
        Detect all process violations for gradual cleanup.

        Returns list of violations with fix recommendations.
        """
        violations = []

        violations.extend(self._detect_sprint_violations(board_snapshot))
        violations.extend(self._detect_unassigned_sprint_items(board_snapshot))
        violations.extend(self._detect_issue_type_violations(board_snapshot))
        violations.extend(self._detect_epic_sprint_violations())

        return violations

    def _detect_sprint_violations(self, board_snapshot: dict) -> list[dict]:
        """
        Detect items being worked on but not in active sprint.

        These are items in 'In Progress', 'Code Review', or 'Testing'
        status but not assigned to the active sprint.
        """
        violations = []

        work_statuses = ["in_progress", "code_review", "testing"]

        for status_key in work_statuses:
            for ticket in board_snapshot.get(status_key, []):
                if not ticket.get("in_active_sprint"):
                    # Find appropriate PM to fix this
                    pm_id = self._get_team_agents("alpha").get("pm")

                    violations.append({
                        "type": "fix_sprint_violation",
                        "priority": "high",
                        "ticket_key": ticket["key"],
                        "ticket_status": ticket["status"],
                        "violation_type": "work_without_sprint",
                        "pm_id": pm_id,
                        "description": (
                            f"{ticket['key']} is {ticket['status']} but not "
                            f"in active sprint"
                        ),
                        "fix_action": "add_to_active_sprint",
                        "fix_comment": (
                            "Added to active sprint - items being worked "
                            "must be in a sprint for proper tracking."
                        ),
                    })

        return violations

    def _detect_unassigned_sprint_items(self, board_snapshot: dict) -> list[dict]:
        """
        Detect sprint items without assignees.

        All items in the active sprint must have an assignee.
        """
        violations = []

        # Check all statuses except done
        for status_key in ["backlog", "in_progress", "code_review", "testing"]:
            for ticket in board_snapshot.get(status_key, []):
                if ticket.get("in_active_sprint") and not ticket.get("assignee"):
                    pm_id = self._get_team_agents("alpha").get("pm")

                    violations.append({
                        "type": "fix_unassigned_sprint_item",
                        "priority": "high",
                        "ticket_key": ticket["key"],
                        "ticket_status": ticket["status"],
                        "violation_type": "unassigned_sprint_item",
                        "pm_id": pm_id,
                        "description": (
                            f"{ticket['key']} is in active sprint but has no assignee"
                        ),
                        "fix_action": "assign_to_developer",
                    })

        return violations

    def _detect_issue_type_violations(self, board_snapshot: dict) -> list[dict]:
        """
        Detect developers assigned to Epics (should be PM-only).
        """
        violations = []

        # Get PM account IDs
        pm_account_ids = set()
        for agent_id, config in self.personas.get("agents", {}).items():
            if config.get("role") == "pm":
                pm_account_ids.add(config.get("jira_account_id"))

        try:
            epics = self.jira.get_epics()

            for epic in epics:
                assignee = epic.fields.assignee
                if not assignee:
                    continue

                # Check if assigned to non-PM
                if assignee.accountId not in pm_account_ids:
                    # Find appropriate PM to reassign to
                    pm_id = self._find_pm_for_epic(epic.key)

                    violations.append({
                        "type": "fix_issue_type_violation",
                        "priority": "medium",
                        "epic_key": epic.key,
                        "epic_summary": epic.fields.summary,
                        "current_assignee": assignee.displayName,
                        "violation_type": "non_pm_on_epic",
                        "pm_id": pm_id,
                        "description": (
                            f"Epic {epic.key} assigned to {assignee.displayName} "
                            f"(non-PM) - should be managed by PM"
                        ),
                        "fix_action": "reassign_to_pm",
                        "fix_comment": (
                            "Reassigned - Epics are managed by Product Management. "
                            "Developers work on Stories, Bugs, and Tasks."
                        ),
                    })
        except Exception as e:
            logger.warning(f"Failed to detect epic violations: {e}")

        return violations

    def _detect_epic_sprint_violations(self) -> list[dict]:
        """
        Detect Epics incorrectly placed in sprints.

        Epics should never be in sprints - only Stories, Bugs, and Tasks.
        """
        violations = []

        try:
            epics_in_sprints = self.jira.get_epics_in_sprints()

            for epic in epics_in_sprints:
                # Find appropriate PM to fix this
                pm_id = self._find_pm_for_epic(epic.key)

                violations.append({
                    "type": "fix_epic_sprint_violation",
                    "priority": "high",
                    "ticket_key": epic.key,
                    "violation_type": "epic_in_sprint",
                    "pm_id": pm_id,
                    "description": (
                        f"Epic {epic.key} is in a sprint - Epics should not "
                        f"be assigned to sprints"
                    ),
                    "fix_action": "remove_from_sprint",
                    "fix_comment": (
                        "Removed from sprint - Epics should not be assigned "
                        "to sprints. Only Stories, Bugs, and Tasks belong in sprints."
                    ),
                })
        except Exception as e:
            logger.warning(f"Failed to detect epic sprint violations: {e}")

        return violations

    # ==================== Release Compliance Detection ====================

    def detect_release_compliance_violations(
        self,
        state: SimulationState,
        board_snapshot: dict,
    ) -> list[dict]:
        """
        Detect tickets violating fix version requirements.

        Called by the Release Manager agent to identify compliance issues.

        Returns:
            List of violation dicts with ticket info and recommended fix
        """
        violations = []

        rm_settings = self.settings.get("release_management", {})
        if not rm_settings.get("enabled", False):
            return violations

        compliance = rm_settings.get("compliance", {})
        enforce_after = compliance.get("enforce_after_status", "In Progress")

        # Map of statuses that require fix versions
        enforce_statuses = {
            "In Progress": ["in_progress"],
            "Code Review": ["in_progress", "code_review"],
            "Testing": ["in_progress", "code_review", "testing"],
        }
        statuses_to_check = enforce_statuses.get(enforce_after, ["in_progress"])

        # Check tickets in enforced statuses
        for status_key in statuses_to_check:
            for ticket in board_snapshot.get(status_key, []):
                # Skip Epics (they don't need fix versions the same way)
                if ticket.get("type") == "Epic":
                    continue

                if not ticket.get("fix_version"):
                    # Find appropriate PM for this ticket
                    pm_id = self._find_pm_for_ticket(ticket)

                    violations.append({
                        "type": "fix_version_violation",
                        "priority": "medium",
                        "ticket_key": ticket["key"],
                        "ticket_summary": ticket.get("summary", ""),
                        "ticket_status": ticket["status"],
                        "ticket_type": ticket.get("type", "Story"),
                        "violation_type": "missing_fix_version",
                        "pm_id": pm_id,
                        "description": (
                            f"{ticket['key']} is {ticket['status']} but has no "
                            f"fix version assigned"
                        ),
                        "suggested_action": "assign_fix_version",
                    })

        return violations

    def detect_release_planning_opportunities(
        self,
        state: SimulationState,
    ) -> list[dict]:
        """
        Detect when release planning activities are needed.

        Called by the Release Manager agent.

        Returns:
            List of opportunity dicts for release planning actions
        """
        opportunities = []

        rm_settings = self.settings.get("release_management", {})
        if not rm_settings.get("enabled", False):
            return opportunities

        release_state = state.release_state
        schedule = rm_settings.get("schedule", {})

        # Check if we need to plan upcoming releases
        planned_count = len([
            r for r in release_state.planned_releases
            if r.status == "planned"
        ])

        planning_buffer = schedule.get("planning_buffer_sprints", 1)
        if planned_count < planning_buffer + 1:
            opportunities.append({
                "type": "plan_release",
                "priority": "medium",
                "planned_count": planned_count,
                "target_count": planning_buffer + 1,
                "description": (
                    f"Only {planned_count} releases planned - Release Manager "
                    f"should plan more"
                ),
            })

        # Check for upcoming release day
        release_day = schedule.get("release_day", 5)
        if state.sprint.sprint_day == release_day:
            current_release = release_state.get_current_release()
            if current_release:
                opportunities.append({
                    "type": "release_day",
                    "priority": "high",
                    "release_name": current_release.name,
                    "description": (
                        f"Today is release day - coordinate {current_release.name} "
                        f"release activities"
                    ),
                })

        # Check for releases missing from Jira
        for release in release_state.planned_releases:
            if not release.created_in_jira and release.status != "released":
                opportunities.append({
                    "type": "create_jira_version",
                    "priority": "high",
                    "release_name": release.name,
                    "target_date": release.target_date.isoformat() if release.target_date else None,
                    "description": (
                        f"Release {release.name} exists in state but not in Jira - "
                        f"PM should create the fix version"
                    ),
                })

        return opportunities

    def get_version_coverage_metrics(self, board_snapshot: dict) -> dict:
        """
        Calculate fix version coverage metrics across the board.

        Returns:
            Dict with coverage statistics
        """
        total = 0
        versioned = 0
        by_status = {}

        for status_key in ["in_progress", "code_review", "testing"]:
            status_tickets = board_snapshot.get(status_key, [])
            status_total = 0
            status_versioned = 0

            for ticket in status_tickets:
                # Skip Epics
                if ticket.get("type") == "Epic":
                    continue

                status_total += 1
                total += 1

                if ticket.get("fix_version"):
                    status_versioned += 1
                    versioned += 1

            by_status[status_key] = {
                "total": status_total,
                "versioned": status_versioned,
                "coverage": (
                    round(status_versioned / status_total * 100, 1)
                    if status_total > 0 else 100.0
                ),
            }

        return {
            "total_tracked": total,
            "total_versioned": versioned,
            "overall_coverage": (
                round(versioned / total * 100, 1) if total > 0 else 100.0
            ),
            "by_status": by_status,
        }

    def _find_pm_for_ticket(self, ticket: dict) -> Optional[str]:
        """
        Find the appropriate PM for a ticket based on assignee team.
        """
        assignee_id = ticket.get("assignee_id")
        if assignee_id:
            # Find agent by Jira account ID
            agent_id = self._find_agent_by_jira_account(assignee_id)
            if agent_id:
                persona = self.personas.get("agents", {}).get(agent_id, {})
                team = persona.get("team", "alpha")
                return self._get_team_agents(team).get("pm")

        # Default to alpha PM
        return self._get_team_agents("alpha").get("pm")
