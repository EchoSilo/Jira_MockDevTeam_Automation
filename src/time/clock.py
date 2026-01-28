"""Clock abstraction for dependency injection and testability.

This module provides a Clock protocol that enables time-dependent code to be
tested deterministically without monkeypatching or freezing global time.

Usage in production code:
    from src.time import RealClock

    clock = RealClock()
    now = clock.now()  # Returns current UTC time as pendulum.DateTime

Usage in tests:
    from src.time import FakeClock
    import pendulum

    clock = FakeClock(pendulum.datetime(2026, 1, 28, 10, 0, tz="UTC"))
    clock.advance(hours=2)
    now = clock.now()  # Returns 2026-01-28 12:00:00 UTC
"""
from typing import Protocol
import pendulum


class Clock(Protocol):
    """Protocol defining the interface for all clock implementations.

    All datetime values are timezone-aware UTC (pendulum.DateTime).
    """

    def now(self) -> pendulum.DateTime:
        """Return the current time in UTC.

        Returns:
            pendulum.DateTime: Current time with timezone=UTC
        """
        ...

    def today(self) -> pendulum.Date:
        """Return the current date in UTC.

        Returns:
            pendulum.Date: Current date in UTC timezone
        """
        ...


class RealClock:
    """Production clock that returns actual system time.

    All times are returned in UTC timezone.
    """

    def now(self) -> pendulum.DateTime:
        """Return the current system time in UTC.

        Returns:
            pendulum.DateTime: Current UTC time
        """
        return pendulum.now("UTC")

    def today(self) -> pendulum.Date:
        """Return the current date in UTC.

        Returns:
            pendulum.Date: Current date in UTC
        """
        return pendulum.now("UTC").date()


class FakeClock:
    """Test clock that returns a frozen time that can be advanced.

    This clock is designed for deterministic testing. Time does not advance
    automatically - it must be explicitly advanced with advance() or set with
    set_time().

    Example:
        clock = FakeClock(pendulum.datetime(2026, 1, 28, 10, 0, tz="UTC"))
        assert clock.now().hour == 10

        clock.advance(hours=2)
        assert clock.now().hour == 12

        clock.set_time(pendulum.datetime(2026, 2, 1, 9, 0, tz="UTC"))
        assert clock.now().day == 1
    """

    def __init__(self, frozen_time: pendulum.DateTime):
        """Initialize with a frozen time.

        Args:
            frozen_time: The time to freeze at (must be timezone-aware)
        """
        if frozen_time.timezone_name is None:
            raise ValueError("frozen_time must be timezone-aware")
        self._frozen_time = frozen_time

    def now(self) -> pendulum.DateTime:
        """Return the frozen time.

        Returns:
            pendulum.DateTime: The frozen time
        """
        return self._frozen_time

    def today(self) -> pendulum.Date:
        """Return the date portion of the frozen time.

        Returns:
            pendulum.Date: Date of the frozen time
        """
        return self._frozen_time.date()

    def advance(self, **kwargs) -> None:
        """Advance the frozen time by a delta.

        Args:
            **kwargs: Time delta arguments (e.g., hours=2, days=1, minutes=30)
                     Accepts any arguments valid for pendulum.duration()

        Example:
            clock.advance(hours=2)
            clock.advance(days=1, hours=3, minutes=15)
        """
        self._frozen_time = self._frozen_time.add(**kwargs)

    def set_time(self, new_time: pendulum.DateTime) -> None:
        """Jump to a specific time.

        Args:
            new_time: The new time to set (must be timezone-aware)

        Raises:
            ValueError: If new_time is not timezone-aware
        """
        if new_time.timezone_name is None:
            raise ValueError("new_time must be timezone-aware")
        self._frozen_time = new_time


def get_clock() -> RealClock:
    """Factory function for dependency injection.

    Returns:
        RealClock: A production clock instance

    This function can be used with FastAPI's Depends() for injecting
    the clock into route handlers and services.
    """
    return RealClock()
