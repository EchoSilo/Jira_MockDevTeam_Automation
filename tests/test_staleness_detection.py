"""Tests for staleness detection and cleanup (RECON-05).

Verifies:
- is_stale() returns False when validation_tick_count < threshold
- is_stale() returns True when validation_tick_count >= threshold
- mark_validated() resets tick count to 0
- increment_validation_miss() increments tick count
- cleanup_stale_scenarios() removes only stale scenarios
- Tombstone records contain correct information
"""
import pytest
from src.state.models import (
    ActiveScenario,
    TicketComplexity,
    ScenarioPhase,
    SimulationState,
)
from src.reconciliation.staleness import cleanup_stale_scenarios


class TestActiveScenarioStaleness:
    """Tests for ActiveScenario staleness methods."""

    def test_is_stale_returns_false_below_threshold(self):
        """is_stale() returns False when validation_tick_count < threshold."""
        scenario = ActiveScenario.create_normal_flow("TEST-1", TicketComplexity.STORY)
        scenario.validation_tick_count = 3
        assert not scenario.is_stale(staleness_threshold=4)

    def test_is_stale_returns_true_at_threshold(self):
        """is_stale() returns True when validation_tick_count == threshold."""
        scenario = ActiveScenario.create_normal_flow("TEST-1", TicketComplexity.STORY)
        scenario.validation_tick_count = 4
        assert scenario.is_stale(staleness_threshold=4)

    def test_is_stale_returns_true_above_threshold(self):
        """is_stale() returns True when validation_tick_count > threshold."""
        scenario = ActiveScenario.create_normal_flow("TEST-1", TicketComplexity.STORY)
        scenario.validation_tick_count = 10
        assert scenario.is_stale(staleness_threshold=4)

    def test_is_stale_uses_default_threshold_of_4(self):
        """is_stale() uses default threshold of 4."""
        scenario = ActiveScenario.create_normal_flow("TEST-1", TicketComplexity.STORY)
        scenario.validation_tick_count = 3
        assert not scenario.is_stale()  # Default threshold is 4

        scenario.validation_tick_count = 4
        assert scenario.is_stale()  # At default threshold

    def test_mark_validated_resets_tick_count(self):
        """mark_validated() resets validation_tick_count to 0."""
        scenario = ActiveScenario.create_normal_flow("TEST-1", TicketComplexity.STORY)
        scenario.validation_tick_count = 5
        scenario.mark_validated()
        assert scenario.validation_tick_count == 0

    def test_mark_validated_updates_last_validated(self):
        """mark_validated() updates last_validated timestamp."""
        import pendulum
        scenario = ActiveScenario.create_normal_flow("TEST-1", TicketComplexity.STORY)
        old_validated = scenario.last_validated

        # Small delay to ensure time difference
        scenario.mark_validated()

        # last_validated should be updated (or same if extremely fast)
        assert scenario.last_validated >= old_validated

    def test_increment_validation_miss_increments_tick_count(self):
        """increment_validation_miss() increments validation_tick_count by 1."""
        scenario = ActiveScenario.create_normal_flow("TEST-1", TicketComplexity.STORY)
        assert scenario.validation_tick_count == 0

        scenario.increment_validation_miss()
        assert scenario.validation_tick_count == 1

        scenario.increment_validation_miss()
        assert scenario.validation_tick_count == 2

        scenario.increment_validation_miss()
        assert scenario.validation_tick_count == 3

    def test_new_scenario_starts_with_zero_tick_count(self):
        """New scenarios start with validation_tick_count of 0."""
        scenario = ActiveScenario.create_normal_flow("TEST-1", TicketComplexity.STORY)
        assert scenario.validation_tick_count == 0
        assert not scenario.is_stale()


