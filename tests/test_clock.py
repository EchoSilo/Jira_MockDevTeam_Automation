"""Unit tests for Clock abstraction and implementations."""
import pendulum
import pytest
from src.time import RealClock, FakeClock


def test_real_clock_returns_utc():
    """RealClock.now() returns timezone-aware UTC datetime."""
    clock = RealClock()
    now = clock.now()

    assert isinstance(now, pendulum.DateTime)
    assert now.timezone_name == "UTC"


def test_real_clock_today_returns_date():
    """RealClock.today() returns a date object."""
    clock = RealClock()
    today = clock.today()

    assert isinstance(today, (pendulum.Date, pendulum.date))


def test_fake_clock_returns_frozen_time():
    """FakeClock.now() returns the exact frozen time provided."""
    frozen_time = pendulum.datetime(2026, 1, 28, 10, 0, 0, tz="UTC")
    clock = FakeClock(frozen_time)

    assert clock.now() == frozen_time
    assert clock.now().timezone_name == "UTC"


def test_fake_clock_advance():
    """FakeClock.advance() moves time forward by specified delta."""
    frozen_time = pendulum.datetime(2026, 1, 28, 10, 0, 0, tz="UTC")
    clock = FakeClock(frozen_time)

    # Advance 2 hours
    clock.advance(hours=2)
    expected_after_hours = pendulum.datetime(2026, 1, 28, 12, 0, 0, tz="UTC")
    assert clock.now() == expected_after_hours

    # Advance 1 day (total: 1 day + 2 hours from start)
    clock.advance(days=1)
    expected_after_days = pendulum.datetime(2026, 1, 29, 12, 0, 0, tz="UTC")
    assert clock.now() == expected_after_days


def test_fake_clock_set_time():
    """FakeClock.set_time() jumps to a completely different time."""
    initial_time = pendulum.datetime(2026, 1, 28, 10, 0, 0, tz="UTC")
    clock = FakeClock(initial_time)

    # Set to a different time
    new_time = pendulum.datetime(2026, 2, 15, 14, 30, 0, tz="UTC")
    clock.set_time(new_time)

    assert clock.now() == new_time


def test_fake_clock_today():
    """FakeClock.today() returns the date portion of frozen time."""
    frozen_time = pendulum.datetime(2026, 1, 28, 10, 0, 0, tz="UTC")
    clock = FakeClock(frozen_time)

    today = clock.today()
    assert today.year == 2026
    assert today.month == 1
    assert today.day == 28


def test_fake_clock_requires_timezone_aware():
    """FakeClock raises ValueError if given naive datetime."""
    naive_time = pendulum.datetime(2026, 1, 28, 10, 0, 0)
    # Remove timezone to make it naive
    naive_time = naive_time.naive()

    with pytest.raises(ValueError, match="must be timezone-aware"):
        FakeClock(naive_time)


def test_fake_clock_set_time_requires_timezone_aware():
    """FakeClock.set_time() raises ValueError if given naive datetime."""
    frozen_time = pendulum.datetime(2026, 1, 28, 10, 0, 0, tz="UTC")
    clock = FakeClock(frozen_time)

    naive_time = pendulum.datetime(2026, 2, 1, 9, 0, 0).naive()

    with pytest.raises(ValueError, match="must be timezone-aware"):
        clock.set_time(naive_time)
