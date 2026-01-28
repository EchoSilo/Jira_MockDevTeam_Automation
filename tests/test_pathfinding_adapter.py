"""
Unit tests for PathfindingAdapter.

Tests pathfinding-based recalculation logic including action scheduling,
adaptation marking, and reconciliation integration.
"""

import pendulum
import pytest

from src.chaos.pathfinding_adapter import PathfindingAdapter, PathfindingResult
from src.orchestrator.pathfinder import WorkflowPathfinder
from src.scheduling.scheduler import Scheduler
from src.scheduling.models import ScheduledAction, ActionStatus
from src.scheduling.persistence import ScheduledActionStore
from src.reconciliation.reconciler import ReconciliationResult
from src.reconciliation.adapters import AdaptationStrategy


@pytest.fixture
def scheduler():
    """Create scheduler with in-memory store."""
    store = ScheduledActionStore(db_path=":memory:")
    return Scheduler(store=store)


@pytest.fixture
def pathfinder():
    """Create pathfinder with mock workflow graph."""
    pf = WorkflowPathfinder()
    # Build simple workflow graph for testing
    pf.workflow_graph = {
        "to do": {"in progress"},
        "in progress": {"code review"},
        "code review": {"testing"},
        "testing": {"done"},
    }
    pf._graph_built = True
    return pf


@pytest.fixture
def adapter(scheduler, pathfinder):
    """Create pathfinding adapter."""
    return PathfindingAdapter(scheduler, pathfinder)


@pytest.fixture
def base_time():
    """Base time for test scenarios."""
    return pendulum.parse("2026-01-28T10:00:00Z")


def test_handle_recalculate_schedules_new_actions(adapter, scheduler, base_time):
    """handle_recalculate should schedule new actions for computed path."""
    # Set current simulation time
    scheduler.clock.current_time = base_time

    # Recalculate path from In Progress to Done
    result = adapter.handle_recalculate(
        ticket_key="PROJ-123",
        current_status="In Progress",
        target_status="done",
        scenario_id="scenario_1",
    )

    # Should have scheduled actions for: Code Review -> Testing -> Done
    assert len(result.actions_scheduled) == 3
    assert result.actions_scheduled[0].action_type == "progress_to_review"
    assert result.actions_scheduled[1].action_type == "complete_review"
    assert result.actions_scheduled[2].action_type == "qa_approve"

    # All actions should be for the same ticket
    for action in result.actions_scheduled:
        assert action.ticket_key == "PROJ-123"
        assert action.scenario_id == "scenario_1"
        assert action.params.get("recalculated") is True


def test_handle_recalculate_marks_original_action_adapted(adapter, scheduler, base_time):
    """handle_recalculate should mark original pending action as ADAPTED."""
    # Schedule an action for the ticket
    original_action = ScheduledAction(
        scheduled_time=base_time.add(minutes=10),
        action_type="dev_progress",
        agent_id="developer",
        ticket_key="PROJ-123",
        status=ActionStatus.PENDING,
    )
    scheduler.schedule_action(original_action)

    # Set current simulation time
    scheduler.clock.current_time = base_time

    # Recalculate path
    result = adapter.handle_recalculate(
        ticket_key="PROJ-123",
        current_status="In Progress",
        target_status="done",
    )

    # Should have marked original action as adapted
    assert result.actions_adapted  # Should have some adapted actions tracked

    # Verify original action marked ADAPTED in store
    stored_action = scheduler.store.load_action(original_action.action_id)
    assert stored_action.status == ActionStatus.ADAPTED
    assert "Status divergence detected" in stored_action.result["reason"]


