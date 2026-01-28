"""Tests for scheduled action persistence."""

import pendulum
import pytest

from src.scheduling.models import ActionStatus, ScheduledAction
from src.scheduling.persistence import ScheduledActionStore


@pytest.fixture
def store(tmp_path):
    """Create a test store with temporary database."""
    db_path = tmp_path / "test_scheduler.db"
    return ScheduledActionStore(str(db_path))


@pytest.fixture
def sample_action():
    """Create a sample scheduled action for testing."""
    return ScheduledAction(
        action_id="test123",
        scheduled_time=pendulum.now("UTC").add(hours=1),
        action_type="transition_status",
        agent_id="dev-alice",
        ticket_key="PROJ-123",
        scenario_id="scenario-1",
        window_minutes=30,
        expected_status="To Do",
        expected_assignee="alice@example.com",
        params={"to_status": "In Progress"},
    )


def test_save_and_load_action(store, sample_action):
    """Test saving and loading a scheduled action."""
    # Save action
    store.save_action(sample_action)

    # Load pending actions
    actions = store.load_pending_actions()

    # Verify action was saved and loaded correctly
    assert len(actions) == 1
    loaded = actions[0]
    assert loaded.action_id == sample_action.action_id
    assert loaded.action_type == sample_action.action_type
    assert loaded.agent_id == sample_action.agent_id
    assert loaded.ticket_key == sample_action.ticket_key
    assert loaded.scenario_id == sample_action.scenario_id
    assert loaded.window_minutes == sample_action.window_minutes
    assert loaded.expected_status == sample_action.expected_status
    assert loaded.expected_assignee == sample_action.expected_assignee
    assert loaded.status == ActionStatus.PENDING
    assert loaded.params == sample_action.params
    # Verify timestamps are close (within 1 second)
    assert abs((loaded.scheduled_time - sample_action.scheduled_time).total_seconds()) < 1


def test_update_status(store, sample_action):
    """Test updating action status with result."""
    # Save action
    store.save_action(sample_action)

    # Update status to completed
    result = {"ticket_status": "In Progress", "comment_id": "10001"}
    executed_at = pendulum.now("UTC")
    store.update_status(
        sample_action.action_id,
        ActionStatus.COMPLETED,
        result=result,
        executed_at=executed_at,
    )

    # Load action and verify status update
    loaded = store.get_action(sample_action.action_id)
    assert loaded is not None
    assert loaded.status == ActionStatus.COMPLETED
    assert loaded.result == result
    assert loaded.executed_at is not None
    assert abs((loaded.executed_at - executed_at).total_seconds()) < 1


def test_load_pending_only(store):
    """Test that load_pending_actions returns only pending actions."""
    # Create and save 3 actions with different statuses
    now = pendulum.now("UTC")

    action1 = ScheduledAction(
        action_id="pending1",
        scheduled_time=now.add(hours=1),
        action_type="transition",
        agent_id="dev-alice",
        ticket_key="PROJ-1",
        status=ActionStatus.PENDING,
    )

    action2 = ScheduledAction(
        action_id="pending2",
        scheduled_time=now.add(hours=2),
        action_type="transition",
        agent_id="dev-bob",
        ticket_key="PROJ-2",
        status=ActionStatus.PENDING,
    )

    action3 = ScheduledAction(
        action_id="completed1",
        scheduled_time=now.add(hours=3),
        action_type="transition",
        agent_id="dev-charlie",
        ticket_key="PROJ-3",
        status=ActionStatus.COMPLETED,
        executed_at=now,
    )

    store.save_action(action1)
    store.save_action(action2)
    store.save_action(action3)

    # Load pending actions
    pending = store.load_pending_actions()

    # Verify only 2 pending actions returned
    assert len(pending) == 2
    pending_ids = {action.action_id for action in pending}
    assert pending_ids == {"pending1", "pending2"}


