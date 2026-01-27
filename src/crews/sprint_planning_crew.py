"""
Sprint Planning Crew - handles sprint planning activities.

Manages:
1. PM plans sprint by allocating items to active sprint
2. PM creates future sprints when needed
3. PM adjusts sprint contents as needed
4. Generates sprint scenarios for simulation guidance
"""

import logging
from datetime import date, timedelta
from typing import Any, Optional

from crewai import Task

from src.scenarios import ScenarioPlanner, SprintScenario
from src.state.models import SimulationState
from .base_crew import BaseCrew

logger = logging.getLogger(__name__)


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
        """Select items for sprint based on priority and type.

        Filters out Epics - only Stories, Bugs, and Tasks belong in sprints.
        """
        # Filter out Epics first - they should never be in sprints
        non_epic_items = [item for item in items if item.get("type") != "Epic"]
        if len(non_epic_items) < len(items):
            filtered_count = len(items) - len(non_epic_items)
            logger.warning(f"Filtered {filtered_count} Epics from sprint planning")

        # Sort: bugs first, then by priority
        priority_order = {"Highest": 0, "High": 1, "Medium": 2, "Low": 3, "Lowest": 4}

        def sort_key(item):
            is_bug = 0 if item.get("type") == "Bug" else 1
            priority = priority_order.get(item.get("priority", "Medium"), 2)
            return (is_bug, priority)

        sorted_items = sorted(non_epic_items, key=sort_key)
        return sorted_items[:max_items]

    def create_future_sprint(
        self,
        pm_id: str,
        team: str,
        sprint_number: int,
        start_date: date,
        current_date: Optional[date] = None,
    ) -> dict:
        """
        PM creates a future sprint.

        Args:
            pm_id: The PM agent ID
            team: Team name
            sprint_number: The sprint number to create
            start_date: When the sprint should start
            current_date: Current simulation date (defaults to today)

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
        current_date: Optional[date] = None,
    ) -> list[dict]:
        """
        Ensure we have enough future sprints planned.

        Args:
            pm_id: The PM agent ID
            current_sprint_number: Current sprint number
            future_sprints: List of existing future sprints
            target_count: How many future sprints to maintain
            current_date: Current simulation date (defaults to today)

        Returns:
            List of results from creating any needed sprints
        """
        today = current_date or date.today()
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
            start_date = self._next_monday(today)
            start_date += timedelta(weeks=existing_count)
        else:
            next_number = current_sprint_number + 1
            start_date = self._next_monday(today)

        for i in range(sprints_needed):
            sprint_start = start_date + timedelta(weeks=i)
            result = self.create_future_sprint(
                pm_id=pm_id,
                team="alpha",  # PMs can create for both teams
                sprint_number=next_number + i,
                start_date=sprint_start,
                current_date=today,
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
        current_date: Optional[date] = None,
    ) -> dict:
        """
        PM activates a future sprint to make it the current active sprint.

        Args:
            pm_id: The PM agent ID
            sprint_id: The ID of the future sprint to activate
            sprint_name: The name of the sprint
            current_date: Current simulation date (defaults to today)

        Returns:
            Result dict with sprint activation details
        """
        persona = self.get_persona(pm_id)
        base_date = current_date or date.today()

        # Sprint should start on Monday and end on Sunday (2 weeks)
        # Find the next Monday if today isn't Monday
        if base_date.weekday() == 0:  # Already Monday
            start_date = base_date
        else:
            start_date = self._next_monday(base_date)

        # Sprint is 2 weeks: start Monday, end Sunday (14 days - 1 = 13 days later)
        end_date = start_date + timedelta(days=13)

        success, error = self.jira_tools.jira.start_sprint(
            sprint_id, start_date=start_date, end_date=end_date
        )

        if success:
            result = f"Successfully activated {sprint_name}"
        else:
            result = f"Failed to activate {sprint_name}: {error}"

        return {
            "action": "start_sprint",
            "success": success,
            "pm_id": pm_id,
            "pm_name": persona.get("display_name"),
            "sprint_id": sprint_id,
            "sprint_name": sprint_name,
            "result": result,
        }

    def _transition_done_to_closed(self, sprint_id: int) -> int:
        """Transition all Done items in sprint to Closed before completing.

        This ensures that items in "Done" status are properly closed before
        the sprint ends, so they don't get incorrectly identified as incomplete.

        Args:
            sprint_id: The sprint ID to check for Done items

        Returns:
            Count of items successfully transitioned to Closed
        """
        closed_count = 0
        jira = self.jira_tools.jira

        try:
            # Get Done items in the sprint (excluding Epics)
            done_issues = jira._client.search_issues(
                f"project = {jira.project_key} AND sprint = {sprint_id} "
                f"AND status = Done AND issuetype != Epic",
                maxResults=200
            )

            for issue in done_issues:
                try:
                    success = jira.transition_issue(issue.key, "Closed")
                    if success:
                        closed_count += 1
                        logger.debug(f"Transitioned {issue.key} from Done to Closed")
                    else:
                        # Try alternate terminal status names
                        for alt_status in ["Close", "Close Issue", "Resolve"]:
                            success = jira.transition_issue(issue.key, alt_status)
                            if success:
                                closed_count += 1
                                logger.debug(
                                    f"Transitioned {issue.key} to {alt_status}"
                                )
                                break
                except Exception as e:
                    logger.warning(f"Failed to close {issue.key}: {e}")

            if closed_count > 0:
                logger.info(
                    f"Transitioned {closed_count} Done items to Closed "
                    f"before sprint completion"
                )
        except Exception as e:
            logger.warning(f"Error transitioning Done items to Closed: {e}")

        return closed_count

    def complete_sprint(
        self,
        pm_id: str,
        sprint_id: int,
        sprint_name: str,
        next_sprint_id: Optional[int] = None,
    ) -> dict:
        """
        PM completes the active sprint, closing it out.

        Transitions Done items to Closed before completing to ensure
        they are properly finalized.

        Args:
            pm_id: The PM agent ID
            sprint_id: The ID of the active sprint to complete
            sprint_name: The name of the sprint
            next_sprint_id: Optional sprint ID to move incomplete issues to

        Returns:
            Result dict with sprint completion details
        """
        persona = self.get_persona(pm_id)

        # Transition Done items to Closed before completing sprint
        closed_count = self._transition_done_to_closed(sprint_id)

        # Complete sprint directly via Jira API
        success, error = self.jira_tools.jira.complete_sprint(
            sprint_id, move_incomplete_to=next_sprint_id
        )

        if success:
            result = f"Successfully completed {sprint_name}"
            if closed_count > 0:
                result += f" (transitioned {closed_count} items to Closed)"
            if next_sprint_id:
                result += f" (incomplete issues moved to sprint {next_sprint_id})"
        else:
            result = f"Failed to complete {sprint_name}: {error}"

        return {
            "action": "complete_sprint",
            "success": success,
            "pm_id": pm_id,
            "pm_name": persona.get("display_name"),
            "sprint_id": sprint_id,
            "sprint_name": sprint_name,
            "next_sprint_id": next_sprint_id,
            "items_closed": closed_count,
            "result": result,
        }

    def rollover_sprint(
        self,
        pm_id: str,
        current_sprint_id: int,
        current_sprint_name: str,
        new_sprint_name: Optional[str] = None,
        current_date: Optional[date] = None,
    ) -> dict:
        """
        Complete the current sprint and start a new one, rolling over incomplete issues.

        This method:
        1. Checks for existing future sprint matching the name, or creates one
        2. Closes the current sprint, moving incomplete issues to the new sprint
        3. Starts the new sprint

        Sprint constraints:
        - Sprints are 2 weeks long (14 days)
        - Sprints start on Monday and end on Sunday
        - Next sprint starts the day after the previous sprint ends

        Args:
            pm_id: The PM agent ID performing the rollover
            current_sprint_id: The ID of the sprint to close
            current_sprint_name: The name of the sprint to close
            new_sprint_name: Optional name for new sprint (creates one if provided)
            current_date: Current simulation date (defaults to today)

        Returns:
            Result dict with rollover details
        """
        persona = self.get_persona(pm_id)
        base_date = current_date or date.today()

        # Calculate sprint dates: start on next Monday, end on Sunday (2 weeks)
        # Find the next Monday from base_date
        days_until_monday = (7 - base_date.weekday()) % 7
        if days_until_monday == 0 and base_date.weekday() != 0:
            days_until_monday = 7  # If today isn't Monday, find next Monday
        start_date = base_date + timedelta(days=days_until_monday)

        # Sprint is 2 weeks: start Monday, end Sunday (14 days - 1 = 13 days later)
        end_date = start_date + timedelta(days=13)  # Monday + 13 days = Sunday

        # Step 1: Check for existing future sprint before creating
        future_sprints = self.jira_tools.jira.get_future_sprints(max_results=4)
        next_sprint_id = None

        # Check if a sprint with matching name already exists
        if new_sprint_name:
            for fs in future_sprints:
                if fs["name"] == new_sprint_name:
                    logger.info(f"Using existing future sprint: {new_sprint_name} (ID: {fs['id']})")
                    next_sprint_id = fs["id"]
                    break

        # If no matching sprint found, create a new one
        if next_sprint_id is None:
            if new_sprint_name:
                new_sprint = self.jira_tools.jira.create_sprint(
                    name=new_sprint_name,
                    start_date=start_date,
                    end_date=end_date,
                )
                if not new_sprint:
                    return {
                        "action": "rollover_sprint",
                        "success": False,
                        "pm_id": pm_id,
                        "pm_name": persona.get("display_name"),
                        "result": f"Failed to create new sprint '{new_sprint_name}'",
                    }
                next_sprint_id = new_sprint["id"]
                logger.info(f"Created new sprint: {new_sprint_name} (ID: {next_sprint_id})")
            elif future_sprints:
                # Use first available future sprint
                next_sprint_id = future_sprints[0]["id"]
                new_sprint_name = future_sprints[0]["name"]
                logger.info(f"Using first future sprint: {new_sprint_name} (ID: {next_sprint_id})")
            else:
                return {
                    "action": "rollover_sprint",
                    "success": False,
                    "pm_id": pm_id,
                    "pm_name": persona.get("display_name"),
                    "result": "No future sprint available and no name provided to create one",
                }

        # Step 2: Close current sprint, moving incomplete issues to next sprint
        close_success, close_error = self.jira_tools.jira.complete_sprint(
            current_sprint_id, move_incomplete_to=next_sprint_id
        )
        if not close_success:
            return {
                "action": "rollover_sprint",
                "success": False,
                "pm_id": pm_id,
                "pm_name": persona.get("display_name"),
                "result": f"Failed to close sprint: {close_error}",
            }

        # Step 3: Start the new sprint with proper 2-week duration
        start_success, start_error = self.jira_tools.jira.start_sprint(
            next_sprint_id, start_date=start_date, end_date=end_date
        )
        if not start_success:
            return {
                "action": "rollover_sprint",
                "success": False,
                "pm_id": pm_id,
                "pm_name": persona.get("display_name"),
                "result": f"Sprint closed but failed to start new sprint: {start_error}",
            }

        logger.info(
            f"Sprint rollover complete: '{current_sprint_name}' -> '{new_sprint_name}'"
        )

        return {
            "action": "rollover_sprint",
            "success": True,
            "pm_id": pm_id,
            "pm_name": persona.get("display_name"),
            "closed_sprint_id": current_sprint_id,
            "closed_sprint_name": current_sprint_name,
            "new_sprint_id": next_sprint_id,
            "new_sprint_name": new_sprint_name,
            "result": f"Rolled over from '{current_sprint_name}' to '{new_sprint_name}'",
        }

    # ========== Sprint Scenario Generation ==========

    def generate_sprint_scenario(
        self,
        sprint_id: int,
        sprint_name: str,
        sprint_items: list[dict[str, Any]],
        state: SimulationState,
        release_context: Optional[str] = None,
    ) -> SprintScenario:
        """
        Generate a sprint scenario for the upcoming sprint.

        This creates a narrative arc that will guide the simulation,
        determining what events happen on which days.

        Args:
            sprint_id: The sprint ID/number
            sprint_name: The sprint name
            sprint_items: List of tickets in the sprint
            state: Current simulation state (for previous sprint context)
            release_context: Optional release info (e.g., "Sprint before v1.2.0")

        Returns:
            SprintScenario with day-by-day script
        """
        planner = ScenarioPlanner()

        # Calculate team capacity (developers * points per sprint)
        developers = self._get_available_developers()
        points_per_dev = 10  # Assume ~10 points per dev per sprint
        team_capacity = len(developers) * points_per_dev

        # Get previous sprint completion rate from state
        previous_completion = None
        if state.completed_sprint_scenarios:
            # Could look up previous scenario completion rate here
            pass

        # Generate the scenario (2-week sprints = 14 days)
        scenario = planner.plan_scenario(
            sprint_id=sprint_id,
            sprint_name=sprint_name,
            sprint_items=sprint_items,
            team_capacity=team_capacity,
            release_context=release_context,
            previous_sprint_completion=previous_completion,
            sprint_duration_days=14,
        )

        logger.info(
            f"Generated sprint scenario: {scenario.archetype.value} "
            f"for {sprint_name} with {len(sprint_items)} items, "
            f"target completion: {scenario.target_completion_rate:.0%}"
        )

        return scenario

    def plan_sprint_with_scenario(
        self,
        pm_id: str,
        team: str,
        active_sprint: dict,
        unassigned_items: list[dict],
        state: SimulationState,
        release_context: Optional[str] = None,
    ) -> dict:
        """
        Plan sprint AND generate scenario in one operation.

        This is the main entry point for sprint planning that also
        sets up the sprint scenario for simulation guidance.

        Args:
            pm_id: The PM agent ID
            team: Team name (alpha/beta)
            active_sprint: Active sprint info dict
            unassigned_items: List of items not in any sprint
            state: Current simulation state
            release_context: Optional release info

        Returns:
            Result dict including both planning result and scenario info
        """
        # First, do the regular sprint planning
        planning_result = self.plan_current_sprint(
            pm_id=pm_id,
            team=team,
            active_sprint=active_sprint,
            unassigned_items=unassigned_items,
        )

        # Get items now in the sprint (including newly added)
        sprint_id = active_sprint.get("id")
        sprint_name = active_sprint.get("name", "Current Sprint")

        # Fetch current sprint items from Jira
        sprint_items = self.jira_tools.jira.get_sprint_issues(sprint_id) or []

        # Convert to the format expected by scenario planner
        # Note: get_sprint_issues returns Jira Issue objects, not dicts
        items_for_scenario = []
        for item in sprint_items:
            # Handle Jira Issue objects (have .key attribute)
            if hasattr(item, 'key'):
                items_for_scenario.append({
                    "key": item.key,
                    "type": getattr(item.fields.issuetype, 'name', 'Story') if hasattr(item.fields, 'issuetype') else 'Story',
                    "priority": getattr(item.fields.priority, 'name', 'Medium') if hasattr(item.fields, 'priority') and item.fields.priority else 'Medium',
                    "story_points": getattr(item.fields, 'customfield_10016', 0) or 0,
                    "summary": getattr(item.fields, 'summary', ''),
                    "assignee": getattr(item.fields.assignee, 'accountId', None) if hasattr(item.fields, 'assignee') and item.fields.assignee else None,
                })
            else:
                # Handle dict format
                items_for_scenario.append({
                    "key": item.get("key"),
                    "type": item.get("fields", {}).get("issuetype", {}).get("name", "Story"),
                    "priority": item.get("fields", {}).get("priority", {}).get("name", "Medium"),
                    "story_points": item.get("fields", {}).get("customfield_10016", 0),
                    "summary": item.get("fields", {}).get("summary", ""),
                    "assignee": item.get("fields", {}).get("assignee", {}).get("accountId") if item.get("fields", {}).get("assignee") else None,
                })

        # Generate scenario if we have items
        scenario = None
        if items_for_scenario:
            try:
                # Extract sprint number from name
                try:
                    sprint_number = int(sprint_name.split()[-1])
                except (ValueError, IndexError):
                    sprint_number = sprint_id

                scenario = self.generate_sprint_scenario(
                    sprint_id=sprint_number,
                    sprint_name=sprint_name,
                    sprint_items=items_for_scenario,
                    state=state,
                    release_context=release_context,
                )

                # Store scenario in state
                state.set_sprint_scenario(scenario)
                scenario.start()  # Mark as started

                planning_result["scenario_generated"] = True
                planning_result["scenario_id"] = scenario.scenario_id
                planning_result["scenario_archetype"] = scenario.archetype.value
                planning_result["scenario_target_completion"] = scenario.target_completion_rate

            except Exception as e:
                logger.error(f"Failed to generate sprint scenario: {e}")
                planning_result["scenario_generated"] = False
                planning_result["scenario_error"] = str(e)

        return planning_result
