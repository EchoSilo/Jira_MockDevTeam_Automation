"""Regression tests for the thrashing convergence fix.

These tests lock in Phase 1 of the stabilization work:

1. The two-field split: ``expected_status`` is always a PRECONDITION (the status a
   ticket must already be in for an action to fire), while ``target_status`` is the
   destination the action moves the ticket TO. The old bug stored the destination in
   ``expected_status``, which guaranteed every pathfinder-scheduled action failed
   validation and triggered an endless RECALCULATE loop.
2. Persistence round-trips the new ``target_status`` column and migrates pre-existing
   databases that predate it.
3. The per-ticket recalculation loop guard in ``TickExecutor`` breaks the thrash even if
   some divergence keeps recurring.
"""

import sqlite3
from unittest.mock import Mock

import pendulum
import pytest

# NOTE: deliberately do NOT stub crewai/jira in sys.modules here. Importing
# pathfinding_adapter pulls in src.orchestrator -> src.tools.jira_tools, which does
# `from crewai.tools import tool`. Shadowing crewai with a MagicMock breaks that
# submodule import. The real packages are installed; test_pathfinding_adapter.py imports
# the same chain with no stubbing, so we follow that pattern.
from src.chaos.pathfinding_adapter import PathfindingAdapter
from src.orchestrator.pathfinder import WorkflowPathfinder
from src.orchestrator.tick_executor import TickExecutor
from src.scheduling.models import ScheduledAction
from src.scheduling.persistence import ScheduledActionStore
from src.scheduling.scheduler import Scheduler
from src.scheduling.virtual_clock import VirtualClock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def base_time():
    return pendulum.datetime(2026, 2, 4, 10, 0, tz="UTC")


@pytest.fixture
def scheduler(base_time):
    store = ScheduledActionStore(db_path=":memory:")
    return Scheduler(store=store, virtual_clock=VirtualClock(base_time))


@pytest.fixture
def pathfinder():
    pf = WorkflowPathfinder()
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
    return PathfindingAdapter(scheduler, pathfinder)


def _regressed_jira(status_name: str) -> Mock:
    """Build a mock Jira client whose issue sits at ``status_name``.

    Note: ``Mock(name=...)`` does NOT set ``.name`` — it names the mock. We set the
    attribute explicitly so ``issue.fields.status.name`` returns the real string.
    """
    status = Mock()
    status.name = status_name
    jira = Mock()
    jira.get_issue.return_value = Mock(fields=Mock(status=status, assignee=None))
    return jira


# ---------------------------------------------------------------------------
# 1. The core poison-removal regression
# ---------------------------------------------------------------------------

def test_recalculated_actions_store_precondition_not_destination(adapter, scheduler, base_time):
    """Each recalculated action's expected_status must be its PRECONDITION.

    Previously expected_status held the destination, so the ticket always sat one step
    behind and validation failed forever. After the fix, action[0]'s precondition is the
    live current status and each subsequent action's precondition is the prior action's
    destination.
    """
    scheduler.clock.current_time = base_time

    result = adapter.handle_recalculate(
        ticket_key="PROJ-123",
        current_status="In Progress",
        target_status="done",
        scenario_id="scenario_1",
    )

    assert len(result.actions_scheduled) >= 1

    prev_target = "In Progress"  # precondition of the first action = live current status
    for action in result.actions_scheduled:
        # expected_status is the precondition — the status the ticket must be in first.
        assert action.expected_status == prev_target, (
            f"{action.action_type}: expected_status should be the precondition "
            f"'{prev_target}', got '{action.expected_status}'"
        )
        # target_status is the destination and must NEVER equal a downstream precondition
        # slot — it is informational only.
        assert action.target_status is not None
        assert action.target_status != action.expected_status
        prev_target = action.target_status


# ---------------------------------------------------------------------------
# 2. Persistence: round-trip + migration
# ---------------------------------------------------------------------------

