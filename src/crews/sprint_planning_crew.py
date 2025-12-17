"""
Sprint Planning Crew - handles sprint planning activities.

Manages:
1. PM plans sprint by allocating items to active sprint
2. PM creates future sprints when needed
3. PM adjusts sprint contents as needed
"""

from datetime import date, timedelta
from typing import Optional

from crewai import Task

from .base_crew import BaseCrew


class SprintPlanningCrew(BaseCrew):
    """
    Crew for sprint planning activities.

    PMs use this crew to:
    - Plan items for the current sprint (every Monday)
    - Create future sprints to maintain planning runway
    - Allocate backlog items based on team capacity
    """

    def plan_current_sprint(
        self,
        pm_id: str,
        team: str,
        active_sprint: dict,
        unassigned_items: list[dict],
    ) -> dict:
        """
        PM allocates items to the current sprint.

        Directly adds items to the sprint via Jira API (no LLM needed for this).

        Args:
            pm_id: The PM agent ID
            team: Team name (alpha/beta)
            active_sprint: Active sprint info dict
            unassigned_items: List of items not in any sprint

        Returns:
            Result dict with action details
        """
        if not unassigned_items:
            return {
                "action": "plan_current_sprint",
                "pm_id": pm_id,
                "result": "No unassigned items to plan",
                "items_added": 0,
            }

        persona = self.get_persona(pm_id)
        sprint_id = active_sprint.get("id")
        sprint_name = active_sprint.get("name", "Current Sprint")

        # Get available developers for assignment
        developers = self._get_available_developers()

        # Select items to add (prioritize bugs and high priority)
        items_to_add = self._select_items_for_sprint(unassigned_items, max_items=8)

        # Add items directly via Jira API and assign if unassigned
        added_keys = []
        dev_index = 0
        for item in items_to_add:
            success = self.jira_tools.jira.add_issue_to_sprint(sprint_id, [item["key"]])
            if success:
                added_keys.append(item["key"])
                # Assign if unassigned (sprint items must have assignees)
                if not item.get("assignee") and developers:
                    dev = developers[dev_index % len(developers)]
                    self.jira_tools.jira.assign_issue(item["key"], dev["account_id"])
                    dev_index += 1

        result = f"Added {len(added_keys)} items to {sprint_name}: {', '.join(added_keys)}"

        return {
            "action": "plan_current_sprint",
            "pm_id": pm_id,
            "pm_name": persona.get("display_name"),
            "team": team,
            "sprint_id": sprint_id,
            "sprint_name": sprint_name,
            "items_added": len(added_keys),
            "added_keys": added_keys,
            "result": result,
        }

    def _get_available_developers(self) -> list[dict]:
        """Get list of developers available for assignment."""
        developers = []
        for agent_id, config in self.personas.get("agents", {}).items():
            if config.get("role") == "developer":
                developers.append({
                    "agent_id": agent_id,
                    "account_id": config.get("jira_account_id"),
                    "name": config.get("display_name"),
                    "team": config.get("team"),
                })
        return developers

    def _select_items_for_sprint(
        self,
        items: list[dict],
        max_items: int = 8,
    ) -> list[dict]:
        """Select items for sprint based on priority and type."""
        # Sort: bugs first, then by priority
        priority_order = {"Highest": 0, "High": 1, "Medium": 2, "Low": 3, "Lowest": 4}

        def sort_key(item):
            is_bug = 0 if item.get("type") == "Bug" else 1
            priority = priority_order.get(item.get("priority", "Medium"), 2)
            return (is_bug, priority)

        sorted_items = sorted(items, key=sort_key)
        return sorted_items[:max_items]

    def create_future_sprint(
        self,
        pm_id: str,
        team: str,
        sprint_number: int,
        start_date: date,
    ) -> dict:
        """
        PM creates a future sprint.

        Args:
            pm_id: The PM agent ID
            team: Team name
            sprint_number: The sprint number to create
            start_date: When the sprint should start

        Returns:
            Result dict with created sprint info
        """
        persona = self.get_persona(pm_id)

        # Calculate end date (7-day sprint)
        end_date = start_date + timedelta(days=6)
        sprint_name = f"Sprint {sprint_number}"

        # Create sprint directly via Jira API
        sprint = self.jira_tools.jira.create_sprint(
            sprint_name, start_date=start_date, end_date=end_date
        )

        if sprint:
            result = f"Created sprint '{sprint['name']}' (ID: {sprint['id']})"
        else:
            result = "Failed to create sprint"

        return {
            "action": "create_future_sprint",
            "pm_id": pm_id,
            "pm_name": persona.get("display_name"),
            "sprint_name": sprint_name,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "result": result,
        }

    def allocate_items_to_future_sprint(
        self,
        pm_id: str,
        team: str,
        sprint_info: dict,
        backlog_items: list[dict],
    ) -> dict:
        """
        PM allocates items to a future sprint for roadmap planning.

        Args:
            pm_id: The PM agent ID
            team: Team name
            sprint_info: Future sprint info dict
            backlog_items: List of backlog items to consider

        Returns:
            Result dict with allocation details
        """
        if not backlog_items:
            return {
                "action": "allocate_to_future_sprint",
                "pm_id": pm_id,
                "result": "No backlog items to allocate",
            }

        persona = self.get_persona(pm_id)
        sprint_name = sprint_info.get("name", "Future Sprint")
        sprint_id = sprint_info.get("id")

        # Select items to add
        items_to_add = self._select_items_for_sprint(backlog_items, max_items=5)

        # Add items directly via Jira API
        added_keys = []
        for item in items_to_add:
            success = self.jira_tools.jira.add_issue_to_sprint(sprint_id, [item["key"]])
            if success:
                added_keys.append(item["key"])

        result = f"Added {len(added_keys)} items to {sprint_name}: {', '.join(added_keys)}"

        return {
            "action": "allocate_to_future_sprint",
            "pm_id": pm_id,
            "pm_name": persona.get("display_name"),
            "sprint_name": sprint_name,
            "items_added": len(added_keys),
            "added_keys": added_keys,
            "result": result,
        }

    def ensure_future_sprints_exist(
        self,
        pm_id: str,
        current_sprint_number: int,
        future_sprints: list[dict],
        target_count: int = 2,
    ) -> list[dict]:
        """
        Ensure we have enough future sprints planned.

        Args:
            pm_id: The PM agent ID
            current_sprint_number: Current sprint number
            future_sprints: List of existing future sprints
            target_count: How many future sprints to maintain

        Returns:
            List of results from creating any needed sprints
        """
        results = []
        existing_count = len(future_sprints)

        if existing_count >= target_count:
            return results

        # Calculate how many sprints to create
        sprints_needed = target_count - existing_count

        # Figure out the next sprint numbers and dates
        if future_sprints:
            # Get the last future sprint number
            last_sprint_name = future_sprints[-1].get("name", "")
            try:
                last_number = int(last_sprint_name.split()[-1])
            except (ValueError, IndexError):
                last_number = current_sprint_number + existing_count
            next_number = last_number + 1
            # Assume sprints start on Monday, 7 days after previous
            # For simplicity, start from next Monday
            start_date = self._next_monday(date.today())
            start_date += timedelta(weeks=existing_count)
        else:
            next_number = current_sprint_number + 1
            start_date = self._next_monday(date.today())

        for i in range(sprints_needed):
            sprint_start = start_date + timedelta(weeks=i)
            result = self.create_future_sprint(
                pm_id=pm_id,
                team="alpha",  # PMs can create for both teams
                sprint_number=next_number + i,
                start_date=sprint_start,
            )
            results.append(result)

        return results

    def _next_monday(self, from_date: date) -> date:
        """Get the next Monday from a given date."""
        days_ahead = 0 - from_date.weekday()  # Monday is 0
        if days_ahead <= 0:
            days_ahead += 7
        return from_date + timedelta(days=days_ahead)

    def start_sprint(
        self,
        pm_id: str,
        sprint_id: int,
        sprint_name: str,
    ) -> dict:
        """
        PM activates a future sprint to make it the current active sprint.

        Args:
            pm_id: The PM agent ID
            sprint_id: The ID of the future sprint to activate
            sprint_name: The name of the sprint

        Returns:
            Result dict with sprint activation details
        """
        persona = self.get_persona(pm_id)

        # Start sprint directly via Jira API
        start_date = date.today()
        end_date = start_date + timedelta(days=7)

        success = self.jira_tools.jira.start_sprint(
            sprint_id, start_date=start_date, end_date=end_date
        )

        result = f"Successfully activated {sprint_name}" if success else f"Failed to activate {sprint_name}"

        return {
            "action": "start_sprint",
            "success": success,
            "pm_id": pm_id,
            "pm_name": persona.get("display_name"),
            "sprint_id": sprint_id,
            "sprint_name": sprint_name,
            "result": result,
        }

    def complete_sprint(
        self,
        pm_id: str,
        sprint_id: int,
        sprint_name: str,
    ) -> dict:
        """
        PM completes the active sprint, closing it out.

        Args:
            pm_id: The PM agent ID
            sprint_id: The ID of the active sprint to complete
            sprint_name: The name of the sprint

        Returns:
            Result dict with sprint completion details
        """
        persona = self.get_persona(pm_id)

        # Complete sprint directly via Jira API
        success = self.jira_tools.jira.complete_sprint(sprint_id)

        result = f"Successfully completed {sprint_name}" if success else f"Failed to complete {sprint_name}"

        return {
            "action": "complete_sprint",
            "success": success,
            "pm_id": pm_id,
            "pm_name": persona.get("display_name"),
            "sprint_id": sprint_id,
            "sprint_name": sprint_name,
            "result": result,
        }
