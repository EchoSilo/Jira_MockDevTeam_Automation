"""Integration tests for chaos injection flow."""

from unittest.mock import MagicMock

import pendulum

from src.chaos import (
    RandomEventGenerator,
    ScenarioAdapter,
    ConfidenceTracker,
    ChaosConfig,
    RandomEvent,
    ChaosEventType,
)


class TestChaosIntegration:
    """Integration tests for chaos injection flow."""

    def test_event_generator_respects_config_disabled(self):
        """Event generator returns None when disabled."""
        config = ChaosConfig(
            enabled=False,
            base_event_chance=0.1,
            event_probabilities={"urgent_bug": 0.1}
        )
        generator = RandomEventGenerator(config, seed=42)

        event = generator.roll_for_event(["TEST-1"], ["dev-alice"])

        assert event is None

    def test_event_generator_respects_probabilities(self):
        """Event generator respects configured probabilities."""
        config = ChaosConfig(
            enabled=True,
            base_event_chance=1.0,  # Always trigger
            event_probabilities={
                "urgent_bug": 1.0,  # Only this event type
                "production_outage": 0.0,
            }
        )
        generator = RandomEventGenerator(config, seed=42)

        # Run multiple times to verify
        events = []
        for _ in range(10):
            event = generator.roll_for_event(["TEST-1"], ["dev-alice"])
            if event:
                events.append(event.event_type)

        # Should only get urgent_bug (or None if roll fails)
        for event_type in events:
            assert event_type == ChaosEventType.urgent_bug

    def test_adapter_inserts_actions_via_scheduler(self):
        """ScenarioAdapter inserts new actions via scheduler."""
        scheduler = MagicMock()
        scheduler.queue = MagicMock()
        scheduler.queue._heap = []
        scheduler.store = MagicMock()

        adapter = ScenarioAdapter(scheduler)

        event = RandomEvent(
            event_type=ChaosEventType.urgent_bug,
            triggered_at=pendulum.now("UTC"),
            affected_tickets=["TEST-123"],
            affected_agents=["dev-alice"],
            description="Test urgent bug event",
            severity="high",
            details={"test": "data"},
        )

        result = adapter.adapt_to_event(event)

        assert scheduler.schedule_action.called
        assert len(result.actions_inserted) > 0

    def test_confidence_tracker_detects_divergence(self):
        """ConfidenceTracker detects when scenario diverged too far."""
        tracker = ConfidenceTracker(threshold=0.7, override_limit=3)

        # Create mock scenario with high divergence
        scenario = MagicMock()
        scenario.script = [
            MagicMock(events=[
                MagicMock(
                    event_id="e1",
                    executed=True,
                    execution_result={"adapted": True, "external_override": True}
                ),
                MagicMock(
                    event_id="e2",
                    executed=True,
                    execution_result={"adapted": True, "external_override": True}
                ),
                MagicMock(
                    event_id="e3",
                    executed=True,
                    execution_result={"adapted": True, "external_override": True}
                ),
                MagicMock(
                    event_id="e4",
                    executed=True,
                    execution_result={}  # Executed as planned
                ),
            ])
        ]
        scenario.events_executed = ["e1", "e2", "e3", "e4"]

        confidence = tracker.calculate_confidence(scenario)

        # 3 external overrides, 1 as planned = 25% fidelity
        assert confidence.script_fidelity < 0.7
        assert confidence.external_overrides >= 3
        assert confidence.accept_reality is True

    def test_chaos_config_loads_from_dict(self):
        """ChaosConfig loads from settings dict."""
        settings = {
            "random_events": {
                "enabled": True,
                "base_event_chance": 0.15,
                "event_probabilities": {
                    "urgent_bug": 0.20,
                    "external_blocker": 0.10,
                },
                "confidence_threshold": 0.7,
                "external_override_limit": 3,
            }
        }

        config = ChaosConfig.load_from_settings(settings)

        assert config.enabled is True
        assert config.base_event_chance == 0.15
        assert config.event_probabilities["urgent_bug"] == 0.20
        assert config.confidence_threshold == 0.7
        assert config.external_override_limit == 3

    def test_full_chaos_flow(self):
        """Test full chaos flow: generate -> adapt -> track."""
        # Setup
        config = ChaosConfig(
            enabled=True,
            base_event_chance=1.0,
            event_probabilities={"urgent_bug": 1.0}
        )
        generator = RandomEventGenerator(config, seed=42)

        scheduler = MagicMock()
        scheduler.queue = MagicMock()
        scheduler.queue._heap = []
        scheduler.store = MagicMock()
        adapter = ScenarioAdapter(scheduler)

        # Generate event
        event = generator.roll_for_event(["TEST-100"], ["dev-alice"])

        if event:
            # Adapt to event
            result = adapter.adapt_to_event(event)

            # Verify adaptation occurred
            assert result.event_id == event.event_id
            # Bug fix action should be inserted
            if event.event_type == ChaosEventType.urgent_bug:
                assert len(result.actions_inserted) > 0
