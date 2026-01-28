"""
ScenarioAdapter modifies active scenarios when chaos events occur.

Inserts new ScheduledActions and marks existing ones as ADAPTED to reflect
realistic disruption patterns.
"""

from dataclasses import dataclass, field
from typing import Optional
import logging

import pendulum

from src.scheduling.scheduler import Scheduler
from src.scheduling.models import ScheduledAction, ActionStatus
from .models import RandomEvent, ChaosEventType

logger = logging.getLogger(__name__)


@dataclass
class AdaptationResult:
    """Result of adapting a scenario to a chaos event."""
    event_id: str
    actions_inserted: list[ScheduledAction] = field(default_factory=list)
    actions_adapted: list[str] = field(default_factory=list)  # action_ids marked ADAPTED
    actions_postponed: list[str] = field(default_factory=list)  # action_ids postponed
    summary: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for logging/reporting."""
        return {
            "event_id": self.event_id,
            "inserted_count": len(self.actions_inserted),
            "adapted_count": len(self.actions_adapted),
            "postponed_count": len(self.actions_postponed),
            "summary": self.summary,
        }


class ScenarioAdapter:
    """
    Adapts active scenarios when chaos events occur.

    Modifies the action queue by:
    - Inserting new emergency response actions
    - Marking existing actions as ADAPTED
    - Postponing non-critical work
    - Reassigning actions when agents unavailable
    """

    def __init__(self, scheduler: Scheduler):
        """Initialize adapter with scheduler reference.

        Args:
            scheduler: Scheduler to modify actions through
        """
        self.scheduler = scheduler

    def adapt_to_event(self, event: RandomEvent) -> AdaptationResult:
        """
        Adapt active scenario to chaos event.

        Routes to event-specific handler based on event type.

        Args:
            event: The chaos event that occurred

        Returns:
            AdaptationResult with inserted/adapted actions
        """
        handlers = {
            ChaosEventType.production_outage: self._handle_production_outage,
            ChaosEventType.urgent_bug: self._handle_urgent_bug,
            ChaosEventType.team_absence: self._handle_team_absence,
            ChaosEventType.external_blocker: self._handle_external_blocker,
            ChaosEventType.priority_shift: self._handle_priority_shift,
            ChaosEventType.scope_change: self._handle_scope_change,
        }

        handler = handlers.get(event.event_type)
        if not handler:
            logger.warning(f"No handler for event type {event.event_type}")
            return AdaptationResult(event_id=event.event_id, summary="No handler available")

        result = handler(event)
        logger.info(f"Adapted scenario for {event.event_type.value}: {result.to_dict()}")
        return result

    def _handle_production_outage(self, event: RandomEvent) -> AdaptationResult:
        """
        Handle production outage: pause non-critical, insert emergency response.

        Strategy:
        - Insert emergency response action for tech_lead
        - Mark non-critical actions as ADAPTED (paused)
        - Keep critical actions (releases, urgent fixes) running
        """
        result = AdaptationResult(event_id=event.event_id)

        # Insert emergency response action
        emergency_action = ScheduledAction(
            scheduled_time=event.triggered_at.add(minutes=5),  # Immediate response
            action_type="emergency_response",
            agent_id="tech_lead",  # Tech lead handles outages
            ticket_key=event.affected_tickets[0] if event.affected_tickets else "",
            window_minutes=60,  # Longer window for emergency work
            params={
                "event_type": event.event_type.value,
                "severity": event.severity,
                "description": event.description,
            },
        )
        self.scheduler.schedule_action(emergency_action)
        result.actions_inserted.append(emergency_action)

        # Mark non-critical actions as ADAPTED
        due_actions = self.scheduler.get_due_actions(max_actions=20)
        for action in due_actions:
            if action.status == ActionStatus.PENDING and self._is_non_critical(action):
                action.status = ActionStatus.ADAPTED
                action.result = {"reason": f"Paused due to {event.event_type.value}"}
                self.scheduler.store.update_status(
                    action.action_id,
                    ActionStatus.ADAPTED,
                    result=action.result,
                    executed_at=pendulum.now("UTC"),
                )
                result.actions_adapted.append(action.action_id)

        result.summary = (
            f"Production outage: inserted emergency response, "
            f"paused {len(result.actions_adapted)} non-critical actions"
        )
        return result

    def _handle_urgent_bug(self, event: RandomEvent) -> AdaptationResult:
        """
        Handle urgent bug: insert fix action and postpone other work.

        Strategy:
        - Insert bug fix action for developer
        - Postpone non-urgent actions by 2 ticks
        - Keep release-critical work running
        """
        result = AdaptationResult(event_id=event.event_id)

        # Insert bug fix action
        bug_fix_action = ScheduledAction(
            scheduled_time=event.triggered_at.add(minutes=10),
            action_type="urgent_bug_fix",
            agent_id="developer",  # Any dev can handle
            ticket_key=event.affected_tickets[0] if event.affected_tickets else "",
            window_minutes=90,  # Longer window for fix work
            params={
                "event_type": event.event_type.value,
                "severity": event.severity,
                "description": event.description,
            },
        )
        self.scheduler.schedule_action(bug_fix_action)
        result.actions_inserted.append(bug_fix_action)

        # Postpone non-urgent actions
        due_actions = self.scheduler.get_due_actions(max_actions=20)
        for action in due_actions:
            if action.status == ActionStatus.PENDING and not self._is_urgent(action):
                # Create postponed action
                postponed_action = ScheduledAction(
                    scheduled_time=action.scheduled_time.add(hours=1.5),  # Postpone by 2 ticks
                    action_type=action.action_type,
                    agent_id=action.agent_id,
                    ticket_key=action.ticket_key,
                    scenario_id=action.scenario_id,
                    window_minutes=action.window_minutes,
                    expected_status=action.expected_status,
                    expected_assignee=action.expected_assignee,
                    params=action.params,
                )
                self.scheduler.schedule_action(postponed_action)

                # Mark original as ADAPTED
                action.status = ActionStatus.ADAPTED
                action.result = {"reason": f"Postponed due to urgent_bug"}
                self.scheduler.store.update_status(
                    action.action_id,
                    ActionStatus.ADAPTED,
                    result=action.result,
                    executed_at=pendulum.now("UTC"),
                )
                result.actions_adapted.append(action.action_id)
                result.actions_postponed.append(action.action_id)

        result.summary = (
            f"Urgent bug: inserted fix action, "
            f"postponed {len(result.actions_postponed)} non-urgent actions"
        )
        return result

    def _handle_team_absence(self, event: RandomEvent) -> AdaptationResult:
        """
        Handle team absence: reassign actions to other agents.

        Strategy:
        - Find actions assigned to absent agent
        - Create replacement actions with different agent
        - Mark original actions as ADAPTED
        """
        result = AdaptationResult(event_id=event.event_id)

        if not event.affected_agents:
            result.summary = "Team absence: no affected agents specified"
            return result

        absent_agent = event.affected_agents[0]

        # Find actions assigned to absent agent
        due_actions = self.scheduler.get_due_actions(max_actions=20)
        for action in due_actions:
            if action.status == ActionStatus.PENDING and action.agent_id == absent_agent:
                # Reassign to replacement agent (simple: use "developer" as fallback)
                replacement_agent = self._get_replacement_agent(absent_agent)
                reassigned_action = ScheduledAction(
                    scheduled_time=action.scheduled_time.add(minutes=30),  # Slight delay
                    action_type=action.action_type,
                    agent_id=replacement_agent,
                    ticket_key=action.ticket_key,
                    scenario_id=action.scenario_id,
                    window_minutes=action.window_minutes,
                    expected_status=action.expected_status,
                    expected_assignee=action.expected_assignee,
                    params={
                        **action.params,
                        "reassigned_from": absent_agent,
                        "reason": "team_absence",
                    },
                )
                self.scheduler.schedule_action(reassigned_action)
                result.actions_inserted.append(reassigned_action)

                # Mark original as ADAPTED
                action.status = ActionStatus.ADAPTED
                action.result = {
                    "reason": f"Reassigned to {replacement_agent} due to team_absence"
                }
                self.scheduler.store.update_status(
                    action.action_id,
                    ActionStatus.ADAPTED,
                    result=action.result,
                    executed_at=pendulum.now("UTC"),
                )
                result.actions_adapted.append(action.action_id)

        result.summary = (
            f"Team absence: reassigned {len(result.actions_inserted)} actions "
            f"from {absent_agent}"
        )
        return result

    def _handle_external_blocker(self, event: RandomEvent) -> AdaptationResult:
        """
        Handle external blocker: add discussion action, extend timeline.

        Strategy:
        - Insert blocker discussion action
        - Mark affected ticket actions as ADAPTED (extended timeline)
        """
        result = AdaptationResult(event_id=event.event_id)

        if not event.affected_tickets:
            result.summary = "External blocker: no affected tickets specified"
            return result

        affected_ticket = event.affected_tickets[0]

        # Insert blocker discussion action
        discussion_action = ScheduledAction(
            scheduled_time=event.triggered_at.add(minutes=15),
            action_type="blocker_discussion",
            agent_id="tech_lead",  # Tech lead handles blockers
            ticket_key=affected_ticket,
            window_minutes=45,
            params={
                "event_type": event.event_type.value,
                "description": event.description,
                "blocker_type": event.details.get("blocker_type", "unknown"),
            },
        )
        self.scheduler.schedule_action(discussion_action)
        result.actions_inserted.append(discussion_action)

        # Mark actions for affected ticket as ADAPTED
        due_actions = self.scheduler.get_due_actions(max_actions=20)
        for action in due_actions:
            if action.status == ActionStatus.PENDING and action.ticket_key == affected_ticket:
                action.status = ActionStatus.ADAPTED
                action.result = {"reason": f"Blocked by external_blocker"}
                self.scheduler.store.update_status(
                    action.action_id,
                    ActionStatus.ADAPTED,
                    result=action.result,
                    executed_at=pendulum.now("UTC"),
                )
                result.actions_adapted.append(action.action_id)

        result.summary = (
            f"External blocker: added discussion action, "
            f"marked {len(result.actions_adapted)} actions as adapted"
        )
        return result

    def _handle_priority_shift(self, event: RandomEvent) -> AdaptationResult:
        """
        Handle priority shift: no immediate action needed.

        Priority shifts typically require PM intervention and don't
        immediately affect scheduled actions.
        """
        result = AdaptationResult(event_id=event.event_id)
        result.summary = "Priority shift: no immediate action adaptation required"
        return result

    def _handle_scope_change(self, event: RandomEvent) -> AdaptationResult:
        """
        Handle scope change: mark affected actions as adapted.

        Strategy:
        - Mark actions for affected ticket as ADAPTED
        - Scenario planner will regenerate actions based on new scope
        """
        result = AdaptationResult(event_id=event.event_id)

        if not event.affected_tickets:
            result.summary = "Scope change: no affected tickets specified"
            return result

        affected_ticket = event.affected_tickets[0]

        # Mark actions for affected ticket as ADAPTED
        due_actions = self.scheduler.get_due_actions(max_actions=20)
        for action in due_actions:
            if action.status == ActionStatus.PENDING and action.ticket_key == affected_ticket:
                action.status = ActionStatus.ADAPTED
                action.result = {
                    "reason": f"Scope changed: {event.details.get('change_type', 'unknown')}"
                }
                self.scheduler.store.update_status(
                    action.action_id,
                    ActionStatus.ADAPTED,
                    result=action.result,
                    executed_at=pendulum.now("UTC"),
                )
                result.actions_adapted.append(action.action_id)

        result.summary = (
            f"Scope change: marked {len(result.actions_adapted)} actions as adapted"
        )
        return result

    def _is_non_critical(self, action: ScheduledAction) -> bool:
        """Determine if action is non-critical (can be paused during outage)."""
        critical_types = {"release_ready", "urgent_bug_fix", "emergency_response"}
        return action.action_type not in critical_types

    def _is_urgent(self, action: ScheduledAction) -> bool:
        """Determine if action is urgent (should not be postponed)."""
        urgent_types = {"release_ready", "urgent_bug_fix", "emergency_response", "qa_approve"}
        return action.action_type in urgent_types

    def _get_replacement_agent(self, absent_agent: str) -> str:
        """Get replacement agent for absent team member.

        Simple strategy: return generic role.
        Real implementation could query available agents from state.
        """
        # Map to generic role
        if "pm" in absent_agent.lower():
            return "pm_backup"
        elif "qa" in absent_agent.lower():
            return "qa_backup"
        elif "tech_lead" in absent_agent.lower():
            return "developer"  # Dev covers for tech lead
        else:
            return "developer"  # Default to developer
