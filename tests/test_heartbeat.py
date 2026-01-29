"""Tests for heartbeat tick gap monitoring."""

import pytest
import pendulum
from src.monitoring.heartbeat import HeartbeatMonitor, HeartbeatAlert


class TestHeartbeatMonitor:
    """Tests for HeartbeatMonitor gap detection."""

    def test_first_tick_no_alert(self):
        """First tick initializes monitor without alert."""
        monitor = HeartbeatMonitor()
        now = pendulum.now("UTC")

        alert = monitor.record_tick(now)

        assert alert is None
        assert monitor.last_tick_time == now

    def test_normal_gap_no_alert(self):
        """Gap within threshold (45 min) produces no alert."""
        monitor = HeartbeatMonitor(expected_interval_minutes=45)

        # First tick
        first = pendulum.parse("2026-01-28T10:00:00", tz="UTC")
        monitor.record_tick(first)

        # Second tick 45 minutes later
        second = first.add(minutes=45)
        alert = monitor.record_tick(second)

        assert alert is None

    def test_gap_exceeds_threshold_logs_warning(self):
        """Gap exceeding 1.5x threshold (67.5 min) during business hours triggers alert."""
        monitor = HeartbeatMonitor(expected_interval_minutes=45, threshold_multiplier=1.5)

        # Tuesday 10am
        first = pendulum.parse("2026-01-28T10:00:00", tz="UTC")
        monitor.record_tick(first)

        # Same day, 2 hours later (during business hours)
        second = first.add(hours=2)  # 120 min > 67.5 min threshold
        alert = monitor.record_tick(second)

        assert alert is not None
        assert alert.alert_type == "heartbeat_gap"
        assert alert.gap_minutes == pytest.approx(120, abs=1)
        assert alert.expected_gap is False

    def test_weekend_gap_no_alert(self):
        """Gap spanning weekend is expected, no alert."""
        monitor = HeartbeatMonitor()

        # Friday 5pm
        friday = pendulum.parse("2026-01-24T17:00:00", tz="UTC")  # Friday
        monitor.record_tick(friday)

        # Monday 9am (64 hours later)
        monday = pendulum.parse("2026-01-27T09:00:00", tz="UTC")  # Monday
        alert = monitor.record_tick(monday)

        assert alert is None  # Expected gap, no alert

    def test_overnight_gap_no_alert(self):
        """Gap spanning overnight (after 5pm to before 9am) is expected."""
        monitor = HeartbeatMonitor(business_hours=(9, 17))

        # Tuesday 4:30pm (last tick before end of day)
        tuesday_pm = pendulum.parse("2026-01-28T16:30:00", tz="UTC")
        monitor.record_tick(tuesday_pm)

        # Wednesday 9am
        wednesday_am = pendulum.parse("2026-01-29T09:00:00", tz="UTC")
        alert = monitor.record_tick(wednesday_am)

        assert alert is None  # Expected overnight gap

    def test_after_hours_start_no_alert(self):
        """Gap starting after business hours is expected."""
        monitor = HeartbeatMonitor(business_hours=(9, 17))

        # Tuesday 6pm (after hours)
        after_hours = pendulum.parse("2026-01-28T18:00:00", tz="UTC")
        monitor.record_tick(after_hours)

        # Wednesday 10am (next business day)
        next_day = pendulum.parse("2026-01-29T10:00:00", tz="UTC")
        alert = monitor.record_tick(next_day)

        assert alert is None

    def test_threshold_configurable(self):
        """Threshold multiplier is configurable."""
        # Very tight threshold
        monitor = HeartbeatMonitor(
            expected_interval_minutes=45,
            threshold_multiplier=1.1  # Alert at 49.5 min
        )

        first = pendulum.parse("2026-01-28T10:00:00", tz="UTC")
        monitor.record_tick(first)

        # 50 minutes later (exceeds 49.5 threshold)
        second = first.add(minutes=50)
        alert = monitor.record_tick(second)

        assert alert is not None
        assert alert.gap_minutes == pytest.approx(50, abs=1)

    def test_reset_clears_state(self):
        """Reset clears last tick time."""
        monitor = HeartbeatMonitor()
        monitor.record_tick(pendulum.now("UTC"))

        monitor.reset()

        assert monitor.last_tick_time is None

    def test_get_status(self):
        """get_status returns configuration."""
        monitor = HeartbeatMonitor(
            expected_interval_minutes=45,
            threshold_multiplier=1.5,
            business_hours=(9, 17),
        )

        status = monitor.get_status()

        assert status["expected_interval_minutes"] == 45
        assert status["threshold_minutes"] == 67.5
        assert status["business_hours"] == (9, 17)

    def test_requirement_perf05_67_minute_alert(self):
        """PERF-05: Alert if tick gap exceeds 67 minutes (1.5x 45 min).

        From requirements:
        'Heartbeat monitoring logs warning if tick gap exceeds 67 minutes'
        """
        monitor = HeartbeatMonitor(
            expected_interval_minutes=45,
            threshold_multiplier=1.5
        )

        # Verify threshold is 67.5 minutes
        assert monitor.threshold_minutes == pytest.approx(67.5)

        # Wednesday 10am
        first = pendulum.parse("2026-01-29T10:00:00", tz="UTC")
        monitor.record_tick(first)

        # 70 minutes later (exceeds 67.5 min)
        second = first.add(minutes=70)
        alert = monitor.record_tick(second)

        assert alert is not None
        assert alert.gap_minutes == pytest.approx(70)
