"""
Tests for capacity planning and backlog prioritization.

Tests CapacityPlanner (velocity-based item selection) and BacklogPrioritizer
(LLM-based ranking with caching).
"""

import pytest
from unittest.mock import Mock, MagicMock
import pendulum

from src.planning import CapacityPlanner, VelocityTracker
from src.planning.backlog_prioritizer import BacklogPrioritizer


class TestCapacityPlanner:
    """Tests for CapacityPlanner."""

    def test_select_items_within_capacity(self):
        """Test selecting items within capacity."""
        tracker = VelocityTracker()
        tracker.record_sprint(1, 20, 20)
        tracker.record_sprint(2, 20, 20)
        tracker.record_sprint(3, 20, 20)

        planner = CapacityPlanner(tracker)
        capacity = planner.calculate_capacity()  # Should be 16 (20 * 0.8)

        backlog = [
            {"key": "PROJ-1", "points": 5},
            {"key": "PROJ-2", "points": 5},
            {"key": "PROJ-3", "points": 5},
            {"key": "PROJ-4", "points": 5},  # This would exceed 16
        ]

        selected = planner.select_items(backlog, capacity)
        assert len(selected) == 3
        total = sum(item["points"] for item in selected)
        assert total == 15

    def test_select_items_max_limit(self):
        """Test max_items limit."""
        planner = CapacityPlanner()
        backlog = [{"key": f"PROJ-{i}", "points": 1} for i in range(20)]

        selected = planner.select_items(backlog, capacity=100, max_items=5)
        assert len(selected) == 5

    def test_estimate_points_for_unestimated(self):
        """Test point estimation for items without points."""
        planner = CapacityPlanner()
        backlog = [
            {"key": "PROJ-1", "type": "Bug"},  # Should estimate 2
            {"key": "PROJ-2", "type": "Story"},  # Should estimate 5
        ]

        selected = planner.select_items(backlog, capacity=10)
        assert len(selected) == 2

    def test_estimate_points_uses_story_points_field(self):
        """Test that story_points field is used if points is missing."""
        planner = CapacityPlanner()
        backlog = [
            {"key": "PROJ-1", "story_points": 3},
            {"key": "PROJ-2", "story_points": 2},
        ]

        selected = planner.select_items(backlog, capacity=5)
        assert len(selected) == 2

    def test_estimate_points_by_type(self):
        """Test point estimation based on item type."""
        planner = CapacityPlanner()

        assert planner._estimate_points({"type": "Bug"}) == 2
        assert planner._estimate_points({"type": "Task"}) == 3
        assert planner._estimate_points({"type": "Story"}) == 5
        assert planner._estimate_points({"type": "Feature"}) == 8
        assert planner._estimate_points({"type": "Unknown"}) == 3

    def test_selection_summary(self):
        """Test selection summary generation."""
        planner = CapacityPlanner()
        selected = [
            {"key": "PROJ-1", "points": 5},
            {"key": "PROJ-2", "points": 3},
        ]

        summary = planner.get_selection_summary(selected)
        assert summary["item_count"] == 2
        assert summary["total_points"] == 8
        assert "PROJ-1" in summary["items"]
        assert "PROJ-2" in summary["items"]

    def test_selection_summary_with_estimated_points(self):
        """Test summary with items requiring point estimation."""
        planner = CapacityPlanner()
        selected = [
            {"key": "PROJ-1", "type": "Bug"},  # Estimated as 2
            {"key": "PROJ-2", "points": 5},
        ]

        summary = planner.get_selection_summary(selected)
        assert summary["total_points"] == 7  # 2 + 5

    def test_capacity_calculation_with_buffer(self):
        """Test capacity calculation with custom buffer."""
        tracker = VelocityTracker()
        tracker.record_sprint(1, 20, 20)

        planner = CapacityPlanner(tracker)

        # 80% buffer
        capacity_80 = planner.calculate_capacity(buffer_percentage=0.8)
        assert capacity_80 == 16  # 20 * 0.8

        # 100% (no buffer)
        capacity_100 = planner.calculate_capacity(buffer_percentage=1.0)
        assert capacity_100 == 20

    def test_select_items_empty_backlog(self):
        """Test selecting from empty backlog."""
        planner = CapacityPlanner()
        selected = planner.select_items([], capacity=10)
        assert len(selected) == 0

    def test_select_items_zero_capacity(self):
        """Test selecting with zero capacity."""
        planner = CapacityPlanner()
        backlog = [{"key": "PROJ-1", "points": 5}]
        selected = planner.select_items(backlog, capacity=0)
        assert len(selected) == 0


