"""Heartbeat monitor for tick gap detection.

Detects when tick gaps exceed expected intervals, accounting for
business hours (M-F 9-5) and weekend gaps.
"""

import logging
from typing import Optional
from dataclasses import dataclass

import pendulum

logger = logging.getLogger(__name__)


@dataclass
class HeartbeatAlert:
    """Alert for unexpected tick gap."""
    alert_type: str  # "heartbeat_gap"
    gap_minutes: float
    threshold_minutes: float
    last_tick: str  # ISO format
    current_tick: str  # ISO format
    expected_gap: bool  # True if gap was during off-hours/weekend


class HeartbeatMonitor:
    """Monitor tick intervals and alert on unexpected gaps.

    Expected interval is 45 minutes (n8n trigger schedule).
    Alert threshold is 1.5x expected = 67.5 minutes.

    Business hours: M-F 9am-5pm (configurable).
    Weekend and off-hours gaps are logged but don't trigger alerts.
    """

    def __init__(
        self,
        expected_interval_minutes: int = 45,
        threshold_multiplier: float = 1.5,
        business_hours: tuple[int, int] = (9, 17),
        business_days: tuple[int, ...] = (1, 2, 3, 4, 5),  # Mon-Fri (pendulum uses 1=Mon)
    ):
        self.expected_interval = expected_interval_minutes
        self.threshold_multiplier = threshold_multiplier
        self.business_hours = business_hours
        self.business_days = business_days
        self.last_tick_time: Optional[pendulum.DateTime] = None

    @property
    def threshold_minutes(self) -> float:
        """Alert threshold in minutes."""
        return self.expected_interval * self.threshold_multiplier

    def record_tick(self, current_time: pendulum.DateTime) -> Optional[HeartbeatAlert]:
        """Record tick and check for anomalous gaps.

        Args:
            current_time: Current tick timestamp (timezone-aware)

        Returns:
            HeartbeatAlert if gap exceeded threshold during business hours,
            None otherwise.
        """
        if self.last_tick_time is None:
            self.last_tick_time = current_time
            logger.debug(f"Heartbeat initialized: first tick at {current_time}")
            return None

        # Calculate gap
        gap = current_time - self.last_tick_time
        gap_minutes = gap.total_seconds() / 60

        alert = None

        if gap_minutes > self.threshold_minutes:
            # Check if gap is expected (crosses off-hours or weekend)
            is_expected = self._is_expected_gap(self.last_tick_time, current_time)

            if is_expected:
                logger.info(
                    f"Expected gap (off-hours/weekend): {gap_minutes:.1f} min "
                    f"from {self.last_tick_time.format('YYYY-MM-DD HH:mm')} "
                    f"to {current_time.format('YYYY-MM-DD HH:mm')}"
                )
            else:
                # Unexpected gap during business hours - this is concerning
                logger.warning(
                    f"HEARTBEAT ALERT: Tick gap {gap_minutes:.1f} min exceeds "
                    f"threshold {self.threshold_minutes:.1f} min. "
                    f"Last tick: {self.last_tick_time.format('YYYY-MM-DD HH:mm')}, "
                    f"Current: {current_time.format('YYYY-MM-DD HH:mm')}"
                )

                alert = HeartbeatAlert(
                    alert_type="heartbeat_gap",
                    gap_minutes=gap_minutes,
                    threshold_minutes=self.threshold_minutes,
                    last_tick=self.last_tick_time.isoformat(),
                    current_tick=current_time.isoformat(),
                    expected_gap=False,
                )
        else:
            logger.debug(f"Heartbeat OK: {gap_minutes:.1f} min gap")

        self.last_tick_time = current_time
        return alert

    def _is_expected_gap(
        self,
        start: pendulum.DateTime,
        end: pendulum.DateTime,
    ) -> bool:
        """Check if gap is expected (crosses off-hours or weekend).

        A gap is expected if:
        1. Start or end is on a weekend day
        2. Start is after end of business hours
        3. End is before start of business hours
        4. Gap spans different days and crosses end-of-day
        """
        start_hour, end_hour = self.business_hours

        # Check weekend
        if start.day_of_week not in self.business_days:
            return True
        if end.day_of_week not in self.business_days:
            return True

        # Check if start was after business hours
        if start.hour >= end_hour:
            return True

        # Check if end is before business hours
        if end.hour < start_hour:
            return True

        # Check if spans different days (overnight)
        if start.date() != end.date():
            return True

        return False

    def reset(self) -> None:
        """Reset last tick time (useful for testing)."""
        self.last_tick_time = None

    def get_status(self) -> dict:
        """Get current monitor status."""
        return {
            "last_tick": self.last_tick_time.isoformat() if self.last_tick_time else None,
            "expected_interval_minutes": self.expected_interval,
            "threshold_minutes": self.threshold_minutes,
            "business_hours": self.business_hours,
            "business_days": self.business_days,
        }
