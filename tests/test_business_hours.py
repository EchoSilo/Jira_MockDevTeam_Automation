"""Tests for business hours validation and sprint cadence."""
import pytest
import pendulum
from fastapi import HTTPException

from src.time import FakeClock, BusinessHoursConfig
from src.time.business_hours import validate_business_hours, reset_config_cache


class TestBusinessHoursValidation:
    """Test business hours enforcement."""

    def setup_method(self):
        """Reset config cache before each test."""
        reset_config_cache()

    def test_weekday_during_hours_passes(self):
        """Request on Tuesday at 10am should pass."""
        # Tuesday, January 28, 2026 at 10:00 AM EST
        clock = FakeClock(pendulum.datetime(2026, 1, 28, 15, 0, 0, tz="UTC"))  # 10am EST = 3pm UTC

        # Should not raise
        validate_business_hours(clock=clock)

    def test_weekday_before_hours_fails(self):
        """Request on Tuesday at 7am should fail."""
        # Tuesday at 7:00 AM EST = 12:00 UTC
        clock = FakeClock(pendulum.datetime(2026, 1, 28, 12, 0, 0, tz="UTC"))

        with pytest.raises(HTTPException) as exc_info:
            validate_business_hours(clock=clock)

        assert exc_info.value.status_code == 403
        assert "9:00-17:00" in exc_info.value.detail

    def test_weekday_after_hours_fails(self):
        """Request on Tuesday at 6pm should fail."""
        # Tuesday at 6:00 PM EST = 11:00 PM UTC
        clock = FakeClock(pendulum.datetime(2026, 1, 28, 23, 0, 0, tz="UTC"))

        with pytest.raises(HTTPException) as exc_info:
            validate_business_hours(clock=clock)

        assert exc_info.value.status_code == 403
        assert "9:00-17:00" in exc_info.value.detail

    def test_saturday_fails(self):
        """Request on Saturday should fail."""
        # Saturday, January 31, 2026 at 10:00 AM EST
        clock = FakeClock(pendulum.datetime(2026, 1, 31, 15, 0, 0, tz="UTC"))

        with pytest.raises(HTTPException) as exc_info:
            validate_business_hours(clock=clock)

        assert exc_info.value.status_code == 403
        assert "Saturday" in exc_info.value.detail

    def test_sunday_fails(self):
        """Request on Sunday should fail."""
        # Sunday, February 1, 2026 at 10:00 AM EST
        clock = FakeClock(pendulum.datetime(2026, 2, 1, 15, 0, 0, tz="UTC"))

        with pytest.raises(HTTPException) as exc_info:
            validate_business_hours(clock=clock)

        assert exc_info.value.status_code == 403
        assert "Sunday" in exc_info.value.detail

    def test_friday_afternoon_passes(self):
        """Request on Friday at 4pm should pass."""
        # Friday, January 30, 2026 at 4:00 PM EST = 9:00 PM UTC
        clock = FakeClock(pendulum.datetime(2026, 1, 30, 21, 0, 0, tz="UTC"))

        # Should not raise
        validate_business_hours(clock=clock)

    def test_friday_at_5pm_fails(self):
        """Request on Friday at exactly 5pm should fail (end_hour is exclusive)."""
        # Friday at 5:00 PM EST = 10:00 PM UTC
        clock = FakeClock(pendulum.datetime(2026, 1, 30, 22, 0, 0, tz="UTC"))

        with pytest.raises(HTTPException) as exc_info:
            validate_business_hours(clock=clock)

        assert exc_info.value.status_code == 403


class TestSprintCadence:
    """Test sprint date calculations with Pendulum."""

    def test_sprint_is_7_calendar_days(self):
        """Sprint from Wednesday to Tuesday is 7 calendar days."""
        # Wednesday, January 28, 2026
        start = pendulum.date(2026, 1, 28)
        assert start.day_of_week == pendulum.WEDNESDAY

        # Add 6 days to get to Tuesday (7 days total including start)
        end = start.add(days=6)
        assert end.day_of_week == pendulum.TUESDAY

        # Verify it's the expected date
        assert end == pendulum.date(2026, 2, 3)

    def test_sprint_day_calculation(self):
        """Sprint day should be 1-indexed from start date."""
        start = pendulum.datetime(2026, 1, 28, 0, 0, 0, tz="UTC")  # Wednesday

        # Day 1 (Wednesday)
        current = pendulum.datetime(2026, 1, 28, 10, 0, 0, tz="UTC")
        sprint_day = (current.date() - start.date()).days + 1
        assert sprint_day == 1

        # Day 7 (Tuesday)
        current = pendulum.datetime(2026, 2, 3, 10, 0, 0, tz="UTC")
        sprint_day = (current.date() - start.date()).days + 1
        assert sprint_day == 7

    def test_sprint_crosses_dst_correctly(self):
        """Sprint spanning DST transition should still be 7 calendar days."""
        # March 2026: DST starts Sunday March 8
        # Sprint Wed March 4 to Tue March 10
        start = pendulum.date(2026, 3, 4)
        assert start.day_of_week == pendulum.WEDNESDAY

        end = start.add(days=6)
        assert end.day_of_week == pendulum.TUESDAY
        assert end == pendulum.date(2026, 3, 10)

        # The DST transition happens on March 8 (Sunday)
        # But date arithmetic should still give us correct calendar days
        days_in_sprint = (end - start).days + 1
        assert days_in_sprint == 7


class TestBusinessHoursConfig:
    """Test BusinessHoursConfig dataclass."""

    def test_default_config(self):
        """Default config should be M-F 9-5."""
        config = BusinessHoursConfig()

        assert config.days == [1, 2, 3, 4, 5]
        assert config.start_hour == 9
        assert config.end_hour == 17
        assert config.timezone == "America/New_York"

    def test_custom_config(self):
        """Custom config should override defaults."""
        config = BusinessHoursConfig(
            timezone="America/Los_Angeles",
            days=[1, 2, 3, 4],  # M-Th
            start_hour=8,
            end_hour=18,
        )

        assert config.days == [1, 2, 3, 4]
        assert config.start_hour == 8
        assert config.end_hour == 18
        assert config.timezone == "America/Los_Angeles"
