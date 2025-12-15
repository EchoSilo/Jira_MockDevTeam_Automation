"""
Tests for the orchestrator and simulation logic.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.state.simulation_state import SimulationState, load_state, save_state


class TestSimulationState:
    """Tests for simulation state management."""

    def test_initial_state(self):
        """Test initial state has correct defaults."""
        state = SimulationState()
        assert state.simulation_day == 1
        assert state.last_run is None
        assert len(state.agents) == 0
        assert len(state.active_tickets) == 0

    def test_get_agent_state_creates_new(self):
        """Test that get_agent_state creates new agent if not exists."""
        state = SimulationState()
        agent_state = state.get_agent_state("test_agent")
        assert agent_state is not None
        assert agent_state.actions_today == 0
        assert "test_agent" in state.agents

    def test_record_action(self):
        """Test recording an action updates state correctly."""
        state = SimulationState()
        state.record_action("test_agent", "comment", "PROJ-123")

        agent = state.agents["test_agent"]
        assert agent.actions_today == 1
        assert agent.last_action is not None
        assert "PROJ-123" in agent.recent_comments

        assert len(state.recent_actions) == 1
        assert state.recent_actions[0].agent_id == "test_agent"

    def test_track_ticket(self):
        """Test ticket tracking."""
        state = SimulationState()
        state.track_ticket("PROJ-123", "In Progress", "dev_1")

        assert "PROJ-123" in state.active_tickets
        ticket = state.active_tickets["PROJ-123"]
        assert ticket.status == "In Progress"
        assert ticket.assigned_to == "dev_1"
        assert ticket.started is not None

    def test_get_agent_workload(self):
        """Test workload calculation."""
        state = SimulationState()
        state.track_ticket("PROJ-1", "In Progress", "dev_1")
        state.track_ticket("PROJ-2", "In Progress", "dev_1")
        state.track_ticket("PROJ-3", "Done", "dev_1")
        state.track_ticket("PROJ-4", "In Progress", "dev_2")

        assert state.get_agent_workload("dev_1") == 2
        assert state.get_agent_workload("dev_2") == 1
        assert state.get_agent_workload("dev_3") == 0

    def test_reset_daily_counters(self):
        """Test daily counter reset."""
        state = SimulationState()
        state.record_action("agent_1", "comment")
        state.record_action("agent_1", "comment")

        assert state.agents["agent_1"].actions_today == 2

        state.reset_daily_counters()
        assert state.agents["agent_1"].actions_today == 0

    def test_advance_sprint_day(self):
        """Test sprint day advancement."""
        state = SimulationState()
        state.current_sprint.day = 14
        state.current_sprint.name = "Sprint 1"

        state.advance_sprint_day()

        # Should start new sprint
        assert state.current_sprint.day == 1
        assert state.current_sprint.name == "Sprint 2"

    def test_is_new_day(self):
        """Test new day detection."""
        state = SimulationState()
        assert state.is_new_day() is True  # No last_run

        from datetime import datetime
        state.last_run = datetime.utcnow()
        assert state.is_new_day() is False


class TestLoadSaveState:
    """Tests for state persistence."""

    def test_save_and_load_state(self, tmp_path):
        """Test state can be saved and loaded."""
        state_file = tmp_path / "test_state.json"

        state = SimulationState()
        state.record_action("test_agent", "comment", "PROJ-1")
        state.track_ticket("PROJ-1", "In Progress")

        save_state(state, str(state_file))

        loaded = load_state(str(state_file))
        assert loaded.simulation_day == state.simulation_day
        assert "test_agent" in loaded.agents
        assert "PROJ-1" in loaded.active_tickets

    def test_load_nonexistent_creates_new(self, tmp_path):
        """Test loading nonexistent file creates new state."""
        state = load_state(str(tmp_path / "nonexistent.json"))
        assert state.simulation_day == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
