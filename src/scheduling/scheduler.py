"""Scheduler combining queue, persistence, and time management."""

import heapq
import logging
from typing import List, Optional

import pendulum

from .models import ScheduledAction, ActionStatus
from .priority_queue import ActionPriorityQueue
from .persistence import ScheduledActionStore
from .business_hours import BusinessHoursScheduler
from .virtual_clock import VirtualClock

logger = logging.getLogger(__name__)


class Scheduler:
    """Main scheduler combining queue, persistence, and time management."""

    def __init__(
        self,
        store: Optional[ScheduledActionStore] = None,
        virtual_clock: Optional[VirtualClock] = None,
        tick_duration_hours: float = 0.75,
        scenario_max_reschedules: int = 3,
    ):
        self.store = store or ScheduledActionStore()
        self.clock = virtual_clock or VirtualClock(
            pendulum.now("UTC"),
            tick_duration_hours=tick_duration_hours,
        )
        self.queue = ActionPriorityQueue()
        self.business_hours = BusinessHoursScheduler()
        # A scenario lifecycle step that misses its (wide) window is re-dated to
        # the next business-hours slot rather than skipped, up to this many times,
        # so a not-yet-ready step waits for its precondition instead of dying.
        self.scenario_max_reschedules = scenario_max_reschedules

        # Load pending actions from persistence
        self._load_pending_actions()

    def _load_pending_actions(self) -> None:
        """Load pending actions from persistence into queue."""
        actions = self.store.load_pending_actions()
        for action in actions:
            self.queue.push(action)
        logger.info(f"Loaded {len(actions)} pending actions from persistence")

    def schedule_action(self, action: ScheduledAction) -> None:
        """Schedule a new action."""
        self.queue.push(action)
        self.store.save_action(action)
        logger.debug(f"Scheduled action {action.action_id} for {action.scheduled_time}")

    def schedule_actions(self, actions: List[ScheduledAction]) -> None:
        """Schedule multiple actions."""
        for action in actions:
            self.schedule_action(action)

    def get_due_actions(
        self,
        max_actions: int = 10
    ) -> List[ScheduledAction]:
        """Get actions due at current simulation time."""
        current_time = self.clock.now()
        return self.queue.get_due_actions(current_time, max_actions)

    def get_overdue_actions(self) -> List[ScheduledAction]:
        """Get actions that are past their execution window."""
        current_time = self.clock.now()
        overdue = []
        for action in self.queue._heap:
            if action.status == ActionStatus.PENDING and action.is_overdue(current_time):
                overdue.append(action)
        return overdue

    def mark_action_completed(
        self,
        action_id: str,
        result: Optional[dict] = None
    ) -> None:
        """Mark action as completed."""
        for action in self.queue._heap:
            if action.action_id == action_id:
                action.mark_completed(result or {})
                self.store.update_status(
                    action_id,
                    ActionStatus.COMPLETED,
                    result=result,
                    executed_at=action.executed_at,
                )
                break

    def mark_action_skipped(
        self,
        action_id: str,
        reason: str
    ) -> None:
        """Mark action as skipped."""
        for action in self.queue._heap:
            if action.action_id == action_id:
                action.mark_skipped(reason)
                self.store.update_status(
                    action_id,
                    ActionStatus.SKIPPED,
                    result={"reason": reason},
                    executed_at=pendulum.now("UTC"),
                )
                logger.info(f"Action {action_id} skipped: {reason}")
                break

    def mark_overdue_as_skipped(self) -> int:
        """Handle overdue actions: reschedule scenario steps, skip the rest.

        Scenario-tagged lifecycle steps (those with a ``scenario_id``) are
        re-dated to the next business-hours slot instead of being skipped, up to
        ``scenario_max_reschedules`` times — this lets a step whose precondition
        isn't ready yet (e.g. day-3 review before day-1 pickup ran) survive to
        retry. Non-scenario actions keep the original skip-on-overdue behavior.

        Returns count of actions skipped (rescheduled ones are not counted).
        """
        overdue = self.get_overdue_actions()
        skipped = 0
        rescheduled = False
        for action in overdue:
            reschedules = action.params.get("reschedule_count", 0)
            if action.scenario_id and reschedules < self.scenario_max_reschedules:
                self._reschedule_action(action)
                rescheduled = True
            else:
                self.mark_action_skipped(
                    action.action_id, "overdue - past execution window"
                )
                skipped += 1

        # Heap ordering is by scheduled_time; mutating it above requires a
        # re-heapify so get_due_actions still walks earliest-first.
        if rescheduled:
            heapq.heapify(self.queue._heap)
        return skipped

    def reschedule_scenario_action(self, action: ScheduledAction) -> bool:
        """Re-date a single scenario action and restore heap order.

        Used when a lifecycle step's precondition isn't ready yet (an earlier
        step hasn't completed) so it should wait and retry rather than be
        skipped. Returns False (and does nothing) once the reschedule cap is hit,
        letting the caller fall back to normal skip/recalculate handling.
        """
        if action.params.get("reschedule_count", 0) >= self.scenario_max_reschedules:
            return False
        self._reschedule_action(action)
        heapq.heapify(self.queue._heap)
        return True

    def _reschedule_action(self, action: ScheduledAction) -> None:
        """Re-date an overdue scenario action to the next business-hours slot."""
        now = self.clock.now()
        new_time = self.business_hours.schedule_action(now, 0)
        action.scheduled_time = new_time
        action.params["reschedule_count"] = action.params.get("reschedule_count", 0) + 1
        # Persist the new time + counter so a restart doesn't resurrect the old slot.
        self.store.save_action(action)
        logger.info(
            "Rescheduled scenario action %s to %s (attempt %d)",
            action.action_id, new_time, action.params["reschedule_count"],
        )

    def advance_tick(self) -> pendulum.DateTime:
        """Advance simulation time by tick duration."""
        return self.clock.advance()

    def get_simulation_time(self) -> pendulum.DateTime:
        """Get current simulation time."""
        return self.clock.now()

    def cleanup_old_actions(self, max_age_hours: int = 48) -> int:
        """Clean up old completed/skipped actions."""
        return self.store.cleanup_old_actions(max_age_hours)

    def get_queue_size(self) -> int:
        """Get number of actions in queue."""
        return self.queue.size()

    def get_scheduled_ticket_keys(self) -> set:
        """Return ticket keys with a PENDING scheduled action.

        Used to keep the inline "plan and execute now" path from touching
        tickets the scheduled lifecycle scripts already own, so the two
        execution paths stay genuinely disjoint (no reconciliation thrash).
        """
        return {
            action.ticket_key
            for action in self.queue._heap
            if action.status == ActionStatus.PENDING and action.ticket_key
        }
