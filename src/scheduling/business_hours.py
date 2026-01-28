"""Business hours scheduling for realistic Jira activity timing."""

import pendulum


class BusinessHoursScheduler:
    """
    Schedules actions to occur only during business hours (M-F, 9-5).

    Ensures that scheduled actions don't fall on weekends or outside work hours,
    creating realistic activity patterns for Jira analytics.

    Attributes:
        work_start_hour: Start of business hours (default: 9am)
        work_end_hour: End of business hours (default: 5pm, exclusive)
        timezone: Timezone for business hours (default: America/New_York)
    """

    def __init__(
        self,
        work_start_hour: int = 9,
        work_end_hour: int = 17,
        timezone: str = "America/New_York",
    ):
        """
        Initialize business hours scheduler.

        Args:
            work_start_hour: Hour when business day starts (0-23)
            work_end_hour: Hour when business day ends (0-23, exclusive)
            timezone: IANA timezone name
        """
        self.work_start_hour = work_start_hour
        self.work_end_hour = work_end_hour
        self.timezone = timezone

    def is_business_day(self, dt: pendulum.DateTime) -> bool:
        """
        Check if given datetime falls on a business day (Monday-Friday).

        Args:
            dt: DateTime to check

        Returns:
            True if Monday-Friday, False if Saturday-Sunday
        """
        # Pendulum day_of_week: 0=Monday, 1=Tuesday, ..., 4=Friday, 5=Saturday, 6=Sunday
        return dt.day_of_week < 5

    def is_business_hours(self, dt: pendulum.DateTime) -> bool:
        """
        Check if given datetime falls within business hours.

        Args:
            dt: DateTime to check

        Returns:
            True if on business day and between work_start_hour and work_end_hour
        """
        if not self.is_business_day(dt):
            return False

        # Convert to scheduler's timezone for hour comparison
        local_dt = dt.in_timezone(self.timezone)
        return self.work_start_hour <= local_dt.hour < self.work_end_hour

    def next_business_day(self, dt: pendulum.DateTime) -> pendulum.DateTime:
        """
        Get the start of the next business day.

        If currently Friday/Saturday/Sunday, returns Monday 9am.
        Otherwise returns next day at work_start_hour.

        Args:
            dt: Starting datetime

        Returns:
            DateTime set to next business day at work_start_hour
        """
        # Convert to scheduler's timezone
        local_dt = dt.in_timezone(self.timezone)

        # Add one day
        next_day = local_dt.add(days=1)

        # Skip weekend if needed
        # If next_day is Saturday (5), add 2 days to get Monday
        # If next_day is Sunday (6), add 1 day to get Monday
        while next_day.day_of_week >= 5:
            next_day = next_day.add(days=1)

        # Set to start of business hours
        result = next_day.set(hour=self.work_start_hour, minute=0, second=0, microsecond=0)

        # Convert back to original timezone
        return result.in_timezone(dt.timezone_name)

    def schedule_action(
        self, base_time: pendulum.DateTime, hours_from_now: float
    ) -> pendulum.DateTime:
        """
        Schedule an action from base_time, respecting business hours.

        Ensures the scheduled time falls on a business day during business hours.
        Weekend times are moved to Monday 9am.
        After-hours times are moved to next business day 9am.
        Before-hours times are moved to same day 9am.

        Args:
            base_time: Starting time for calculation
            hours_from_now: Hours to add (can be 0 for "now")

        Returns:
            DateTime adjusted to fall within business hours
        """
        # Calculate target time
        target_time = base_time.add(hours=hours_from_now)

        # Convert to scheduler's timezone for checks
        local_target = target_time.in_timezone(self.timezone)

        # Check 1: If not a business day, move to next business day
        if not self.is_business_day(local_target):
            return self.next_business_day(local_target)

        # Check 2: If before work hours, move to start of work hours same day
        if local_target.hour < self.work_start_hour:
            result = local_target.set(
                hour=self.work_start_hour, minute=0, second=0, microsecond=0
            )
            return result.in_timezone(target_time.timezone_name)

        # Check 3: If during or after work hours end, move to next business day
        if local_target.hour >= self.work_end_hour:
            return self.next_business_day(local_target)

        # Within business hours - return as-is
        return target_time
