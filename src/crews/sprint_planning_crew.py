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
        agent = self.get_agent(pm_id, use_complex_llm=True)

        # Format items for the prompt
        items_summary = "\n".join([
            f"- {item['key']}: {item['summary']} [{item['type']}] "
            f"Priority: {item.get('priority', 'Medium')}"
            for item in unassigned_items[:15]
        ])

        sprint_name = active_sprint.get("name", "Current Sprint")
        sprint_id = active_sprint.get("id")

        task = Task(
            description=f"""You are {persona['display_name']} (PM) planning the sprint for Team {team.title()}.

## Sprint: {sprint_name} (ID: {sprint_id})

## Unassigned Items Available:
{items_summary}

## Your Task:
1. Review these items and select 5-8 items appropriate for this sprint
2. Consider team capacity (2 developers) and typical velocity
3. Use 'Add Issue to Sprint' tool to assign selected items to sprint {sprint_id}
4. Add a brief planning comment on the first item you add

## Guidelines:
- Prioritize bugs and high-priority stories first
- Balance complexity across the sprint
- Don't overcommit - leave buffer for unknowns
- Select items that can realistically be completed in one week

Your communication style: {persona.get('persona', '')}
""",
            expected_output=(
                "Confirmation of items added to sprint with brief planning rationale"
            ),
            agent=agent,
        )

        result = self.execute_crew([agent], [task])

        return {
            "action": "plan_current_sprint",
            "pm_id": pm_id,
            "pm_name": persona.get("display_name"),
            "team": team,
            "sprint_id": sprint_id,
            "sprint_name": sprint_name,
            "result": result,
        }

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
        agent = self.get_agent(pm_id, use_complex_llm=False)

        # Calculate end date (7-day sprint)
        end_date = start_date + timedelta(days=6)
        sprint_name = f"Sprint {sprint_number}"

        task = Task(
            description=f"""You are {persona['display_name']} (PM) creating a future sprint.

## Create Sprint:
- Name: {sprint_name}
- Start Date: {start_date.isoformat()}
- End Date: {end_date.isoformat()}

Use the 'Create Sprint' tool to create this sprint.
""",
            expected_output="Confirmation of sprint creation with sprint ID",
            agent=agent,
        )

        result = self.execute_crew([agent], [task])

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
        agent = self.get_agent(pm_id, use_complex_llm=True)

        items_summary = "\n".join([
            f"- {item['key']}: {item['summary']} [{item['type']}] "
            f"Priority: {item.get('priority', 'Medium')}"
            for item in backlog_items[:20]
        ])

        sprint_name = sprint_info.get("name", "Future Sprint")
        sprint_id = sprint_info.get("id")

        task = Task(
            description=f"""You are {persona['display_name']} (PM) doing roadmap planning.

## Planning for: {sprint_name} (ID: {sprint_id})

## Backlog Items:
{items_summary}

## Your Task:
1. Review items and select 3-5 items for this future sprint
2. Consider dependencies and logical sequencing
3. Use 'Add Issue to Sprint' tool to assign items to sprint {sprint_id}

Focus on items that:
- Have clear requirements
- Align with the roadmap
- Don't have blocking dependencies
""",
            expected_output="Confirmation of items allocated to future sprint",
            agent=agent,
        )

        result = self.execute_crew([agent], [task])

        return {
            "action": "allocate_to_future_sprint",
            "pm_id": pm_id,
            "pm_name": persona.get("display_name"),
            "sprint_name": sprint_name,
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