class TestBacklogPrioritizer:
    """Tests for BacklogPrioritizer."""

    def test_prioritize_uses_llm(self):
        """Test that prioritize calls LLM."""
        from unittest.mock import patch, MagicMock
        import sys

        mock_llm = Mock()
        mock_llm.routine_model = "claude-3-5-haiku-20241022"

        # Mock litellm module
        mock_litellm = MagicMock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = '["PROJ-2", "PROJ-1"]'
        mock_litellm.completion = Mock(return_value=mock_response)

        with patch.dict(sys.modules, {'litellm': mock_litellm}):
            prioritizer = BacklogPrioritizer(mock_llm)
            backlog = [
                {"key": "PROJ-1", "summary": "Feature A"},
                {"key": "PROJ-2", "summary": "Bug fix"},
            ]

            result = prioritizer.prioritize(backlog)
            assert mock_litellm.completion.called
            assert result[0]["key"] == "PROJ-2"  # Bug should be first

    def test_prioritize_caches_result(self):
        """Test that prioritization is cached."""
        from unittest.mock import patch, MagicMock
        import sys

        mock_llm = Mock()
        mock_llm.routine_model = "claude-3-5-haiku-20241022"

        # Mock litellm module
        mock_litellm = MagicMock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = '["PROJ-1", "PROJ-2"]'
        mock_litellm.completion = Mock(return_value=mock_response)

        with patch.dict(sys.modules, {'litellm': mock_litellm}):
            prioritizer = BacklogPrioritizer(mock_llm, cache_hours=24)
            backlog = [
                {"key": "PROJ-1", "summary": "A"},
                {"key": "PROJ-2", "summary": "B"},
            ]

            # First call should use LLM
            prioritizer.prioritize(backlog)
            assert mock_litellm.completion.call_count == 1

            # Second call should use cache
            prioritizer.prioritize(backlog)
            assert mock_litellm.completion.call_count == 1  # Still 1

    def test_prioritize_force_refresh(self):
        """Test force_refresh bypasses cache."""
        from unittest.mock import patch, MagicMock
        import sys

        mock_llm = Mock()
        mock_llm.routine_model = "claude-3-5-haiku-20241022"

        # Mock litellm module
        mock_litellm = MagicMock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = '["PROJ-1"]'
        mock_litellm.completion = Mock(return_value=mock_response)

        with patch.dict(sys.modules, {'litellm': mock_litellm}):
            prioritizer = BacklogPrioritizer(mock_llm)
            backlog = [{"key": "PROJ-1", "summary": "A"}]

            prioritizer.prioritize(backlog)
            prioritizer.prioritize(backlog, force_refresh=True)
            assert mock_litellm.completion.call_count == 2

    def test_fallback_on_llm_error(self):
        """Test fallback prioritization when LLM fails."""
        from unittest.mock import patch, MagicMock
        import sys

        mock_llm = Mock()
        mock_llm.routine_model = "claude-3-5-haiku-20241022"

        # Mock litellm module to raise error
        mock_litellm = MagicMock()
        mock_litellm.completion = Mock(side_effect=Exception("LLM error"))

        with patch.dict(sys.modules, {'litellm': mock_litellm}):
            prioritizer = BacklogPrioritizer(mock_llm)
            backlog = [
                {"key": "PROJ-1", "type": "Story", "priority": "Low"},
                {"key": "PROJ-2", "type": "Bug", "priority": "High"},
            ]

            result = prioritizer.prioritize(backlog)
            # Should fall back to type-based: Bugs before Stories
            assert result[0]["key"] == "PROJ-2"

    def test_fallback_prioritization_by_type(self):
        """Test fallback prioritization uses type order."""
        mock_llm = Mock()
        prioritizer = BacklogPrioritizer(mock_llm)

        backlog = [
            {"key": "PROJ-1", "type": "Feature", "priority": "Medium"},
            {"key": "PROJ-2", "type": "Story", "priority": "Medium"},
            {"key": "PROJ-3", "type": "Bug", "priority": "Medium"},
            {"key": "PROJ-4", "type": "Task", "priority": "Medium"},
        ]

        result = prioritizer._fallback_prioritize(backlog)
        # Order should be Bug, Task, Story, Feature
        assert result[0]["key"] == "PROJ-3"  # Bug
        assert result[1]["key"] == "PROJ-4"  # Task
        assert result[2]["key"] == "PROJ-2"  # Story
        assert result[3]["key"] == "PROJ-1"  # Feature

    def test_fallback_prioritization_by_priority(self):
        """Test fallback uses priority when types are equal."""
        mock_llm = Mock()
        prioritizer = BacklogPrioritizer(mock_llm)

        backlog = [
            {"key": "PROJ-1", "type": "Story", "priority": "Low"},
            {"key": "PROJ-2", "type": "Story", "priority": "High"},
            {"key": "PROJ-3", "type": "Story", "priority": "Highest"},
        ]

        result = prioritizer._fallback_prioritize(backlog)
        # Order should be Highest, High, Low
        assert result[0]["key"] == "PROJ-3"
        assert result[1]["key"] == "PROJ-2"
        assert result[2]["key"] == "PROJ-1"

    def test_cache_expiry(self):
        """Test cache expires after configured hours."""
        mock_llm = Mock()
        mock_llm.routine_model = "claude-3-5-haiku-20241022"

        prioritizer = BacklogPrioritizer(mock_llm, cache_hours=1)
        backlog = [{"key": "PROJ-1", "summary": "A"}]

        # Set up cache manually
        cache_key = prioritizer._get_cache_key(backlog)
        prioritizer._cache = {"key": cache_key, "order": ["PROJ-1"]}
        prioritizer._cache_time = pendulum.now("UTC").subtract(hours=2)  # Expired

        # Should return False since cache is expired
        assert not prioritizer._is_cache_valid(cache_key)

    def test_cache_invalid_for_different_backlog(self):
        """Test cache is invalid when backlog changes."""
        mock_llm = Mock()
        prioritizer = BacklogPrioritizer(mock_llm)

        backlog1 = [{"key": "PROJ-1"}]
        backlog2 = [{"key": "PROJ-2"}]

        cache_key1 = prioritizer._get_cache_key(backlog1)
        cache_key2 = prioritizer._get_cache_key(backlog2)

        # Set cache for backlog1
        prioritizer._update_cache(cache_key1, ["PROJ-1"])

        # Should be invalid for backlog2
        assert not prioritizer._is_cache_valid(cache_key2)

    def test_parse_prioritization_response(self):
        """Test parsing LLM response for ticket keys."""
        mock_llm = Mock()
        prioritizer = BacklogPrioritizer(mock_llm)

        # Valid JSON array
        response = '["PROJ-1", "PROJ-2", "PROJ-3"]'
        result = prioritizer._parse_prioritization_response(response)
        assert result == ["PROJ-1", "PROJ-2", "PROJ-3"]

        # JSON array with extra text
        response = 'Here are the priorities:\n["PROJ-1", "PROJ-2"]\nThat\'s it.'
        result = prioritizer._parse_prioritization_response(response)
        assert result == ["PROJ-1", "PROJ-2"]

        # Invalid JSON
        response = "Not a JSON array"
        result = prioritizer._parse_prioritization_response(response)
        assert result == []

    def test_build_prioritization_prompt(self):
        """Test prompt building for LLM."""
        mock_llm = Mock()
        prioritizer = BacklogPrioritizer(mock_llm)

        backlog = [
            {"key": "PROJ-1", "type": "Story", "summary": "Feature A"},
            {"key": "PROJ-2", "type": "Bug", "summary": "Fix error"},
        ]

        prompt = prioritizer._build_prioritization_prompt(backlog, sprint_goals="Complete auth")

        assert "PROJ-1" in prompt
        assert "PROJ-2" in prompt
        assert "Feature A" in prompt
        assert "Fix error" in prompt
        assert "Complete auth" in prompt
        assert "JSON array" in prompt

    def test_sort_backlog(self):
        """Test sorting backlog by ordered keys."""
        mock_llm = Mock()
        prioritizer = BacklogPrioritizer(mock_llm)

        backlog = [
            {"key": "PROJ-1", "summary": "First"},
            {"key": "PROJ-2", "summary": "Second"},
            {"key": "PROJ-3", "summary": "Third"},
        ]

        ordered_keys = ["PROJ-3", "PROJ-1", "PROJ-2"]
        result = prioritizer._sort_backlog(backlog, ordered_keys)

        assert result[0]["key"] == "PROJ-3"
        assert result[1]["key"] == "PROJ-1"
        assert result[2]["key"] == "PROJ-2"

    def test_sort_backlog_partial_keys(self):
        """Test sorting when ordered_keys doesn't include all items."""
        mock_llm = Mock()
        prioritizer = BacklogPrioritizer(mock_llm)

        backlog = [
            {"key": "PROJ-1", "summary": "First"},
            {"key": "PROJ-2", "summary": "Second"},
            {"key": "PROJ-3", "summary": "Third"},
        ]

        # Only prioritize PROJ-2
        ordered_keys = ["PROJ-2"]
        result = prioritizer._sort_backlog(backlog, ordered_keys)

        # PROJ-2 should be first, others follow in original order
        assert result[0]["key"] == "PROJ-2"
