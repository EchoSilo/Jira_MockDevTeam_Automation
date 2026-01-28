"""
Unit tests for ScenarioAdapter.

Tests chaos event adaptation logic including action insertion,
adaptation marking, postponement, and agent reassignment.
"""

import pendulum
import pytest

from src.chaos.models import RandomEvent, ChaosEventType
from src.chaos.scenario_adapter import ScenarioAdapter, AdaptationResult
from src.scheduling.scheduler import Scheduler
from src.scheduling.models import ScheduledAction, ActionStatus
from src.scheduling.persistence import ScheduledActionStore


@pytest.fixture
def scheduler():
    """Create scheduler with in-memory store."""
    store = ScheduledActionStore(db_path=":memory:")
    return Scheduler(store=store)


@pytest.fixture
def adapter(scheduler):
    """Create scenario adapter."""
    return ScenarioAdapter(scheduler)


@pytest.fixture
def base_time():
    """Base time for test scenarios."""
    return pendulum.parse("2026-01-28T10:00:00Z")


def test_production_outage_inserts_emergency_response(adapter, scheduler, base_time):
    """Production outage should insert emergency response action."""
    # Create production outage event
    event = RandomEvent(
        event_type=ChaosEventType.production_outage,
        triggered_at=base_time,
        affected_tickets=["PROJ-123"],
        affected_agents=[],
        description="Production outage detected",
        severity="critical",
        details={"impact": "high"},
        duration_ticks=1,
    )

    # Adapt scenario
    result = adapter.adapt_to_event(event)

    # Should insert emergency response action
    assert len(result.actions_inserted) == 1
    assert result.actions_inserted[0].action_type == "emergency_response"
    assert result.actions_inserted[0].agent_id == "tech_lead"
    assert result.actions_inserted[0].ticket_key == "PROJ-123"
    assert "production outage" in result.summary.lower()


def test_production_outage_pauses_non_critical_actions(adapter, scheduler, base_time):
    """Production outage should pause non-critical actions but keep critical ones."""
    # Schedule mix of critical and non-critical actions
    critical_action = ScheduledAction(
        scheduled_time=base_time.add(minutes=10),
        action_type="release_ready",
        agent_id="developer",
    )
    non_critical_action = ScheduledAction(
        scheduled_time=base_time.add(minutes=10),
        action_type="dev_progress",
        agent_id="developer",
    )
    scheduler.schedule_action(critical_action)
    scheduler.schedule_action(non_critical_action)

    # Create production outage event
    event = RandomEvent(
        event_type=ChaosEventType.production_outage,
        triggered_at=base_time,
        affected_tickets=["PROJ-123"],
        affected_agents=[],
        description="Production outage detected",
        severity="critical",
        details={"impact": "high"},
    )

    # Adapt scenario
    result = adapter.adapt_to_event(event)

    # Should have paused non-critical action
    assert len(result.actions_adapted) >= 1

    # Verify non-critical action marked ADAPTED
    stored_action = scheduler.store.load_action(non_critical_action.action_id)
    assert stored_action.status == ActionStatus.ADAPTED
    assert "production_outage" in stored_action.result["reason"]


def test_urgent_bug_inserts_fix_action(adapter, scheduler, base_time):
    """Urgent bug should insert fix action."""
    event = RandomEvent(
        event_type=ChaosEventType.urgent_bug,
        triggered_at=base_time,
        affected_tickets=["PROJ-456"],
        affected_agents=[],
        description="Urgent bug discovered",
        severity="high",
        details={"impact": "medium-high"},
    )

    result = adapter.adapt_to_event(event)

    # Should insert bug fix action
    assert len(result.actions_inserted) == 1
    assert result.actions_inserted[0].action_type == "urgent_bug_fix"
    assert result.actions_inserted[0].agent_id == "developer"
    assert result.actions_inserted[0].ticket_key == "PROJ-456"


