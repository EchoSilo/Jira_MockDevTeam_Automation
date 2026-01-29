"""Integration tests for Phase 5 performance optimization components."""

import pytest
import pendulum
from unittest.mock import Mock, AsyncMock, patch

from src.orchestrator.async_executor import AsyncActionExecutor
from src.chaos.dynamic_tuner import DynamicChaosTuner
from src.monitoring.heartbeat import HeartbeatMonitor
from src.reconciliation.circuit_breaker import PerTicketCircuitBreaker


class TestPhase5Integration:
    """Integration tests for Phase 5 components working together."""

    def test_per_ticket_breaker_with_tick_execution(self):
        """Per-ticket circuit breaker integrates with TickExecutor pattern."""
        breaker = PerTicketCircuitBreaker(failure_threshold=3)

        # Simulate 3 failures for one ticket
        for _ in range(3):
            breaker.record_failure("ESCRUM-111", "status mismatch")

        # Action for ESCRUM-111 should be skipped
        assert not breaker.is_healthy("ESCRUM-111")

        # Action for ESCRUM-222 should proceed
        assert breaker.is_healthy("ESCRUM-222")

    def test_dynamic_tuner_adjusts_after_low_completion(self):
        """Dynamic tuner reduces chaos after poor sprint."""
        tuner = DynamicChaosTuner()

        # Simulate 3 poor sprints
        for _ in range(3):
            tuner.adjust(0.5)  # 50% completion

        # Chaos should be significantly reduced
        assert tuner.current_multiplier < 0.8

        # Apply to probabilities
        base = {"urgent_bug": 0.1}
        adjusted = tuner.get_adjusted_probabilities(base)
        assert adjusted["urgent_bug"] < 0.08  # Reduced from 0.1

    def test_heartbeat_tracks_ticks_correctly(self):
        """Heartbeat monitor tracks tick gaps."""
        monitor = HeartbeatMonitor(expected_interval_minutes=45)

        # First tick
        t1 = pendulum.parse("2026-01-28T10:00:00", tz="UTC")
        alert = monitor.record_tick(t1)
        assert alert is None

        # Normal tick
        t2 = t1.add(minutes=45)
        alert = monitor.record_tick(t2)
        assert alert is None

        # Late tick during business hours
        t3 = t2.add(minutes=90)  # 90 min gap > 67.5 threshold
        alert = monitor.record_tick(t3)
        assert alert is not None
        assert alert.gap_minutes == pytest.approx(90, abs=1)

    @pytest.mark.asyncio
    async def test_async_executor_timeout_enforcement(self):
        """Async executor enforces timeouts without cascade failures."""
        import asyncio

        executor = AsyncActionExecutor(
            max_action_time=0.5,  # 500ms per action
            max_total_time=2.0,   # 2s total
        )

        async def fast_action(action):
            await asyncio.sleep(0.1)
            return {"success": True, "action_id": action["action_id"]}

        async def slow_action(action):
            await asyncio.sleep(1.0)  # Will timeout at 500ms
            return {"success": True, "action_id": action["action_id"]}

        actions = [
            {"action_id": "fast-1"},
            {"action_id": "slow-1"},
            {"action_id": "fast-2"},
        ]

        async def router(action):
            if "slow" in action["action_id"]:
                return await slow_action(action)
            return await fast_action(action)

        successful, failed = await executor.execute_all(actions, router)

        # Fast actions should succeed
        assert len(successful) >= 2
        # Slow action should timeout
        assert len(failed) >= 1

    def test_all_components_can_be_instantiated(self):
        """All Phase 5 components can be created with defaults."""
        executor = AsyncActionExecutor()
        tuner = DynamicChaosTuner()
        monitor = HeartbeatMonitor()
        breaker = PerTicketCircuitBreaker()

        assert executor.max_action_time == 10.0
        assert executor.max_total_time == 45.0
        assert tuner.current_multiplier == 1.0
        assert monitor.expected_interval == 45
        assert breaker.failure_threshold == 3

    def test_settings_yaml_has_performance_section(self):
        """settings.yaml contains performance configuration."""
        import yaml

        with open("config/settings.yaml") as f:
            settings = yaml.safe_load(f)

        assert "performance" in settings
        assert "heartbeat" in settings["performance"]
        assert "chaos_tuning" in settings["performance"]
        assert "ticket_circuit_breaker" in settings["performance"]
