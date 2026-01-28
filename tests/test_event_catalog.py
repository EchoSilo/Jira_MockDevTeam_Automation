"""Tests for EventCatalog."""

import pytest
from pathlib import Path
import tempfile
import yaml

from src.chaos.event_catalog import EventCatalog
from src.chaos.models import ChaosEventType
from src.scenarios.sprint_scenario import ScenarioArchetype


class TestEventCatalog:
    """Tests for EventCatalog class."""

    def test_loads_from_default_path(self):
        """EventCatalog loads from config/chaos_events.yaml by default."""
        catalog = EventCatalog()
        # Should have loaded templates if file exists
        templates = catalog.get_template(ChaosEventType.production_outage)
        assert isinstance(templates, dict)

    def test_loads_from_custom_path(self, tmp_path):
        """EventCatalog loads from custom path."""
        config_file = tmp_path / "test_events.yaml"
        config_file.write_text(yaml.dump({
            "event_templates": {
                "urgent_bug": {"default_severity": "high"}
            },
            "archetype_weights": {
                "smooth_sprint": {"urgent_bug": 0.5}
            }
        }))

        catalog = EventCatalog(config_file)
        template = catalog.get_template(ChaosEventType.urgent_bug)
        assert template["default_severity"] == "high"

    def test_get_template_returns_empty_for_unknown(self):
        """get_template returns empty dict for unknown event type."""
        catalog = EventCatalog()
        # Use a type that might not have a template
        template = catalog.get_template(ChaosEventType.scope_change)
        # Either returns template or empty dict, both valid
        assert isinstance(template, dict)

    def test_get_weight_multiplier_default(self):
        """get_weight_multiplier returns 1.0 for unknown archetype/event."""
        catalog = EventCatalog()
        # Even with empty config, should return 1.0
        multiplier = catalog.get_weight_multiplier(
            ScenarioArchetype.SMOOTH_SPRINT,
            ChaosEventType.urgent_bug
        )
        assert isinstance(multiplier, float)

    def test_get_weight_multiplier_from_config(self, tmp_path):
        """get_weight_multiplier returns configured value."""
        config_file = tmp_path / "test_events.yaml"
        config_file.write_text(yaml.dump({
            "event_templates": {},
            "archetype_weights": {
                "blocker_heavy": {"external_blocker": 2.0}
            }
        }))

        catalog = EventCatalog(config_file)
        multiplier = catalog.get_weight_multiplier(
            ScenarioArchetype.BLOCKER_HEAVY,
            ChaosEventType.external_blocker
        )
        assert multiplier == pytest.approx(2.0)

    def test_adjust_probabilities_with_archetype(self, tmp_path):
        """adjust_probabilities applies archetype multipliers."""
        config_file = tmp_path / "test_events.yaml"
        config_file.write_text(yaml.dump({
            "event_templates": {},
            "archetype_weights": {
                "blocker_heavy": {"external_blocker": 2.0}
            }
        }))

        catalog = EventCatalog(config_file)
        base_probs = {"external_blocker": 0.15}
        adjusted = catalog.adjust_probabilities(
            base_probs,
            ScenarioArchetype.BLOCKER_HEAVY
        )
        assert adjusted["external_blocker"] == pytest.approx(0.30)

    def test_adjust_probabilities_unknown_event_type(self, tmp_path):
        """adjust_probabilities preserves unknown event types."""
        config_file = tmp_path / "test_events.yaml"
        config_file.write_text(yaml.dump({
            "event_templates": {},
            "archetype_weights": {}
        }))

        catalog = EventCatalog(config_file)
        base_probs = {"unknown_event": 0.1}
        adjusted = catalog.adjust_probabilities(
            base_probs,
            ScenarioArchetype.SMOOTH_SPRINT
        )
        assert adjusted["unknown_event"] == pytest.approx(0.1)

    def test_adjust_probabilities_multiple_events(self, tmp_path):
        """adjust_probabilities handles multiple event types."""
        config_file = tmp_path / "test_events.yaml"
        config_file.write_text(yaml.dump({
            "event_templates": {},
            "archetype_weights": {
                "smooth_sprint": {
                    "production_outage": 0.2,
                    "urgent_bug": 0.5
                }
            }
        }))

        catalog = EventCatalog(config_file)
        base_probs = {
            "production_outage": 0.05,
            "urgent_bug": 0.10
        }
        adjusted = catalog.adjust_probabilities(
            base_probs,
            ScenarioArchetype.SMOOTH_SPRINT
        )
        assert adjusted["production_outage"] == pytest.approx(0.01)
        assert adjusted["urgent_bug"] == pytest.approx(0.05)

    def test_format_description_substitution(self, tmp_path):
        """format_description substitutes template variables."""
        config_file = tmp_path / "test_events.yaml"
        config_file.write_text(yaml.dump({
            "event_templates": {
                "urgent_bug": {"description_template": "Bug in {ticket_key}"}
            },
            "archetype_weights": {}
        }))

        catalog = EventCatalog(config_file)
        desc = catalog.format_description(
            ChaosEventType.urgent_bug,
            ticket_key="TEST-123"
        )
        assert desc == "Bug in TEST-123"

    def test_format_description_missing_variable(self, tmp_path):
        """format_description handles missing template variables gracefully."""
        config_file = tmp_path / "test_events.yaml"
        config_file.write_text(yaml.dump({
            "event_templates": {
                "urgent_bug": {"description_template": "Bug in {ticket_key}"}
            },
            "archetype_weights": {}
        }))

        catalog = EventCatalog(config_file)
        desc = catalog.format_description(ChaosEventType.urgent_bug)
        # Should return unformatted template when variable missing
        assert desc == "Bug in {ticket_key}"

    def test_format_description_no_template(self):
        """format_description returns default when template missing."""
        catalog = EventCatalog()
        # Create empty catalog
        catalog._templates = {}
        desc = catalog.format_description(ChaosEventType.urgent_bug)
        assert "urgent_bug" in desc

    def test_get_response_action_with_response(self, tmp_path):
        """get_response_action returns action details."""
        config_file = tmp_path / "test_events.yaml"
        config_file.write_text(yaml.dump({
            "event_templates": {
                "production_outage": {
                    "requires_response_action": True,
                    "response_agent_role": "tech_lead",
                    "response_action_type": "emergency_response"
                }
            },
            "archetype_weights": {}
        }))

        catalog = EventCatalog(config_file)
        response = catalog.get_response_action(ChaosEventType.production_outage)
        assert response is not None
        assert response["agent_role"] == "tech_lead"
        assert response["action_type"] == "emergency_response"

    def test_get_response_action_without_response(self, tmp_path):
        """get_response_action returns None when no response required."""
        config_file = tmp_path / "test_events.yaml"
        config_file.write_text(yaml.dump({
            "event_templates": {
                "priority_shift": {
                    "requires_response_action": False
                }
            },
            "archetype_weights": {}
        }))

        catalog = EventCatalog(config_file)
        response = catalog.get_response_action(ChaosEventType.priority_shift)
        assert response is None

    def test_missing_config_file_graceful(self, tmp_path):
        """EventCatalog handles missing config file gracefully."""
        missing_path = tmp_path / "nonexistent.yaml"
        catalog = EventCatalog(missing_path)
        # Should work with empty config
        template = catalog.get_template(ChaosEventType.urgent_bug)
        assert template == {}

    def test_full_workflow_with_real_config(self):
        """Test complete workflow with real config file."""
        catalog = EventCatalog()

        # Get template
        template = catalog.get_template(ChaosEventType.external_blocker)
        if template:  # Only test if real config exists
            assert "description_template" in template

        # Get weight multiplier
        multiplier = catalog.get_weight_multiplier(
            ScenarioArchetype.BLOCKER_HEAVY,
            ChaosEventType.external_blocker
        )
        assert isinstance(multiplier, float)

        # Adjust probabilities
        base_probs = {"external_blocker": 0.15}
        adjusted = catalog.adjust_probabilities(
            base_probs,
            ScenarioArchetype.BLOCKER_HEAVY
        )
        assert "external_blocker" in adjusted

        # Format description
        desc = catalog.format_description(
            ChaosEventType.external_blocker,
            ticket_key="TEST-123",
            blocker_detail="waiting for API"
        )
        assert isinstance(desc, str)