def test_urgent_bug_postpones_non_urgent_work(adapter, scheduler, base_time):
    """Urgent bug should postpone non-urgent actions."""
    # Schedule non-urgent action
    non_urgent_action = ScheduledAction(
        scheduled_time=base_time.add(minutes=10),
        action_type="dev_progress",
        agent_id="developer",
        ticket_key="PROJ-999",
    )
    scheduler.schedule_action(non_urgent_action)

    event = RandomEvent(
        event_type=ChaosEventType.urgent_bug,
        triggered_at=base_time,
        affected_tickets=["PROJ-456"],
        affected_agents=[],
        description="Urgent bug discovered",
        severity="high",
        details={},
    )

    result = adapter.adapt_to_event(event)

    # Should have postponed non-urgent action
    assert len(result.actions_postponed) >= 1

    # Original action should be marked ADAPTED
    stored_action = scheduler.store.load_action(non_urgent_action.action_id)
    assert stored_action.status == ActionStatus.ADAPTED
    assert "urgent_bug" in stored_action.result["reason"]

    # Should have inserted new postponed action
    assert len(result.actions_inserted) >= 2  # bug fix + postponed action(s)


def test_team_absence_reassigns_actions(adapter, scheduler, base_time):
    """Team absence should reassign actions to replacement agent."""
    # Schedule action for agent who will be absent
    absent_agent = "alice_developer"
    action_for_absent = ScheduledAction(
        scheduled_time=base_time.add(minutes=10),
        action_type="dev_progress",
        agent_id=absent_agent,
        ticket_key="PROJ-789",
    )
    scheduler.schedule_action(action_for_absent)

    event = RandomEvent(
        event_type=ChaosEventType.team_absence,
        triggered_at=base_time,
        affected_tickets=[],
        affected_agents=[absent_agent],
        description=f"{absent_agent} unexpectedly unavailable",
        severity="medium",
        details={"absence_reason": "unplanned", "duration": 3},
        duration_ticks=3,
    )

    result = adapter.adapt_to_event(event)

    # Should have reassigned action
    assert len(result.actions_inserted) >= 1
    reassigned = result.actions_inserted[0]
    assert reassigned.agent_id != absent_agent
    assert reassigned.ticket_key == "PROJ-789"
    assert reassigned.params.get("reassigned_from") == absent_agent

    # Original action should be marked ADAPTED
    stored_action = scheduler.store.load_action(action_for_absent.action_id)
    assert stored_action.status == ActionStatus.ADAPTED
    assert "team_absence" in stored_action.result["reason"]


def test_external_blocker_adds_discussion_action(adapter, scheduler, base_time):
    """External blocker should add blocker discussion action."""
    event = RandomEvent(
        event_type=ChaosEventType.external_blocker,
        triggered_at=base_time,
        affected_tickets=["PROJ-111"],
        affected_agents=[],
        description="External blocker identified",
        severity="medium",
        details={"blocker_type": "external_dependency"},
    )

    result = adapter.adapt_to_event(event)

    # Should insert discussion action
    assert len(result.actions_inserted) == 1
    assert result.actions_inserted[0].action_type == "blocker_discussion"
    assert result.actions_inserted[0].agent_id == "tech_lead"
    assert result.actions_inserted[0].ticket_key == "PROJ-111"


def test_external_blocker_marks_affected_actions_adapted(adapter, scheduler, base_time):
    """External blocker should mark actions for affected ticket as adapted."""
    blocked_ticket = "PROJ-111"

    # Schedule action for ticket that will be blocked
    action_for_blocked = ScheduledAction(
        scheduled_time=base_time.add(minutes=10),
        action_type="dev_progress",
        agent_id="developer",
        ticket_key=blocked_ticket,
    )
    scheduler.schedule_action(action_for_blocked)

    event = RandomEvent(
        event_type=ChaosEventType.external_blocker,
        triggered_at=base_time,
        affected_tickets=[blocked_ticket],
        affected_agents=[],
        description="External blocker identified",
        severity="medium",
        details={"blocker_type": "external_dependency"},
    )

    result = adapter.adapt_to_event(event)

    # Should have marked action as adapted
    assert len(result.actions_adapted) >= 1

    # Verify action marked ADAPTED
    stored_action = scheduler.store.load_action(action_for_blocked.action_id)
    assert stored_action.status == ActionStatus.ADAPTED
    assert "external_blocker" in stored_action.result["reason"]


