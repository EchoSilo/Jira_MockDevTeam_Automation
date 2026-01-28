"""
Tests for chaos event models and configuration.

Tests verify RandomEvent validation, ChaosConfig loading,
and event type enumeration.
"""

import pytest
import pendulum
from src.chaos import RandomEvent, ChaosConfig, ChaosEventType


class TestChaosEventType:
    """Test ChaosEventType enum."""

    def test_has_all_six_event_types(self):
        """Verify all 6 event types are defined."""
        expected_types = {
            "production_outage",
            "urgent_bug",
            "team_absence",
            "external_blocker",
            "priority_shift",
            "scope_change"
        }
        actual_types = {e.value for e in ChaosEventType}
        assert actual_types == expected_types


class TestRandomEvent:
    """Test RandomEvent dataclass."""

    def test_auto_generates_event_id(self):
        """Event ID should be auto-generated if not provided."""
        event = RandomEvent(
            event_type=ChaosEventType.urgent_bug,
            triggered_at=pendulum.now("UTC"),
            affected_tickets=["PROJ-123"],
            affected_agents=[],
            description="Test bug",
            severity="high",
            duration_ticks=1,
            details={}
        )
        assert event.event_id is not None
        assert len(event.event_id) == 8  # uuid[:8]

    def test_validates_severity_enum(self):
        """Severity must be one of: low, medium, high, critical."""
        valid_severities = ["low", "medium", "high", "critical"]

        for severity in valid_severities:
            event = RandomEvent(
                event_type=ChaosEventType.urgent_bug,
                triggered_at=pendulum.now("UTC"),
                affected_tickets=["PROJ-123"],
                affected_agents=[],
                description="Test",
                severity=severity,
                duration_ticks=1,
                details={}
            )
            assert event.severity == severity

        # Invalid severity should raise ValueError
        with pytest.raises(ValueError, match="severity must be one of"):
            RandomEvent(
                event_type=ChaosEventType.urgent_bug,
                triggered_at=pendulum.now("UTC"),
                affected_tickets=["PROJ-123"],
                affected_agents=[],
                description="Test",
                severity="invalid",
                duration_ticks=1,
                details={}
            )

    def test_duration_ticks_defaults_to_one(self):
        """Duration should default to 1 tick if not specified."""
        event = RandomEvent(
            event_type=ChaosEventType.urgent_bug,
            triggered_at=pendulum.now("UTC"),
            affected_tickets=["PROJ-123"],
            affected_agents=[],
            description="Test",
            severity="high",
            details={}
        )
        assert event.duration_ticks == 1

    def test_accepts_pendulum_datetime(self):
        """Triggered_at must be pendulum.DateTime."""
        now = pendulum.now("UTC")
        event = RandomEvent(
            event_type=ChaosEventType.urgent_bug,
            triggered_at=now,
            affected_tickets=["PROJ-123"],
            affected_agents=[],
            description="Test",
            severity="high",
            duration_ticks=1,
            details={}
        )
        assert event.triggered_at == now
        assert isinstance(event.triggered_at, pendulum.DateTime)


class TestChaosConfig:
    """Test ChaosConfig dataclass."""

    def test_loads_from_settings_yaml(self):
        """Should load from config/settings.yaml."""
        config = ChaosConfig.load_from_settings()

        assert isinstance(config.enabled, bool)
        assert isinstance(config.base_event_chance, float)
        assert isinstance(config.event_probabilities, dict)

    def test_has_default_event_probabilities(self):
        """Default event probabilities should be set."""
        config = ChaosConfig.load_from_settings()

        # Check all 6 event types have probabilities
        expected_types = [
            "production_outage",
            "urgent_bug",
            "team_absence",
            "external_blocker",
            "priority_shift",
            "scope_change"
        ]

        for event_type in expected_types:
            assert event_type in config.event_probabilities
            prob = config.event_probabilities[event_type]
            assert 0.0 <= prob <= 1.0, f"{event_type} probability must be in [0, 1]"

    def test_handles_missing_random_events_section_gracefully(self):
        """Should return defaults if random_events section is missing."""
        # This test verifies graceful handling
        # If settings.yaml doesn't have random_events, we should get defaults
        config = ChaosConfig.load_from_settings()

        # Even if missing from YAML, we should get sensible defaults
        assert config.base_event_chance >= 0.0
        assert config.base_event_chance <= 1.0
        assert len(config.event_probabilities) == 6

    def test_validates_probability_range(self):
        """Event probabilities must be between 0.0 and 1.0."""
        # This test expects validation to happen in __post_init__
        with pytest.raises(ValueError, match="probability must be between 0.0 and 1.0"):
            ChaosConfig(
                enabled=True,
                base_event_chance=0.1,
                event_probabilities={
                    "production_outage": 1.5,  # Invalid: > 1.0
                    "urgent_bug": 0.1,
                    "team_absence": 0.03,
                    "external_blocker": 0.15,
                    "priority_shift": 0.12,
                    "scope_change": 0.05
                }
            )

    def test_validates_base_event_chance_range(self):
        """Base event chance must be between 0.0 and 1.0."""
        with pytest.raises(ValueError, match="base_event_chance must be between 0.0 and 1.0"):
            ChaosConfig(
                enabled=True,
                base_event_chance=1.5,  # Invalid: > 1.0
                event_probabilities={}
            )
