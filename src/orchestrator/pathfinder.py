"""
Workflow Pathfinder - computes valid action sequences for Jira transitions.

Provides workflow intelligence to the orchestrator by:
1. Building a workflow graph from observed Jira transitions
2. Computing shortest paths between statuses using BFS
3. Generating action scripts for scenarios based on pathfinding
"""

import logging
from typing import Optional
from collections import deque

logger = logging.getLogger(__name__)


class WorkflowPathfinder:
    """Computes valid action sequences for Jira workflow transitions."""

    # Status -> Action type mapping (what action transitions TO this status)
    STATUS_TO_ACTION = {
        "in progress": "pick_up_task",
        "code review": "progress_to_review",
        "in review": "progress_to_review",
        "testing": "complete_review",
        "ready for qa": "complete_review",
        "in testing": "complete_review",
        "done": "qa_approve",
    }

    # Action type -> required role
    ACTION_ROLES = {
        "pick_up_task": "developer",
        "progress_to_review": "developer",
        "complete_review": "tech_lead",
        "qa_approve": "qa",
        "qa_reject": "qa",
        "add_progress_comment": "developer",
        "inject_blocker": "developer",
        "resolve_blocker": "developer",
        "acknowledge_rejection": "developer",
        "complete_fix": "developer",
    }

    # Rework script actions
    REWORK_ACTIONS = [
        {"type": "qa_reject", "target_status": "In Progress", "role": "qa"},
        {"type": "acknowledge_rejection", "target_status": None, "role": "developer"},
        {"type": "complete_fix", "target_status": "Code Review", "role": "developer"},
    ]

    # Blocker script actions
    BLOCKER_ACTIONS = [
        {"type": "inject_blocker", "target_status": "Blocked", "role": "developer"},
        {"type": "discuss_blocker", "target_status": None, "role": "tech_lead"},
        {"type": "resolve_blocker", "target_status": "In Progress", "role": "developer"},
    ]

    def __init__(self):
        self.workflow_graph: dict[str, set[str]] = {}
        self._graph_built = False

    def build_graph_from_snapshot(self, board_snapshot: dict) -> None:
        """
        Build workflow graph from current board snapshot transitions.

        This creates a directed graph where edges represent valid transitions.
        The graph is rebuilt each tick to reflect current Jira state.
        """
        self.workflow_graph.clear()

        for category in ["backlog", "in_progress", "code_review", "testing"]:
            for ticket in board_snapshot.get(category, []):
                current = ticket.get("status", "").lower().strip()
                for t in ticket.get("available_transitions", []):
                    target = t.get("to", "").lower().strip()
                    if current and target:
                        self.workflow_graph.setdefault(current, set()).add(target)

        self._graph_built = True
        logger.debug(
            f"Built workflow graph with {len(self.workflow_graph)} statuses: "
            f"{dict((k, list(v)) for k, v in self.workflow_graph.items())}"
        )

    def get_path(self, current_status: str, target_status: str) -> list[str]:
        """
        BFS to find shortest status path from current to target.

        Args:
            current_status: Starting status (e.g., "To Do")
            target_status: Target status (e.g., "Done")

        Returns:
            List of intermediate statuses to traverse (excluding start, including end).
            Empty list if no path found or already at target.
        """
        current = current_status.lower().strip()
        target = target_status.lower().strip()

        if current == target:
            return []

        if not self._graph_built:
            logger.warning("Workflow graph not built, cannot compute path")
            return []

        visited = {current}
        queue = deque([(current, [])])

        while queue:
            node, path = queue.popleft()
            for neighbor in self.workflow_graph.get(node, []):
                new_path = path + [neighbor]
                if neighbor == target:
                    return new_path
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, new_path))

        logger.warning(f"No path found from '{current}' to '{target}'")
        return []

    def get_action_for_status(self, target_status: str) -> Optional[str]:
        """Get the action type that transitions to a given status."""
        return self.STATUS_TO_ACTION.get(target_status.lower().strip())

    def generate_action_sequence(
        self,
        current_status: str,
        target_status: str,
    ) -> list[dict]:
        """
        Generate action sequence to go from current to target status.

        Args:
            current_status: Starting status
            target_status: Target status to reach

        Returns:
            List of action dicts with type, target_status, and role.
        """
        path = self.get_path(current_status, target_status)
        actions = []

        for status in path:
            action_type = self.get_action_for_status(status)
            if action_type:
                actions.append({
                    "type": action_type,
                    "target_status": status.title(),
                    "role": self.ACTION_ROLES.get(action_type),
                    "optional": False,
                })

        return actions

    def generate_scenario_script(
        self,
        scenario_type: str,
        current_status: str,
        complexity: str = "story",
    ) -> list[dict]:
        """
        Generate full action script for a scenario type.

        Args:
            scenario_type: Type of scenario (normal_flow, rework, blocker, etc.)
            current_status: Current ticket status
            complexity: Ticket complexity level

        Returns:
            List of planned actions forming the complete scenario script.
        """
        if scenario_type == "normal_flow":
            return self._generate_normal_flow_script(current_status, complexity)
        elif scenario_type == "rework":
            return self._generate_rework_script(current_status, complexity)
        elif scenario_type == "blocker":
            return self._generate_blocker_script(current_status, complexity)
        elif scenario_type == "scope_creep":
            return self._generate_scope_creep_script(current_status, complexity)
        elif scenario_type == "dependency":
            return self._generate_dependency_script(current_status, complexity)
        else:
            logger.warning(f"Unknown scenario type: {scenario_type}, using normal_flow")
            return self._generate_normal_flow_script(current_status, complexity)

    def _generate_normal_flow_script(
        self,
        current_status: str,
        complexity: str,
    ) -> list[dict]:
        """
        Normal flow: current -> Done with optional progress comments.

        A straightforward journey through the workflow.
        """
        base_actions = self.generate_action_sequence(current_status, "done")

        # Enrich with optional actions
        enriched = []
        for action in base_actions:
            enriched.append(action)
            # Add optional progress comment after pickup
            if action["type"] == "pick_up_task":
                enriched.append({
                    "type": "add_progress_comment",
                    "target_status": None,
                    "role": "developer",
                    "optional": True,
                })

        return enriched

    def _generate_rework_script(
        self,
        current_status: str,
        complexity: str,
    ) -> list[dict]:
        """
        Rework flow: Get to Testing, then QA rejects, fix, and complete.

        Injects a rejection cycle into the normal flow.
        """
        # First get to Testing status
        to_testing = self.generate_action_sequence(current_status, "testing")
        if not to_testing:
            # Try alternate status names
            to_testing = self.generate_action_sequence(current_status, "ready for qa")
        if not to_testing:
            to_testing = self.generate_action_sequence(current_status, "in testing")

        # Then add rework cycle
        rework_cycle = [
            {"type": "qa_reject", "target_status": "In Progress", "role": "qa", "optional": False},
            {"type": "acknowledge_rejection", "target_status": None, "role": "developer", "optional": False},
            {"type": "add_progress_comment", "target_status": None, "role": "developer", "optional": True},
            {"type": "complete_fix", "target_status": "Code Review", "role": "developer", "optional": False},
        ]

        # Then complete the journey
        post_fix = self.generate_action_sequence("code review", "done")

        return to_testing + rework_cycle + post_fix

    def _generate_blocker_script(
        self,
        current_status: str,
        complexity: str,
    ) -> list[dict]:
        """
        Blocker flow: Start work, hit a blocker, resolve it, complete.

        Injects a blocker interruption into the normal flow.
        """
        # First get to In Progress
        to_in_progress = self.generate_action_sequence(current_status, "in progress")

        # Blocker cycle
        blocker_cycle = [
            {"type": "inject_blocker", "target_status": None, "role": "developer", "optional": False},
            {"type": "discuss_blocker", "target_status": None, "role": "tech_lead", "optional": True},
            {"type": "add_progress_comment", "target_status": None, "role": "developer", "optional": True},
            {"type": "resolve_blocker", "target_status": "In Progress", "role": "developer", "optional": False},
        ]

        # Complete the journey after blocker resolved
        post_blocker = self.generate_action_sequence("in progress", "done")

        return to_in_progress + blocker_cycle + post_blocker

    def _generate_scope_creep_script(
        self,
        current_status: str,
        complexity: str,
    ) -> list[dict]:
        """
        Scope creep flow: Normal flow but with extra comments about scope changes.
        """
        base = self._generate_normal_flow_script(current_status, complexity)

        # Inject scope-related comments mid-development
        enriched = []
        for i, action in enumerate(base):
            enriched.append(action)
            # After picking up, add scope discussion
            if action["type"] == "pick_up_task":
                enriched.append({
                    "type": "add_progress_comment",
                    "target_status": None,
                    "role": "developer",
                    "optional": False,
                    "context": "scope_discussion",
                })

        return enriched

    def _generate_dependency_script(
        self,
        current_status: str,
        complexity: str,
    ) -> list[dict]:
        """
        Dependency flow: Normal flow but with waiting period.
        """
        # Get to in progress
        to_in_progress = self.generate_action_sequence(current_status, "in progress")

        # Dependency wait (simulated with comments)
        dependency_cycle = [
            {"type": "add_progress_comment", "target_status": None, "role": "developer",
             "optional": False, "context": "waiting_on_dependency"},
            {"type": "add_progress_comment", "target_status": None, "role": "developer",
             "optional": True, "context": "dependency_resolved"},
        ]

        # Complete normally
        post_dependency = self.generate_action_sequence("in progress", "done")

        return to_in_progress + dependency_cycle + post_dependency

    def get_disruption_actions(self, disruption_type: str) -> list[dict]:
        """
        Get action sequence for a disruption (to inject into existing script).

        Args:
            disruption_type: Type of disruption (blocker, rework)

        Returns:
            List of actions to inject into the script.
        """
        if disruption_type == "blocker":
            return [
                {"type": "inject_blocker", "target_status": None, "role": "developer", "optional": False},
                {"type": "discuss_blocker", "target_status": None, "role": "tech_lead", "optional": True},
                {"type": "resolve_blocker", "target_status": "In Progress", "role": "developer", "optional": False},
            ]
        elif disruption_type == "rework":
            return [
                {"type": "qa_reject", "target_status": "In Progress", "role": "qa", "optional": False},
                {"type": "acknowledge_rejection", "target_status": None, "role": "developer", "optional": False},
                {"type": "complete_fix", "target_status": "Code Review", "role": "developer", "optional": False},
            ]
        else:
            logger.warning(f"Unknown disruption type: {disruption_type}")
            return []

    def recalculate_remaining_script(
        self,
        current_status: str,
        target_status: str = "done",
    ) -> list[dict]:
        """
        Recalculate script from current position to target.

        Used when actual Jira state diverges from expected script state.
        """
        return self.generate_action_sequence(current_status, target_status)
