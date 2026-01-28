"""Scenario scheduler that converts sprint scripts to calendar timestamps."""

import random
from typing import List, Optional

import pendulum

from src.scheduling.business_hours import BusinessHoursScheduler
from src.scheduling.models import ScheduledAction


class ScenarioScheduler:
    """
    Converts scenario scripts (day 1-7) to calendar timestamps.

    Sprint scenarios specify actions as "day 1", "day 3", etc. These must be
    converted to actual calendar timestamps respecting business hours and weekends.

    Attributes:
        business_hours: BusinessHoursScheduler for time validation
    """

    def __init__(self, business_hours: Optional[BusinessHoursScheduler] = None):
        """
        Initialize scenario scheduler.

        Args:
            business_hours: BusinessHoursScheduler instance (creates default if None)
        """
        self.business_hours = business_hours or BusinessHoursScheduler()

    def convert_scenario_to_actions(
        self,
        scenario_script: List[dict],
        sprint_start_date: pendulum.DateTime,
        ticket_key: str,
        scenario_id: str,
    ) -> List[ScheduledAction]:
        """
        Convert scenario script to scheduled actions with calendar timestamps.

        Takes script with relative day numbers (1-7) and converts to actual
        calendar timestamps, distributing actions throughout business hours
        and skipping weekends.

        Args:
            scenario_script: List of action dicts with "day" field (1-7)
            sprint_start_date: Starting date of sprint
            ticket_key: Jira ticket key (e.g., "PROJ-100")
            scenario_id: Unique scenario identifier

        Returns:
            List of ScheduledAction objects with calendar timestamps

        Example script action:
            {
                "day": 1,
                "type": "pick_up_task",
                "agent_id": "dev_alpha_1",
                "expected_status": "To Do",
                "params": {"priority": "high"}
            }
        """
        actions = []

        for script_action in scenario_script:
            day = script_action.get("day")
            if day is None:
                continue  # Skip actions without day field

            # Calculate base date from sprint start + (day - 1)
            base_date = sprint_start_date.add(days=day - 1)

            # Distribute time within business hours
            scheduled_time = self._distribute_time_within_day(base_date)

            # Create ScheduledAction
            action = ScheduledAction(
                scheduled_time=scheduled_time,
                action_type=script_action.get("type", ""),
                agent_id=script_action.get("agent_id", ""),
                ticket_key=ticket_key,
                scenario_id=scenario_id,
                expected_status=script_action.get("expected_status"),
                expected_assignee=script_action.get("expected_assignee"),
                params=script_action.get("params", {}),
            )

            actions.append(action)

        return actions

    def _distribute_time_within_day(self, base_date: pendulum.DateTime) -> pendulum.DateTime:
        """
        Distribute action time randomly within business hours.

        If base_date is weekend, moves to Monday first. Then adds random
        offset within the workday (9am-5pm).

        Args:
            base_date: Base date to schedule from

        Returns:
            DateTime adjusted to fall within business hours on same working day
        """
        # First, ensure we're on a business day (move weekend to Monday)
        working_date = base_date
        if not self.business_hours.is_business_day(base_date):
            working_date = self.business_hours.next_business_day(base_date)

        # Convert to scheduler's timezone
        local_date = working_date.in_timezone(self.business_hours.timezone)

        # Random hour within workday (9-17, so 0-8 hour offset from start)
        random_hours = random.uniform(0, 7.99)  # Stay within 8-hour window

        # Random minutes for realistic timestamps
        random_minutes = random.randint(0, 59)

        # Set to start of business hours + random offset
        result = local_date.set(
            hour=self.business_hours.work_start_hour,
            minute=0,
            second=0,
            microsecond=0
        ).add(hours=random_hours, minutes=random_minutes)

        # Convert back to original timezone
        return result.in_timezone(base_date.timezone_name)