def test_priority_shift_no_immediate_action(adapter, base_time):
    """Priority shift should not immediately modify actions (PM-driven)."""
    event = RandomEvent(
        event_type=ChaosEventType.priority_shift,
        triggered_at=base_time,
        affected_tickets=["PROJ-222"],
        affected_agents=[],
        description="Priority shift requested",
        severity="medium",
        details={"reason": "stakeholder_request"},
    )

    result = adapter.adapt_to_event(event)

    # Should have no immediate action modifications
    assert len(result.actions_inserted) == 0
    assert len(result.actions_adapted) == 0
    assert "no immediate action" in result.summary.lower()


def test_scope_change_marks_affected_actions_adapted(adapter, scheduler, base_time):
    """Scope change should mark actions for affected ticket as adapted."""
    affected_ticket = "PROJ-333"

    # Schedule action for ticket with scope change
    action_for_changed = ScheduledAction(
        scheduled_time=base_time.add(minutes=10),
        action_type="dev_progress",
        agent_id="developer",
        ticket_key=affected_ticket,
    )
    scheduler.schedule_action(action_for_changed)

    event = RandomEvent(
        event_type=ChaosEventType.scope_change,
        triggered_at=base_time,
        affected_tickets=[affected_ticket],
        affected_agents=[],
        description="Scope change requested",
        severity="high",
        details={"change_type": "requirements_update"},
    )

    result = adapter.adapt_to_event(event)

    # Should have marked action as adapted
    assert len(result.actions_adapted) >= 1

    # Verify action marked ADAPTED
    stored_action = scheduler.store.load_action(action_for_changed.action_id)
    assert stored_action.status == ActionStatus.ADAPTED
    assert "Scope changed" in stored_action.result["reason"]


def test_adaptation_result_to_dict(base_time):
    """AdaptationResult.to_dict() should return summary dictionary."""
    action1 = ScheduledAction(
        scheduled_time=base_time,
        action_type="test_action",
        agent_id="test_agent",
    )

    result = AdaptationResult(
        event_id="test123",
        actions_inserted=[action1],
        actions_adapted=["action1", "action2"],
        actions_postponed=["action3"],
        summary="Test summary",
    )

    result_dict = result.to_dict()

    assert result_dict["event_id"] == "test123"
    assert result_dict["inserted_count"] == 1
    assert result_dict["adapted_count"] == 2
    assert result_dict["postponed_count"] == 1
    assert result_dict["summary"] == "Test summary"


def test_team_absence_handles_no_affected_agents(adapter, base_time):
    """Team absence with no affected agents should return early."""
    event = RandomEvent(
        event_type=ChaosEventType.team_absence,
        triggered_at=base_time,
        affected_tickets=[],
        affected_agents=[],  # Empty
        description="Team absence event",
        severity="medium",
        details={},
    )

    result = adapter.adapt_to_event(event)

    assert len(result.actions_inserted) == 0
    assert "no affected agents" in result.summary.lower()


def test_external_blocker_handles_no_affected_tickets(adapter, base_time):
    """External blocker with no affected tickets should return early."""
    event = RandomEvent(
        event_type=ChaosEventType.external_blocker,
        triggered_at=base_time,
        affected_tickets=[],  # Empty
        affected_agents=[],
        description="External blocker event",
        severity="medium",
        details={},
    )

    result = adapter.adapt_to_event(event)

    assert len(result.actions_inserted) == 0
    assert "no affected tickets" in result.summary.lower()