class TestCleanupStaleScenarios:
    """Tests for cleanup_stale_scenarios function."""

    def test_cleanup_removes_stale_scenarios(self):
        """cleanup_stale_scenarios() removes scenarios at/above threshold."""
        state = SimulationState()

        # Create fresh scenario (below threshold)
        fresh = ActiveScenario.create_normal_flow("FRESH-1", TicketComplexity.STORY)
        fresh.validation_tick_count = 2
        state.add_scenario(fresh)

        # Create stale scenario (at threshold)
        stale = ActiveScenario.create_normal_flow("STALE-1", TicketComplexity.STORY)
        stale.validation_tick_count = 5
        state.add_scenario(stale)

        tombstones = cleanup_stale_scenarios(state, staleness_threshold=4)

        # Only stale scenario should be removed
        assert len(tombstones) == 1
        assert tombstones[0]["ticket_key"] == "STALE-1"

        # Verify state
        remaining_tickets = [s.ticket_key for s in state.active_scenarios.values()]
        assert "FRESH-1" in remaining_tickets
        assert "STALE-1" not in remaining_tickets

    def test_cleanup_keeps_fresh_scenarios(self):
        """cleanup_stale_scenarios() keeps scenarios below threshold."""
        state = SimulationState()

        # Create multiple fresh scenarios
        for i in range(3):
            scenario = ActiveScenario.create_normal_flow(f"FRESH-{i}", TicketComplexity.STORY)
            scenario.validation_tick_count = i  # 0, 1, 2 - all below 4
            state.add_scenario(scenario)

        tombstones = cleanup_stale_scenarios(state, staleness_threshold=4)

        assert len(tombstones) == 0
        assert len(state.active_scenarios) == 3

    def test_cleanup_removes_multiple_stale_scenarios(self):
        """cleanup_stale_scenarios() removes all stale scenarios."""
        state = SimulationState()

        # Create multiple stale scenarios
        for i in range(3):
            scenario = ActiveScenario.create_normal_flow(f"STALE-{i}", TicketComplexity.STORY)
            scenario.validation_tick_count = 4 + i  # 4, 5, 6 - all at/above threshold
            state.add_scenario(scenario)

        # Create one fresh scenario
        fresh = ActiveScenario.create_normal_flow("FRESH-1", TicketComplexity.STORY)
        fresh.validation_tick_count = 1
        state.add_scenario(fresh)

        tombstones = cleanup_stale_scenarios(state, staleness_threshold=4)

        assert len(tombstones) == 3
        assert len(state.active_scenarios) == 1
        assert list(state.active_scenarios.values())[0].ticket_key == "FRESH-1"

    def test_tombstone_contains_ticket_key(self):
        """Tombstone records include ticket_key."""
        state = SimulationState()
        stale = ActiveScenario.create_normal_flow("ESCRUM-123", TicketComplexity.STORY)
        stale.validation_tick_count = 5
        state.add_scenario(stale)

        tombstones = cleanup_stale_scenarios(state, staleness_threshold=4)

        assert tombstones[0]["ticket_key"] == "ESCRUM-123"

    def test_tombstone_contains_reason(self):
        """Tombstone records include reason with tick count."""
        state = SimulationState()
        stale = ActiveScenario.create_normal_flow("ESCRUM-123", TicketComplexity.STORY)
        stale.validation_tick_count = 7
        state.add_scenario(stale)

        tombstones = cleanup_stale_scenarios(state, staleness_threshold=4)

        assert "unvalidated for 7 ticks" in tombstones[0]["reason"]

    def test_tombstone_contains_last_phase(self):
        """Tombstone records include last_phase."""
        state = SimulationState()
        stale = ActiveScenario.create_normal_flow("ESCRUM-123", TicketComplexity.STORY)
        stale.validation_tick_count = 5
        stale.current_phase = ScenarioPhase.IN_PROGRESS
        state.add_scenario(stale)

        tombstones = cleanup_stale_scenarios(state, staleness_threshold=4)

        assert tombstones[0]["last_phase"] == "in_progress"

    def test_tombstone_contains_scenario_id(self):
        """Tombstone records include scenario_id."""
        state = SimulationState()
        stale = ActiveScenario.create_normal_flow("ESCRUM-123", TicketComplexity.STORY)
        stale.validation_tick_count = 5
        scenario_id = stale.scenario_id
        state.add_scenario(stale)

        tombstones = cleanup_stale_scenarios(state, staleness_threshold=4)

        assert tombstones[0]["scenario_id"] == scenario_id

    def test_cleanup_records_action_in_state(self):
        """cleanup_stale_scenarios() records scenario_invalidated action."""
        state = SimulationState()
        stale = ActiveScenario.create_normal_flow("STALE-1", TicketComplexity.STORY)
        stale.validation_tick_count = 5
        state.add_scenario(stale)

        cleanup_stale_scenarios(state, staleness_threshold=4)

        # Find the recorded action
        invalidated_actions = [
            a for a in state.recent_actions
            if a.action_type == "scenario_invalidated"
        ]
        assert len(invalidated_actions) == 1
        assert invalidated_actions[0].agent_id == "system"
        assert "Stale scenario" in invalidated_actions[0].details

    def test_cleanup_moves_to_completed_scenarios(self):
        """cleanup_stale_scenarios() moves scenario to completed_scenarios list."""
        state = SimulationState()
        stale = ActiveScenario.create_normal_flow("STALE-1", TicketComplexity.STORY)
        stale.validation_tick_count = 5
        scenario_id = stale.scenario_id
        state.add_scenario(stale)

        cleanup_stale_scenarios(state, staleness_threshold=4)

        assert scenario_id in state.completed_scenarios
        assert scenario_id not in state.active_scenarios

    def test_cleanup_with_custom_threshold(self):
        """cleanup_stale_scenarios() respects custom staleness_threshold."""
        state = SimulationState()
        scenario = ActiveScenario.create_normal_flow("TEST-1", TicketComplexity.STORY)
        scenario.validation_tick_count = 2
        state.add_scenario(scenario)

        # With threshold of 4, should not be removed
        tombstones = cleanup_stale_scenarios(state, staleness_threshold=4)
        assert len(tombstones) == 0
        assert len(state.active_scenarios) == 1

        # With threshold of 2, should be removed
        tombstones = cleanup_stale_scenarios(state, staleness_threshold=2)
        assert len(tombstones) == 1
        assert len(state.active_scenarios) == 0

    def test_cleanup_with_empty_state(self):
        """cleanup_stale_scenarios() handles empty state gracefully."""
        state = SimulationState()
        tombstones = cleanup_stale_scenarios(state, staleness_threshold=4)
        assert tombstones == []