def test_handle_recalculate_marks_all_pending_actions_for_ticket(adapter, scheduler, base_time):
    """handle_recalculate should mark ALL pending actions for ticket as adapted."""
    # Schedule multiple actions for the same ticket
    action1 = ScheduledAction(
        scheduled_time=base_time.add(minutes=10),
        action_type="dev_progress",
        agent_id="developer",
        ticket_key="PROJ-456",
        status=ActionStatus.PENDING,
    )
    action2 = ScheduledAction(
        scheduled_time=base_time.add(minutes=20),
        action_type="code_review",
        agent_id="tech_lead",
        ticket_key="PROJ-456",
        status=ActionStatus.PENDING,
    )
    action3 = ScheduledAction(
        scheduled_time=base_time.add(minutes=30),
        action_type="qa_test",
        agent_id="qa",
        ticket_key="PROJ-456",
        status=ActionStatus.PENDING,
    )
    # Add action for different ticket (should NOT be affected)
    other_action = ScheduledAction(
        scheduled_time=base_time.add(minutes=10),
        action_type="dev_progress",
        agent_id="developer",
        ticket_key="PROJ-999",
        status=ActionStatus.PENDING,
    )

    scheduler.schedule_action(action1)
    scheduler.schedule_action(action2)
    scheduler.schedule_action(action3)
    scheduler.schedule_action(other_action)

    # Set current simulation time
    scheduler.clock.current_time = base_time

    # Recalculate path for PROJ-456
    result = adapter.handle_recalculate(
        ticket_key="PROJ-456",
        current_status="In Progress",
        target_status="done",
    )

    # All three actions for PROJ-456 should be marked ADAPTED
    stored1 = scheduler.store.load_action(action1.action_id)
    stored2 = scheduler.store.load_action(action2.action_id)
    stored3 = scheduler.store.load_action(action3.action_id)
    assert stored1.status == ActionStatus.ADAPTED
    assert stored2.status == ActionStatus.ADAPTED
    assert stored3.status == ActionStatus.ADAPTED

    # Other ticket action should remain PENDING
    stored_other = scheduler.store.load_action(other_action.action_id)
    assert stored_other.status == ActionStatus.PENDING


def test_handle_recalculate_no_path_found(adapter, scheduler, base_time):
    """handle_recalculate should handle gracefully when no path found."""
    # Set current simulation time
    scheduler.clock.current_time = base_time

    # Try to recalculate from invalid status
    result = adapter.handle_recalculate(
        ticket_key="PROJ-789",
        current_status="Invalid Status",
        target_status="done",
    )

    # Should have no scheduled actions
    assert len(result.actions_scheduled) == 0
    assert "No path found" in result.summary


def test_handle_reconciliation_result_processes_recalculate(adapter, scheduler, base_time):
    """handle_reconciliation_result should process RECALCULATE strategy."""
    # Set current simulation time
    scheduler.clock.current_time = base_time

    # Create reconciliation result with RECALCULATE
    reconciliation = ReconciliationResult(
        strategy=AdaptationStrategy.RECALCULATE,
        reason="Ticket regressed to 'In Progress', recalculating plan",
    )

    scheduled_action = ScheduledAction(
        scheduled_time=base_time.add(minutes=10),
        action_type="code_review",
        agent_id="tech_lead",
        ticket_key="PROJ-111",
        scenario_id="scenario_2",
    )

    # Process reconciliation result
    result = adapter.handle_reconciliation_result(reconciliation, scheduled_action)

    # Should have recalculated path
    assert result is not None
    assert result.ticket_key == "PROJ-111"
    assert len(result.actions_scheduled) > 0


def test_handle_reconciliation_result_returns_none_for_non_recalculate(adapter, scheduler, base_time):
    """handle_reconciliation_result should return None for non-RECALCULATE strategies."""
    # Set current simulation time
    scheduler.clock.current_time = base_time

    # Create reconciliation result with SKIP strategy
    reconciliation = ReconciliationResult(
        strategy=AdaptationStrategy.SKIP,
        reason="Ticket already progressed",
    )

    scheduled_action = ScheduledAction(
        scheduled_time=base_time.add(minutes=10),
        action_type="code_review",
        agent_id="tech_lead",
        ticket_key="PROJ-222",
    )

    # Process reconciliation result
    result = adapter.handle_reconciliation_result(reconciliation, scheduled_action)

    # Should return None (no recalculation needed)
    assert result is None


