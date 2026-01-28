"""Tests for TickExecutor."""

import sys
import pytest
from unittest.mock import Mock, MagicMock

import pendulum

# Mock all external dependencies before any imports
sys.modules['jira'] = MagicMock()
sys.modules['jira.resources'] = MagicMock()
sys.modules['crewai'] = MagicMock()
sys.modules['litellm'] = MagicMock()
sys.modules['anthropic'] = MagicMock()
sys.modules['fastapi'] = MagicMock()

from src.orchestrator.tick_executor import TickExecutor
from src.scheduling import Scheduler, ScheduledAction, ActionStatus
from src.scheduling.persistence import ScheduledActionStore
from src.scheduling.virtual_clock import VirtualClock


@pytest.fixture
def mock_jira():
    """Create mock Jira client."""
    jira = Mock()
    jira.get_issue.return_value = Mock(
        fields=Mock(
            status=Mock(name="To Do"),
            assignee=None,
        )
    )
    return jira


@pytest.fixture
def scheduler(tmp_path):
    """Create scheduler with temp database."""
    store = ScheduledActionStore(str(tmp_path / "scheduler.db"))
    clock = VirtualClock(pendulum.datetime(2026, 2, 4, 10, 0, tz="UTC"))
    return Scheduler(store=store, virtual_clock=clock)


@pytest.fixture
def executor(scheduler, mock_jira):
    """Create TickExecutor."""
    return TickExecutor(scheduler, mock_jira)


class TestTickExecutor:
    def test_execute_tick_with_due_actions(self, executor, scheduler):
        """Test executing due actions."""
        # Schedule action for current time
        action = ScheduledAction(
            scheduled_time=scheduler.get_simulation_time(),
            action_type="pick_up_task",
            agent_id="dev_1",
            ticket_key="PROJ-100",
        )
        scheduler.schedule_action(action)

        # Mock action executor (simulating ScenarioOrchestrator._execute_action)
        mock_executor = Mock(return_value={"success": True})
        mock_state = Mock()

        result = executor.execute_tick(mock_state, mock_executor)

        assert mock_executor.called
        assert result["metrics"]["executed"] == 1

    def test_overdue_actions_skipped(self, executor, scheduler):
        """Test that overdue actions are marked skipped."""
        # Schedule action for past time
        past_time = scheduler.get_simulation_time().subtract(hours=2)
        action = ScheduledAction(
            scheduled_time=past_time,
            action_type="pick_up_task",
            agent_id="dev_1",
            ticket_key="PROJ-100",
            window_minutes=30,
        )
        scheduler.schedule_action(action)

        mock_executor = Mock()
        mock_state = Mock()

        result = executor.execute_tick(mock_state, mock_executor)

        assert result["metrics"]["overdue_skipped"] == 1
        # Action should not be executed
        assert not mock_executor.called

    def test_idempotency_prevents_duplicate(self, executor, scheduler):
        """Test that duplicate actions are skipped."""
        action = ScheduledAction(
            scheduled_time=scheduler.get_simulation_time(),
            action_type="pick_up_task",
            agent_id="dev_1",
            ticket_key="PROJ-100",
        )
        scheduler.schedule_action(action)

        # First execution
        mock_executor = Mock(return_value={"success": True})
        mock_state = Mock()
        executor.execute_tick(mock_state, mock_executor)

        # Schedule same action again (simulate restart)
        action2 = ScheduledAction(
            scheduled_time=scheduler.get_simulation_time(),
            action_type="pick_up_task",
            agent_id="dev_1",
            ticket_key="PROJ-100",
        )
        scheduler.schedule_action(action2)

        # Second execution should skip
        result = executor.execute_tick(mock_state, mock_executor)
        # First call happened, second should skip
        assert mock_executor.call_count == 1

    def test_simulation_time_advances(self, executor, scheduler):
        """Test that simulation time advances each tick."""
        initial_time = scheduler.get_simulation_time()

        mock_executor = Mock(return_value={"success": True})
        mock_state = Mock()

        result = executor.execute_tick(mock_state, mock_executor)

        # Default tick is 0.75 hours (45 min)
        expected_next = initial_time.add(minutes=45)
        assert scheduler.get_simulation_time() == expected_next

    def test_max_actions_per_tick(self, executor, scheduler):
        """Test max actions per tick limit."""
        executor.max_actions_per_tick = 2

        # Schedule 5 actions
        for i in range(5):
            action = ScheduledAction(
                scheduled_time=scheduler.get_simulation_time(),
                action_type="pick_up_task",
                agent_id=f"dev_{i}",
                ticket_key=f"PROJ-{i}",
            )
            scheduler.schedule_action(action)

        mock_executor = Mock(return_value={"success": True})
        mock_state = Mock()

        result = executor.execute_tick(mock_state, mock_executor)

        # Should only execute 2
        assert mock_executor.call_count == 2

    def test_failed_action_marked_skipped(self, executor, scheduler):
        """Test that failed actions are marked skipped."""
        action = ScheduledAction(
            scheduled_time=scheduler.get_simulation_time(),
            action_type="pick_up_task",
            agent_id="dev_1",
            ticket_key="PROJ-100",
        )
        scheduler.schedule_action(action)

        # Executor returns error
        mock_executor = Mock(return_value={"error": "test error"})
        mock_state = Mock()

        result = executor.execute_tick(mock_state, mock_executor)

        assert result["metrics"]["skipped"] == 1
        assert result["metrics"]["executed"] == 0

    def test_metrics_reset_each_tick(self, executor, scheduler):
        """Test that metrics reset each tick."""
        mock_executor = Mock(return_value={"success": True})
        mock_state = Mock()

        # First tick
        executor.execute_tick(mock_state, mock_executor)

        # Second tick should have fresh metrics
        result = executor.execute_tick(mock_state, mock_executor)

        assert result["metrics"]["executed"] == 0  # No new actions
        assert result["metrics"]["skipped"] == 0

    def test_action_dict_format_matches_orchestrator(self, executor, scheduler):
        """Test that action_dict passed to executor matches ScenarioOrchestrator format."""
        action = ScheduledAction(
            scheduled_time=scheduler.get_simulation_time(),
            action_type="transition_status",
            agent_id="dev_1",
            ticket_key="PROJ-100",
            scenario_id="scenario_123",
            params={"target_status": "In Progress"},
        )
        scheduler.schedule_action(action)

        captured_dict = None
        def capture_executor(action_dict, state):
            nonlocal captured_dict
            captured_dict = action_dict
            return {"success": True}

        mock_state = Mock()
        executor.execute_tick(mock_state, capture_executor)

        # Verify dict format matches what ScenarioOrchestrator expects
        assert captured_dict["type"] == "transition_status"
        assert captured_dict["ticket_key"] == "PROJ-100"
        assert captured_dict["agent_id"] == "dev_1"
        assert captured_dict["scenario_id"] == "scenario_123"
        assert captured_dict["target_status"] == "In Progress"
