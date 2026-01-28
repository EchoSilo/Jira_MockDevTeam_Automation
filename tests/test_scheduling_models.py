"""Tests for ScheduledAction model and ActionStatus enum."""

import pendulum
import pytest

from src.scheduling.models import ActionStatus, ScheduledAction


class TestActionStatus:
    """Test ActionStatus enum."""

    def test_action_status_values(self):
        """Test that all expected status values exist."""
        assert ActionStatus.PENDING
        assert ActionStatus.READY
        assert ActionStatus.COMPLETED
        assert ActionStatus.SKIPPED
        assert ActionStatus.ADAPTED


class TestScheduledAction:
    """Test ScheduledAction dataclass."""

    @pytest.fixture
    def base_time(self):
        """Base time for testing."""
        return pendulum.parse("2026-01-28T10:00:00Z")

    @pytest.fixture
    def action(self, base_time):
        """Create a basic ScheduledAction for testing."""
        return ScheduledAction(
            scheduled_time=base_time,
            action_type="status_transition",
            agent_id="agent_1",
            ticket_key="PROJ-123",
        )

    def test_scheduled_action_creation(self, base_time):
        """Test creating a ScheduledAction with required fields."""
        action = ScheduledAction(
            scheduled_time=base_time,
            action_type="status_transition",
            agent_id="agent_1",
            ticket_key="PROJ-123",
        )
        assert action.scheduled_time == base_time
        assert action.action_type == "status_transition"
        assert action.agent_id == "agent_1"
        assert action.ticket_key == "PROJ-123"
        assert action.status == ActionStatus.PENDING
        assert action.window_minutes == 30
        assert action.action_id is not None
        assert len(action.action_id) == 8

    def test_scheduled_action_with_optional_fields(self, base_time):
        """Test creating a ScheduledAction with optional fields."""
        action = ScheduledAction(
            scheduled_time=base_time,
            action_type="add_comment",
            agent_id="agent_2",
            ticket_key="PROJ-456",
            scenario_id="scenario_1",
            window_minutes=60,
            expected_status="In Progress",
            expected_assignee="agent_1",
            params={"comment": "Test comment"},
        )
        assert action.scenario_id == "scenario_1"
        assert action.window_minutes == 60
        assert action.expected_status == "In Progress"
        assert action.expected_assignee == "agent_1"
        assert action.params == {"comment": "Test comment"}

    def test_is_due_within_window(self, action, base_time):
        """Test is_due returns True when current time is within execution window."""
        # Within window (15 minutes after scheduled time)
        current_time = base_time.add(minutes=15)
        assert action.is_due(current_time) is True

    def test_is_due_at_scheduled_time(self, action, base_time):
        """Test is_due returns True at exact scheduled time."""
        assert action.is_due(base_time) is True

    def test_is_due_at_window_end(self, action, base_time):
        """Test is_due returns True at end of window."""
        # Exactly at window end (30 minutes after scheduled time)
        current_time = base_time.add(minutes=30)
        assert action.is_due(current_time) is True

    def test_is_due_before_window(self, action, base_time):
        """Test is_due returns False when current time is before scheduled time."""
        current_time = base_time.subtract(minutes=1)
        assert action.is_due(current_time) is False

    def test_is_due_after_window(self, action, base_time):
        """Test is_due returns False when current time is after window."""
        current_time = base_time.add(minutes=31)
        assert action.is_due(current_time) is False

    def test_is_overdue_before_scheduled(self, action, base_time):
        """Test is_overdue returns False before scheduled time."""
        current_time = base_time.subtract(minutes=1)
        assert action.is_overdue(current_time) is False

    def test_is_overdue_within_window(self, action, base_time):
        """Test is_overdue returns False within execution window."""
        current_time = base_time.add(minutes=15)
        assert action.is_overdue(current_time) is False

    def test_is_overdue_at_window_end(self, action, base_time):
        """Test is_overdue returns False at exact window end."""
        current_time = base_time.add(minutes=30)
        assert action.is_overdue(current_time) is False

    def test_is_overdue_after_window(self, action, base_time):
        """Test is_overdue returns True after execution window."""
        current_time = base_time.add(minutes=31)
        assert action.is_overdue(current_time) is True

    def test_mark_completed(self, action, base_time):
        """Test mark_completed sets status and executed_at."""
        result = {"status": "Done", "transition_id": "123"}

        before_time = pendulum.now("UTC")
        action.mark_completed(result)
        after_time = pendulum.now("UTC")

        assert action.status == ActionStatus.COMPLETED
        assert action.executed_at is not None
        assert before_time <= action.executed_at <= after_time
        assert action.result == result

    def test_mark_skipped(self, action):
        """Test mark_skipped sets status and result with reason."""
        reason = "Ticket already in target status"
        action.mark_skipped(reason)

        assert action.status == ActionStatus.SKIPPED
        assert action.result == {"reason": reason}

    def test_action_ordering_by_scheduled_time(self, base_time):
        """Test that actions are ordered by scheduled_time only."""
        action1 = ScheduledAction(
            scheduled_time=base_time.add(hours=2),
            action_type="type_a",
            agent_id="agent_1",
            ticket_key="PROJ-111",
        )
        action2 = ScheduledAction(
            scheduled_time=base_time.add(hours=1),
            action_type="type_b",
            agent_id="agent_2",
            ticket_key="PROJ-222",
        )
        action3 = ScheduledAction(
            scheduled_time=base_time.add(hours=3),
            action_type="type_c",
            agent_id="agent_3",
            ticket_key="PROJ-333",
        )

        # Sort and verify order
        actions = sorted([action1, action2, action3])
        assert actions[0].ticket_key == "PROJ-222"  # Earliest (1 hour)
        assert actions[1].ticket_key == "PROJ-111"  # Middle (2 hours)
        assert actions[2].ticket_key == "PROJ-333"  # Latest (3 hours)

    def test_custom_window_minutes(self, base_time):
        """Test action with custom window_minutes."""
        action = ScheduledAction(
            scheduled_time=base_time,
            action_type="status_transition",
            agent_id="agent_1",
            ticket_key="PROJ-123",
            window_minutes=60,
        )

        # Within 60-minute window
        assert action.is_due(base_time.add(minutes=45)) is True
        assert action.is_due(base_time.add(minutes=60)) is True
        assert action.is_due(base_time.add(minutes=61)) is False

        # Overdue after 60 minutes
        assert action.is_overdue(base_time.add(minutes=60)) is False
        assert action.is_overdue(base_time.add(minutes=61)) is True

    def test_action_id_uniqueness(self, base_time):
        """Test that each action gets a unique action_id."""
        action1 = ScheduledAction(
            scheduled_time=base_time,
            action_type="type_a",
            agent_id="agent_1",
            ticket_key="PROJ-123",
        )
        action2 = ScheduledAction(
            scheduled_time=base_time,
            action_type="type_a",
            agent_id="agent_1",
            ticket_key="PROJ-123",
        )

        assert action1.action_id != action2.action_id

    def test_default_params_is_empty_dict(self, action):
        """Test that params defaults to empty dict."""
        assert action.params == {}
        assert isinstance(action.params, dict)

    def test_executed_at_initially_none(self, action):
        """Test that executed_at is initially None."""
        assert action.executed_at is None

    def test_result_initially_none(self, action):
        """Test that result is initially None."""
        assert action.result is None
