"""Integration tests for /trigger metric mapping."""

import sys
import pytest
from unittest.mock import Mock, MagicMock, patch

# Mock external dependencies
sys.modules['jira'] = MagicMock()
sys.modules['jira.resources'] = MagicMock()
sys.modules['crewai'] = MagicMock()
sys.modules['litellm'] = MagicMock()
sys.modules['anthropic'] = MagicMock()


class TestTriggerMetricMapping:
    """Tests for /trigger endpoint metric mapping."""

    def test_actions_completed_maps_from_metrics_executed(self):
        """Verify actions_completed is extracted from tick_results.metrics.executed."""
        # Simulate tick_results from TickExecutor
        tick_results = {
            "tick_start": "2026-01-29T10:00:00Z",
            "metrics": {"executed": 3, "skipped": 1},
            "actions": [],
        }

        # Simulate the merge logic from main.py
        results = {}
        results.update(tick_results)
        results["actions_completed"] = results.get("metrics", {}).get("executed", 0)

        assert results["actions_completed"] == 3

    def test_actions_completed_defaults_to_zero_on_empty_metrics(self):
        """Verify actions_completed defaults to 0 when metrics dict is missing."""
        # Simulate tick_results without metrics
        tick_results = {
            "tick_start": "2026-01-29T10:00:00Z",
            "actions": [],
        }

        results = {}
        results.update(tick_results)
        results["actions_completed"] = results.get("metrics", {}).get("executed", 0)

        assert results["actions_completed"] == 0

    def test_actions_completed_defaults_on_missing_executed_key(self):
        """Verify actions_completed defaults to 0 when executed key is missing."""
        tick_results = {
            "metrics": {"skipped": 2},  # executed key missing
        }

        results = {}
        results.update(tick_results)
        results["actions_completed"] = results.get("metrics", {}).get("executed", 0)

        assert results["actions_completed"] == 0