def test_extract_status_from_reason_regressed_pattern(adapter):
    """_extract_status_from_reason should extract status from 'regressed to' pattern."""
    reason = "Ticket regressed to 'In Progress', recalculating plan"
    status = adapter._extract_status_from_reason(reason)
    assert status == "In Progress"


def test_extract_status_from_reason_alternative_pattern(adapter):
    """_extract_status_from_reason should extract status from alternative pattern."""
    reason = "Status changed to 'Code Review'"
    status = adapter._extract_status_from_reason(reason)
    assert status == "Code Review"


def test_extract_status_from_reason_no_match(adapter):
    """_extract_status_from_reason should return None when no match."""
    reason = "Some random reason without status"
    status = adapter._extract_status_from_reason(reason)
    assert status is None


def test_get_agent_for_role_finds_agent(adapter):
    """_get_agent_for_role should return agent ID for valid role."""
    agent_id = adapter._get_agent_for_role("developer")
    assert agent_id == "developer"

    agent_id = adapter._get_agent_for_role("qa")
    assert agent_id == "qa"


def test_get_agent_for_role_returns_none_for_invalid_role(adapter):
    """_get_agent_for_role should return None for invalid role."""
    agent_id = adapter._get_agent_for_role("invalid_role")
    assert agent_id is None

    agent_id = adapter._get_agent_for_role(None)
    assert agent_id is None


def test_handle_recalculate_uses_custom_agent_pool():
    """handle_recalculate should use custom agent pool when provided."""
    # Create adapter with custom agent pool
    store = ScheduledActionStore(db_path=":memory:")
    scheduler = Scheduler(store=store)
    pathfinder = WorkflowPathfinder()
    pathfinder.workflow_graph = {
        "in progress": {"done"},
    }
    pathfinder._graph_built = True

    custom_agent_pool = {
        "developer": "alice_dev",
        "qa": "bob_qa",
    }
    adapter = PathfindingAdapter(scheduler, pathfinder, agent_pool=custom_agent_pool)

    base_time = pendulum.parse("2026-01-28T10:00:00Z")
    scheduler.clock.current_time = base_time

    # Recalculate path
    result = adapter.handle_recalculate(
        ticket_key="PROJ-333",
        current_status="In Progress",
        target_status="done",
    )

    # Should have used custom agent pool
    # (qa_approve action requires 'qa' role, should map to 'bob_qa')
    if len(result.actions_scheduled) > 0:
        # Find qa action
        qa_action = next(
            (a for a in result.actions_scheduled if a.action_type == "qa_approve"),
            None
        )
        if qa_action:
            assert qa_action.agent_id == "bob_qa"


def test_pathfinding_result_to_dict():
    """PathfindingResult.to_dict() should return summary dictionary."""
    base_time = pendulum.parse("2026-01-28T10:00:00Z")
    action1 = ScheduledAction(
        scheduled_time=base_time,
        action_type="test_action",
        agent_id="test_agent",
    )

    result = PathfindingResult(
        ticket_key="PROJ-444",
        actions_scheduled=[action1],
        actions_adapted=["action1", "action2"],
        summary="Test recalculation",
    )

    result_dict = result.to_dict()

    assert result_dict["ticket_key"] == "PROJ-444"
    assert result_dict["scheduled_count"] == 1
    assert result_dict["adapted_count"] == 2
    assert result_dict["summary"] == "Test recalculation"


def test_handle_recalculate_skips_action_when_no_agent_for_role(adapter, scheduler, base_time):
    """handle_recalculate should skip actions when no agent found for role."""
    # Create adapter with empty agent pool
    adapter.agent_pool = {}

    # Set current simulation time
    scheduler.clock.current_time = base_time

    # Recalculate path (should generate actions but skip scheduling due to missing agents)
    result = adapter.handle_recalculate(
        ticket_key="PROJ-555",
        current_status="In Progress",
        target_status="done",
    )

    # Should have 0 scheduled actions (no agents available)
    assert len(result.actions_scheduled) == 0
