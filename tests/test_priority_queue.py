"""Tests for ActionPriorityQueue."""

import pendulum
import pytest

from src.scheduling.models import ActionStatus, ScheduledAction
from src.scheduling.priority_queue import ActionPriorityQueue


class TestActionPriorityQueue:
    """Test ActionPriorityQueue heap-based priority queue."""

    @pytest.fixture
    def base_time(self):
        """Base time for testing."""
        return pendulum.parse("2026-01-28T10:00:00Z")

    @pytest.fixture
    def queue(self):
        """Create an empty priority queue."""
        return ActionPriorityQueue()

    @pytest.fixture
    def actions(self, base_time):
        """Create sample actions for testing."""
        return [
            ScheduledAction(
                scheduled_time=base_time.add(hours=2),
                action_type="status_transition",
                agent_id="agent_1",
                ticket_key="PROJ-111",
            ),
            ScheduledAction(
                scheduled_time=base_time.add(hours=1),
                action_type="add_comment",
                agent_id="agent_2",
                ticket_key="PROJ-222",
            ),
            ScheduledAction(
                scheduled_time=base_time.add(hours=3),
                action_type="log_work",
                agent_id="agent_3",
                ticket_key="PROJ-333",
            ),
        ]

    def test_empty_queue_size(self, queue):
        """Test that new queue has size 0."""
        assert queue.size() == 0

    def test_empty_queue_is_empty(self, queue):
        """Test that new queue is_empty returns True."""
        assert queue.is_empty() is True

    def test_push_increases_size(self, queue, actions):
        """Test that push increases queue size."""
        queue.push(actions[0])
        assert queue.size() == 1

        queue.push(actions[1])
        assert queue.size() == 2

    def test_push_updates_is_empty(self, queue, actions):
        """Test that push updates is_empty state."""
        assert queue.is_empty() is True
        queue.push(actions[0])
        assert queue.is_empty() is False

    def test_peek_empty_queue(self, queue):
        """Test that peek on empty queue returns None."""
        assert queue.peek() is None

    def test_peek_returns_earliest_action(self, queue, actions):
        """Test that peek returns action with earliest scheduled_time."""
        queue.push(actions[0])  # 2 hours
        queue.push(actions[1])  # 1 hour (earliest)
        queue.push(actions[2])  # 3 hours

        earliest = queue.peek()
        assert earliest is not None
        assert earliest.ticket_key == "PROJ-222"  # 1 hour action

    def test_peek_does_not_remove(self, queue, actions):
        """Test that peek does not remove action from queue."""
        queue.push(actions[0])
        queue.push(actions[1])

        size_before = queue.size()
        queue.peek()
        assert queue.size() == size_before

    def test_pop_empty_queue(self, queue):
        """Test that pop on empty queue returns None."""
        assert queue.pop() is None

    def test_pop_returns_earliest_action(self, queue, actions):
        """Test that pop returns action with earliest scheduled_time."""
        queue.push(actions[0])  # 2 hours
        queue.push(actions[1])  # 1 hour (earliest)
        queue.push(actions[2])  # 3 hours

        earliest = queue.pop()
        assert earliest is not None
        assert earliest.ticket_key == "PROJ-222"  # 1 hour action

    def test_pop_removes_action(self, queue, actions):
        """Test that pop removes action from queue."""
        queue.push(actions[0])
        queue.push(actions[1])

        size_before = queue.size()
        queue.pop()
        assert queue.size() == size_before - 1

    def test_pop_order(self, queue, actions):
        """Test that pop returns actions in scheduled_time order."""
        queue.push(actions[0])  # 2 hours
        queue.push(actions[1])  # 1 hour
        queue.push(actions[2])  # 3 hours

        first = queue.pop()
        second = queue.pop()
        third = queue.pop()

        assert first.ticket_key == "PROJ-222"   # 1 hour
        assert second.ticket_key == "PROJ-111"  # 2 hours
        assert third.ticket_key == "PROJ-333"   # 3 hours

    def test_get_due_actions_empty_queue(self, queue, base_time):
        """Test get_due_actions on empty queue returns empty list."""
        due_actions = queue.get_due_actions(base_time)
        assert due_actions == []

    def test_get_due_actions_returns_pending_within_window(self, queue, base_time):
        """Test get_due_actions returns only PENDING actions within window."""
        action1 = ScheduledAction(
            scheduled_time=base_time,
            action_type="type_a",
            agent_id="agent_1",
            ticket_key="PROJ-111",
        )
        action2 = ScheduledAction(
            scheduled_time=base_time.add(minutes=10),
            action_type="type_b",
            agent_id="agent_2",
            ticket_key="PROJ-222",
        )
        action3 = ScheduledAction(
            scheduled_time=base_time.add(hours=2),
            action_type="type_c",
            agent_id="agent_3",
            ticket_key="PROJ-333",
        )

        queue.push(action1)
        queue.push(action2)
        queue.push(action3)

        # Check at base_time + 20 minutes (action1 and action2 are due)
        current_time = base_time.add(minutes=20)
        due_actions = queue.get_due_actions(current_time)

        assert len(due_actions) == 2
        assert due_actions[0].ticket_key == "PROJ-111"
        assert due_actions[1].ticket_key == "PROJ-222"

    def test_get_due_actions_excludes_completed(self, queue, base_time):
        """Test get_due_actions excludes COMPLETED actions."""
        action1 = ScheduledAction(
            scheduled_time=base_time,
            action_type="type_a",
            agent_id="agent_1",
            ticket_key="PROJ-111",
        )
        action2 = ScheduledAction(
            scheduled_time=base_time.add(minutes=10),
            action_type="type_b",
            agent_id="agent_2",
            ticket_key="PROJ-222",
        )

        # Mark action1 as completed
        action1.mark_completed({"status": "Done"})

        queue.push(action1)
        queue.push(action2)

        current_time = base_time.add(minutes=20)
        due_actions = queue.get_due_actions(current_time)

        # Only action2 should be returned (action1 is COMPLETED)
        assert len(due_actions) == 1
        assert due_actions[0].ticket_key == "PROJ-222"

    def test_get_due_actions_excludes_skipped(self, queue, base_time):
        """Test get_due_actions excludes SKIPPED actions."""
        action1 = ScheduledAction(
            scheduled_time=base_time,
            action_type="type_a",
            agent_id="agent_1",
            ticket_key="PROJ-111",
        )
        action2 = ScheduledAction(
            scheduled_time=base_time.add(minutes=10),
            action_type="type_b",
            agent_id="agent_2",
            ticket_key="PROJ-222",
        )

        # Mark action1 as skipped
        action1.mark_skipped("Already done")

        queue.push(action1)
        queue.push(action2)

        current_time = base_time.add(minutes=20)
        due_actions = queue.get_due_actions(current_time)

        # Only action2 should be returned (action1 is SKIPPED)
        assert len(due_actions) == 1
        assert due_actions[0].ticket_key == "PROJ-222"

    def test_get_due_actions_respects_max_actions(self, queue, base_time):
        """Test get_due_actions respects max_actions limit."""
        for i in range(5):
            action = ScheduledAction(
                scheduled_time=base_time.add(minutes=i),
                action_type=f"type_{i}",
                agent_id=f"agent_{i}",
                ticket_key=f"PROJ-{i}",
            )
            queue.push(action)

        current_time = base_time.add(minutes=20)
        due_actions = queue.get_due_actions(current_time, max_actions=3)

        assert len(due_actions) == 3

    def test_get_due_actions_does_not_remove(self, queue, base_time):
        """Test get_due_actions does not remove actions from queue."""
        action = ScheduledAction(
            scheduled_time=base_time,
            action_type="type_a",
            agent_id="agent_1",
            ticket_key="PROJ-111",
        )
        queue.push(action)

        size_before = queue.size()
        queue.get_due_actions(base_time.add(minutes=10))
        assert queue.size() == size_before

    def test_cancel_action_marks_skipped(self, queue, base_time):
        """Test cancel_action marks action as SKIPPED."""
        action = ScheduledAction(
            scheduled_time=base_time,
            action_type="type_a",
            agent_id="agent_1",
            ticket_key="PROJ-111",
        )
        queue.push(action)

        queue.cancel_action(action.action_id)

        # Action still in queue but status is SKIPPED
        assert queue.size() == 1
        peeked = queue.peek()
        assert peeked.status == ActionStatus.SKIPPED

    def test_cancel_action_not_in_queue(self, queue, base_time):
        """Test cancel_action with non-existent action_id does nothing."""
        action = ScheduledAction(
            scheduled_time=base_time,
            action_type="type_a",
            agent_id="agent_1",
            ticket_key="PROJ-111",
        )
        queue.push(action)

        # Cancel non-existent action
        queue.cancel_action("nonexistent")

        # Original action should be unchanged
        assert queue.size() == 1
        peeked = queue.peek()
        assert peeked.status == ActionStatus.PENDING

    def test_canceled_actions_excluded_from_get_due_actions(self, queue, base_time):
        """Test that canceled actions are excluded from get_due_actions."""
        action1 = ScheduledAction(
            scheduled_time=base_time,
            action_type="type_a",
            agent_id="agent_1",
            ticket_key="PROJ-111",
        )
        action2 = ScheduledAction(
            scheduled_time=base_time.add(minutes=10),
            action_type="type_b",
            agent_id="agent_2",
            ticket_key="PROJ-222",
        )

        queue.push(action1)
        queue.push(action2)

        # Cancel action1
        queue.cancel_action(action1.action_id)

        current_time = base_time.add(minutes=20)
        due_actions = queue.get_due_actions(current_time)

        # Only action2 should be returned
        assert len(due_actions) == 1
        assert due_actions[0].ticket_key == "PROJ-222"

    def test_get_due_actions_stops_at_future_actions(self, queue, base_time):
        """Test get_due_actions stops when scheduled_time > current_time."""
        action1 = ScheduledAction(
            scheduled_time=base_time,
            action_type="type_a",
            agent_id="agent_1",
            ticket_key="PROJ-111",
        )
        action2 = ScheduledAction(
            scheduled_time=base_time.add(hours=2),
            action_type="type_b",
            agent_id="agent_2",
            ticket_key="PROJ-222",
        )

        queue.push(action1)
        queue.push(action2)

        # Check at base_time + 10 minutes (only action1 is due)
        current_time = base_time.add(minutes=10)
        due_actions = queue.get_due_actions(current_time)

        assert len(due_actions) == 1
        assert due_actions[0].ticket_key == "PROJ-111"
