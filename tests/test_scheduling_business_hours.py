"""Tests for BusinessHoursScheduler - TDD RED phase."""

import pytest
import pendulum


class TestBusinessHoursScheduler:
    """Test suite for business hours scheduling logic."""

    def setup_method(self):
        """Set up test fixtures."""
        # Import here to ensure it fails if not implemented
        from src.scheduling.business_hours import BusinessHoursScheduler

        self.scheduler = BusinessHoursScheduler()

    def test_is_business_day_monday(self):
        """Monday should be a business day."""
        monday = pendulum.datetime(2026, 1, 26, 10, 0, tz="America/New_York")  # Monday
        assert self.scheduler.is_business_day(monday) is True

    def test_is_business_day_tuesday(self):
        """Tuesday should be a business day."""
        tuesday = pendulum.datetime(2026, 1, 27, 10, 0, tz="America/New_York")
        assert self.scheduler.is_business_day(tuesday) is True

    def test_is_business_day_wednesday(self):
        """Wednesday should be a business day."""
        wednesday = pendulum.datetime(2026, 1, 28, 10, 0, tz="America/New_York")
        assert self.scheduler.is_business_day(wednesday) is True

    def test_is_business_day_thursday(self):
        """Thursday should be a business day."""
        thursday = pendulum.datetime(2026, 1, 29, 10, 0, tz="America/New_York")
        assert self.scheduler.is_business_day(thursday) is True

    def test_is_business_day_friday(self):
        """Friday should be a business day."""
        friday = pendulum.datetime(2026, 1, 30, 10, 0, tz="America/New_York")
        assert self.scheduler.is_business_day(friday) is True

    def test_is_business_day_saturday(self):
        """Saturday should NOT be a business day."""
        saturday = pendulum.datetime(2026, 1, 31, 10, 0, tz="America/New_York")
        assert self.scheduler.is_business_day(saturday) is False

    def test_is_business_day_sunday(self):
        """Sunday should NOT be a business day."""
        sunday = pendulum.datetime(2026, 2, 1, 10, 0, tz="America/New_York")
        assert self.scheduler.is_business_day(sunday) is False

    def test_is_business_hours_monday_10am(self):
        """Monday 10am should be business hours."""
        monday_10am = pendulum.datetime(2026, 1, 26, 10, 0, tz="America/New_York")
        assert self.scheduler.is_business_hours(monday_10am) is True

    def test_is_business_hours_monday_9am_exactly(self):
        """Monday 9am should be business hours (start boundary)."""
        monday_9am = pendulum.datetime(2026, 1, 26, 9, 0, tz="America/New_York")
        assert self.scheduler.is_business_hours(monday_9am) is True

    def test_is_business_hours_monday_4pm(self):
        """Monday 4pm should be business hours."""
        monday_4pm = pendulum.datetime(2026, 1, 26, 16, 0, tz="America/New_York")
        assert self.scheduler.is_business_hours(monday_4pm) is True

    def test_is_business_hours_monday_5pm_not_included(self):
        """Monday 5pm should NOT be business hours (end boundary exclusive)."""
        monday_5pm = pendulum.datetime(2026, 1, 26, 17, 0, tz="America/New_York")
        assert self.scheduler.is_business_hours(monday_5pm) is False

    def test_is_business_hours_monday_6pm(self):
        """Monday 6pm should NOT be business hours."""
        monday_6pm = pendulum.datetime(2026, 1, 26, 18, 0, tz="America/New_York")
        assert self.scheduler.is_business_hours(monday_6pm) is False

    def test_is_business_hours_monday_8am(self):
        """Monday 8am should NOT be business hours (before start)."""
        monday_8am = pendulum.datetime(2026, 1, 26, 8, 0, tz="America/New_York")
        assert self.scheduler.is_business_hours(monday_8am) is False

    def test_is_business_hours_saturday_10am(self):
        """Saturday 10am should NOT be business hours (not a business day)."""
        saturday_10am = pendulum.datetime(2026, 1, 31, 10, 0, tz="America/New_York")
        assert self.scheduler.is_business_hours(saturday_10am) is False

    def test_is_business_hours_sunday_10am(self):
        """Sunday 10am should NOT be business hours (not a business day)."""
        sunday_10am = pendulum.datetime(2026, 2, 1, 10, 0, tz="America/New_York")
        assert self.scheduler.is_business_hours(sunday_10am) is False

    def test_next_business_day_from_monday(self):
        """Next business day from Monday should be Tuesday 9am."""
        monday = pendulum.datetime(2026, 1, 26, 14, 0, tz="America/New_York")
        next_day = self.scheduler.next_business_day(monday)

        assert next_day.day_of_week == 1  # Tuesday
        assert next_day.hour == 9
        assert next_day.minute == 0

    def test_next_business_day_from_friday(self):
        """Next business day from Friday should be Monday 9am (skip weekend)."""
        friday = pendulum.datetime(2026, 1, 30, 14, 0, tz="America/New_York")
        next_day = self.scheduler.next_business_day(friday)

        assert next_day.day_of_week == 0  # Monday
        assert next_day.hour == 9
        assert next_day.minute == 0
        assert next_day.day == 2  # Feb 2

    def test_next_business_day_from_saturday(self):
        """Next business day from Saturday should be Monday 9am."""
        saturday = pendulum.datetime(2026, 1, 31, 14, 0, tz="America/New_York")
        next_day = self.scheduler.next_business_day(saturday)

        assert next_day.day_of_week == 0  # Monday
        assert next_day.hour == 9
        assert next_day.minute == 0
        assert next_day.day == 2  # Feb 2

    def test_next_business_day_from_sunday(self):
        """Next business day from Sunday should be Monday 9am."""
        sunday = pendulum.datetime(2026, 2, 1, 14, 0, tz="America/New_York")
        next_day = self.scheduler.next_business_day(sunday)

        assert next_day.day_of_week == 0  # Monday
        assert next_day.hour == 9
        assert next_day.minute == 0
        assert next_day.day == 2  # Feb 2

    def test_schedule_action_within_business_hours(self):
        """Scheduling within business hours should return target time."""
        monday_10am = pendulum.datetime(2026, 1, 26, 10, 0, tz="America/New_York")
        result = self.scheduler.schedule_action(monday_10am, hours_from_now=2)

        # Should be Monday 12pm
        assert result.day_of_week == 0  # Monday
        assert result.hour == 12
        assert result.day == 26

    def test_schedule_action_friday_4pm_plus_2_hours(self):
        """Friday 4pm + 2 hours should schedule for Monday 9am (not Saturday)."""
        friday_4pm = pendulum.datetime(2026, 1, 30, 16, 0, tz="America/New_York")
        result = self.scheduler.schedule_action(friday_4pm, hours_from_now=2)

        # Should be Monday 9am (Feb 2)
        assert result.day_of_week == 0  # Monday
        assert result.hour == 9
        assert result.minute == 0
        assert result.day == 2  # Feb 2

    def test_schedule_action_monday_6pm_zero_hours(self):
        """Monday 6pm (after hours) + 0 hours should schedule for Tuesday 9am."""
        monday_6pm = pendulum.datetime(2026, 1, 26, 18, 0, tz="America/New_York")
        result = self.scheduler.schedule_action(monday_6pm, hours_from_now=0)

        # Should be Tuesday 9am
        assert result.day_of_week == 1  # Tuesday
        assert result.hour == 9
        assert result.minute == 0
        assert result.day == 27

    def test_schedule_action_monday_8am_zero_hours(self):
        """Monday 8am (before hours) + 0 hours should schedule for Monday 9am."""
        monday_8am = pendulum.datetime(2026, 1, 26, 8, 0, tz="America/New_York")
        result = self.scheduler.schedule_action(monday_8am, hours_from_now=0)

        # Should be Monday 9am (same day)
        assert result.day_of_week == 0  # Monday
        assert result.hour == 9
        assert result.minute == 0
        assert result.day == 26

    def test_schedule_action_saturday_10am_zero_hours(self):
        """Saturday 10am + 0 hours should schedule for Monday 9am."""
        saturday_10am = pendulum.datetime(2026, 1, 31, 10, 0, tz="America/New_York")
        result = self.scheduler.schedule_action(saturday_10am, hours_from_now=0)

        # Should be Monday 9am
        assert result.day_of_week == 0  # Monday
        assert result.hour == 9
        assert result.minute == 0
        assert result.day == 2  # Feb 2

    def test_schedule_action_sunday_2pm_plus_1_hour(self):
        """Sunday 2pm + 1 hour should schedule for Monday 9am."""
        sunday_2pm = pendulum.datetime(2026, 2, 1, 14, 0, tz="America/New_York")
        result = self.scheduler.schedule_action(sunday_2pm, hours_from_now=1)

        # Should be Monday 9am
        assert result.day_of_week == 0  # Monday
        assert result.hour == 9
        assert result.minute == 0
        assert result.day == 2

    def test_schedule_action_crosses_business_hours_boundary(self):
        """Action that crosses end-of-day should move to next business day."""
        monday_4pm = pendulum.datetime(2026, 1, 26, 16, 0, tz="America/New_York")
        result = self.scheduler.schedule_action(monday_4pm, hours_from_now=2)

        # 4pm + 2h = 6pm (after hours), should be Tuesday 9am
        assert result.day_of_week == 1  # Tuesday
        assert result.hour == 9
        assert result.minute == 0
        assert result.day == 27

    def test_schedule_action_preserves_timezone(self):
        """Scheduled time should preserve original timezone."""
        monday_10am = pendulum.datetime(2026, 1, 26, 10, 0, tz="America/New_York")
        result = self.scheduler.schedule_action(monday_10am, hours_from_now=1)

        assert result.timezone_name == "America/New_York"

    def test_custom_work_hours(self):
        """Scheduler should respect custom work hours."""
        from src.scheduling.business_hours import BusinessHoursScheduler

        # 10am-4pm work hours
        scheduler = BusinessHoursScheduler(work_start_hour=10, work_end_hour=16)

        monday_9am = pendulum.datetime(2026, 1, 26, 9, 0, tz="America/New_York")
        assert scheduler.is_business_hours(monday_9am) is False

        monday_10am = pendulum.datetime(2026, 1, 26, 10, 0, tz="America/New_York")
        assert scheduler.is_business_hours(monday_10am) is True

        monday_4pm = pendulum.datetime(2026, 1, 26, 16, 0, tz="America/New_York")
        assert scheduler.is_business_hours(monday_4pm) is False