def test_persistence_roundtrips_target_status(base_time):
    store = ScheduledActionStore(db_path=":memory:")
    action = ScheduledAction(
        scheduled_time=base_time,
        action_type="progress_to_review",
        agent_id="dev_1",
        ticket_key="PROJ-100",
        expected_status="In Progress",   # precondition
        target_status="Code Review",     # destination
    )
    store.save_action(action)

    loaded = store.get_action(action.action_id)
    assert loaded is not None
    assert loaded.expected_status == "In Progress"
    assert loaded.target_status == "Code Review"


def test_persistence_migrates_db_without_target_status(tmp_path, base_time):
    """A DB created before target_status existed must gain the column on open."""
    db_path = str(tmp_path / "legacy.db")

    # Hand-build the OLD schema (no target_status column) and insert a row.
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE scheduled_actions (
            action_id TEXT PRIMARY KEY,
            scheduled_time TEXT NOT NULL,
            action_type TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            ticket_key TEXT NOT NULL,
            scenario_id TEXT,
            window_minutes INTEGER DEFAULT 30,
            expected_status TEXT,
            expected_assignee TEXT,
            status TEXT DEFAULT 'pending',
            params TEXT,
            created_at TEXT NOT NULL,
            executed_at TEXT,
            result TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO scheduled_actions (action_id, scheduled_time, action_type, "
        "agent_id, ticket_key, expected_status, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("abc123", base_time.isoformat(), "pick_up_task", "dev_1", "PROJ-1",
         "To Do", "pending", base_time.isoformat()),
    )
    conn.commit()
    conn.close()

    # Opening the store must run the idempotent migration.
    store = ScheduledActionStore(db_path=db_path)

    # Column now exists and the legacy row loads with target_status defaulted to None.
    loaded = store.get_action("abc123")
    assert loaded is not None
    assert loaded.expected_status == "To Do"
    assert loaded.target_status is None

    # Re-opening must not error (migration is guarded / idempotent).
    ScheduledActionStore(db_path=db_path)


# ---------------------------------------------------------------------------
# 3. The recalculation loop guard
# ---------------------------------------------------------------------------

def test_loop_guard_skips_after_max_recalculations(scheduler, adapter, base_time):
    """Once a ticket hits the recalc cap, the executor skips instead of recalculating."""
    jira = _regressed_jira("In Progress")  # regressed relative to expected "Code Review"
    executor = TickExecutor(scheduler, jira, pathfinding_adapter=adapter)

    # Pre-seed the guard at its cap for this ticket.
    executor._recalc_counts["PROJ-100"] = executor.MAX_RECALCULATIONS_PER_TICKET

    action = ScheduledAction(
        scheduled_time=scheduler.get_simulation_time(),
        action_type="complete_review",
        agent_id="dev_1",
        ticket_key="PROJ-100",
        expected_status="Code Review",  # precondition outranks actual → RECALCULATE
    )
    scheduler.schedule_action(action)

    pending_before = len(scheduler.store.load_pending_actions())

    result = executor.execute_tick(Mock(), Mock(return_value={"success": True}))

    # The action was skipped by the guard, NOT recalculated.
    assert result["actions"][0]["reason"] == "recalc_loop_guard"
    # No new poisoned actions were scheduled — the queue did not grow.
    pending_after = len(scheduler.store.load_pending_actions())
    assert pending_after <= pending_before


def test_loop_guard_allows_recalculation_below_cap(scheduler, adapter, base_time):
    """Below the cap, a genuine regression still recalculates (guard is not over-eager)."""
    jira = _regressed_jira("In Progress")
    executor = TickExecutor(scheduler, jira, pathfinding_adapter=adapter)

    action = ScheduledAction(
        scheduled_time=scheduler.get_simulation_time(),
        action_type="complete_review",
        agent_id="dev_1",
        ticket_key="PROJ-100",
        expected_status="Code Review",
    )
    scheduler.schedule_action(action)

    result = executor.execute_tick(Mock(), Mock(return_value={"success": True}))

    # First divergence recalculates rather than skipping via the guard.
    assert result["actions"][0].get("recalculated") is True
    assert executor._recalc_counts["PROJ-100"] == 1