def test_cleanup_old_actions(store):
    """Test cleanup of old completed actions."""
    now = pendulum.now("UTC")
    old_time = now.subtract(hours=50)  # Older than 48 hours

    # Create old completed action
    old_action = ScheduledAction(
        action_id="old_completed",
        scheduled_time=old_time,
        action_type="transition",
        agent_id="dev-alice",
        ticket_key="PROJ-1",
        status=ActionStatus.COMPLETED,
        executed_at=old_time,
    )

    # Create recent completed action
    recent_action = ScheduledAction(
        action_id="recent_completed",
        scheduled_time=now.subtract(hours=1),
        action_type="transition",
        agent_id="dev-bob",
        ticket_key="PROJ-2",
        status=ActionStatus.COMPLETED,
        executed_at=now.subtract(hours=1),
    )

    # Create old skipped action
    old_skipped = ScheduledAction(
        action_id="old_skipped",
        scheduled_time=old_time,
        action_type="transition",
        agent_id="dev-charlie",
        ticket_key="PROJ-3",
        status=ActionStatus.SKIPPED,
        executed_at=old_time,
    )

    store.save_action(old_action)
    store.save_action(recent_action)
    store.save_action(old_skipped)

    # Cleanup actions older than 48 hours
    deleted_count = store.cleanup_old_actions(max_age_hours=48)

    # Verify 2 old actions deleted (completed and skipped)
    assert deleted_count == 2

    # Verify recent action still exists
    recent = store.get_action("recent_completed")
    assert recent is not None

    # Verify old actions are gone
    assert store.get_action("old_completed") is None
    assert store.get_action("old_skipped") is None


def test_get_action(store, sample_action):
    """Test retrieving a specific action by ID."""
    # Save action
    store.save_action(sample_action)

    # Retrieve by ID
    loaded = store.get_action(sample_action.action_id)

    # Verify action matches
    assert loaded is not None
    assert loaded.action_id == sample_action.action_id
    assert loaded.action_type == sample_action.action_type
    assert loaded.ticket_key == sample_action.ticket_key


def test_get_action_not_found(store):
    """Test get_action returns None for non-existent action."""
    loaded = store.get_action("nonexistent")
    assert loaded is None


def test_actions_sorted_by_scheduled_time(store):
    """Test that pending actions are returned in chronological order."""
    now = pendulum.now("UTC")

    # Create 3 actions with different scheduled times
    action1 = ScheduledAction(
        action_id="action1",
        scheduled_time=now.add(hours=3),
        action_type="transition",
        agent_id="dev-alice",
        ticket_key="PROJ-1",
    )

    action2 = ScheduledAction(
        action_id="action2",
        scheduled_time=now.add(hours=1),
        action_type="transition",
        agent_id="dev-bob",
        ticket_key="PROJ-2",
    )

    action3 = ScheduledAction(
        action_id="action3",
        scheduled_time=now.add(hours=2),
        action_type="transition",
        agent_id="dev-charlie",
        ticket_key="PROJ-3",
    )

    # Save in non-chronological order
    store.save_action(action1)
    store.save_action(action2)
    store.save_action(action3)

    # Load pending actions
    pending = store.load_pending_actions()

    # Verify chronological order
    assert len(pending) == 3
    assert pending[0].action_id == "action2"  # Earliest (now + 1h)
    assert pending[1].action_id == "action3"  # Middle (now + 2h)
    assert pending[2].action_id == "action1"  # Latest (now + 3h)


def test_save_action_updates_existing(store, sample_action):
    """Test that saving an action with same ID updates it."""
    # Save action
    store.save_action(sample_action)

    # Modify and save again
    sample_action.expected_status = "In Progress"
    sample_action.params = {"new_param": "value"}
    store.save_action(sample_action)

    # Verify only one action exists with updated values
    pending = store.load_pending_actions()
    assert len(pending) == 1
    assert pending[0].expected_status == "In Progress"
    assert pending[0].params == {"new_param": "value"}


def test_save_action_with_null_fields(store):
    """Test saving action with null optional fields."""
    action = ScheduledAction(
        action_id="minimal",
        scheduled_time=pendulum.now("UTC").add(hours=1),
        action_type="transition",
        agent_id="dev-alice",
        ticket_key="PROJ-1",
        scenario_id=None,
        expected_status=None,
        expected_assignee=None,
    )

    store.save_action(action)
    loaded = store.get_action("minimal")

    assert loaded is not None
    assert loaded.scenario_id is None
    assert loaded.expected_status is None
    assert loaded.expected_assignee is None


def test_database_persistence_across_instances(tmp_path):
    """Test that data persists across store instances."""
    db_path = tmp_path / "persistent.db"

    # Create action with first instance
    store1 = ScheduledActionStore(str(db_path))
    action = ScheduledAction(
        action_id="persist",
        scheduled_time=pendulum.now("UTC").add(hours=1),
        action_type="transition",
        agent_id="dev-alice",
        ticket_key="PROJ-1",
    )
    store1.save_action(action)

    # Load with second instance
    store2 = ScheduledActionStore(str(db_path))
    loaded = store2.get_action("persist")

    assert loaded is not None
    assert loaded.action_id == "persist"
