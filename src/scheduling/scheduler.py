"""Scheduler combining queue, persistence, and time management."""

import logging
from typing import List, Optional

import pendulum

from .models import ScheduledAction, ActionStatus
from .priority_queue import ActionPriorityQueue
from .persistence import ScheduledActionStore
from .virtual_clock import VirtualClock

logger = logging.getLogger(__name__)


class Scheduler:
    """Main scheduler combining queue, persistence, and time management."""

    def __init__(
        self,
        store: Optional[ScheduledActionStore] = None,
        virtual_clock: Optional[VirtualClock] = None,
        tick_duration_hours: float = 0.75,
    ):
        self.store = store or ScheduledActionStore()
        self.clock = virtual_clock or VirtualClock(
            pendulum.now("UTC"),
            tick_duration_hours=tick_duration_hours,
        )
        self.queue = ActionPriorityQueue()

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
        """Mark all overdue actions as skipped.

        Returns count of actions marked.
        """
        overdue = self.get_overdue_actions()
        for action in overdue:
            self.mark_action_skipped(action.action_id, "overdue - past execution window")
        return len(overdue)

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
