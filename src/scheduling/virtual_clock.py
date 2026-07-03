"""Virtual clock for simulation time advancement."""

from typing import Optional

import pendulum


class VirtualClock:
    """
    Virtual clock that tracks simulation time independent of wall-clock time.

    Enables controlled time advancement for testing and simulation scenarios
    where actions need to be scheduled based on simulated time rather than
    real-world time.

    Attributes:
        _simulation_time: Current simulation time
        tick_duration_hours: Default hours to advance per tick (default: 0.75 = 45 minutes)
    """

    def __init__(
        self,
        start_time: pendulum.DateTime,
        tick_duration_hours: float = 0.75,
    ):
        """
        Initialize virtual clock at specified start time.

        Args:
            start_time: Initial simulation time
            tick_duration_hours: Default hours to advance per tick (default: 0.75)
        """
        self._simulation_time = start_time
        self.tick_duration_hours = tick_duration_hours

    def now(self) -> pendulum.DateTime:
        """
        Get current simulation time.

        Returns:
            Current simulation time
        """
        return self._simulation_time

    def advance(self, hours: Optional[float] = None) -> pendulum.DateTime:
        """
        Advance simulation time by specified hours.

        Args:
            hours: Hours to advance (default: tick_duration_hours)

        Returns:
            New simulation time after advancement
        """
        hours_to_add = hours if hours is not None else self.tick_duration_hours
        self._simulation_time = self._simulation_time.add(hours=hours_to_add)
        return self._simulation_time

    def set_time(self, time: pendulum.DateTime) -> None:
        """
        Jump simulation time to specific datetime.

        Args:
            time: Time to set simulation clock to
        """
        self._simulation_time = time


class RealtimeClock(VirtualClock):
    """Clock that tracks REAL wall-clock time (real-time-paced simulation).

    The simulator is real-time paced: n8n triggers fire through the real workday and
    tickets advance on real elapsed time (e.g. the 24h in-progress minimum in
    src/state/models.py). Unlike the base VirtualClock, this clock does NOT compress
    time and is NOT artificially advanced per tick — real time advances on its own, so
    ``advance()``/``set_time()`` are no-ops. This keeps the scheduler's notion of "now"
    in agreement with the pacing gates, instead of racing ahead of them.

    Subclasses VirtualClock so it remains a drop-in wherever a VirtualClock is expected
    (Scheduler, and call sites that read ``tick_duration_hours``).
    """

    def __init__(self, tick_duration_hours: float = 0.75):
        # start_time is only a placeholder; now() ignores it and returns real time.
        super().__init__(pendulum.now("UTC"), tick_duration_hours=tick_duration_hours)

    def now(self) -> pendulum.DateTime:
        """Return the current REAL time in UTC."""
        return pendulum.now("UTC")

    def advance(self, hours: Optional[float] = None) -> pendulum.DateTime:
        """No-op: real time advances by itself. Returns the current real time.

        Neutralizes any ``advance_tick()`` calls (including the historical double
        advance) so time can never be compressed or jumped ahead of reality.
        """
        return pendulum.now("UTC")

    def set_time(self, time: pendulum.DateTime) -> None:
        """No-op: real time cannot be set. Kept for interface compatibility."""
        return None
