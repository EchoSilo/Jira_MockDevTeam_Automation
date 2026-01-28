"""ActionPriorityQueue for managing scheduled actions."""

import heapq
from typing import List, Optional

import pendulum

from src.scheduling.models import ActionStatus, ScheduledAction


class ActionPriorityQueue:
    """
    Priority queue for scheduled actions using min-heap.

    Actions are ordered by scheduled_time (earliest first).
    Completed/skipped actions remain in heap but are excluded from get_due_actions().
    """

    def __init__(self):
        """Initialize empty priority queue."""
        self._heap: List[ScheduledAction] = []

    def push(self, action: ScheduledAction) -> None:
        """
        Add action to priority queue in O(log n) time.

        Args:
            action: ScheduledAction to add
        """
        heapq.heappush(self._heap, action)

    def peek(self) -> Optional[ScheduledAction]:
        """
        Return earliest action without removing it.

        Returns:
            ScheduledAction with earliest scheduled_time, or None if empty
        """
        return self._heap[0] if self._heap else None

    def pop(self) -> Optional[ScheduledAction]:
        """
        Remove and return earliest action in O(log n) time.

        Returns:
            ScheduledAction with earliest scheduled_time, or None if empty
        """
        return heapq.heappop(self._heap) if self._heap else None

    def get_due_actions(
        self,
        current_time: pendulum.DateTime,
        max_actions: int = 10
    ) -> List[ScheduledAction]:
        """
        Get PENDING actions within execution window.

        Does not remove actions from queue. Iterates heap in scheduled_time order
        and returns actions where is_due(current_time) and status == PENDING.

        Args:
            current_time: Current time for window checking
            max_actions: Maximum number of actions to return (default 10)

        Returns:
            List of due PENDING actions, up to max_actions
        """
        due_actions = []

        for action in self._heap:
            # Stop if we've found enough actions
            if len(due_actions) >= max_actions:
                break

            # Stop if we've reached actions scheduled in the future
            # (heap is sorted by scheduled_time)
            if action.scheduled_time > current_time:
                break

            # Include only PENDING actions within their execution window
            if action.status == ActionStatus.PENDING and action.is_due(current_time):
                due_actions.append(action)

        return due_actions

    def cancel_action(self, action_id: str) -> None:
        """
        Cancel action by marking it as SKIPPED.

        Does not remove from heap (heapq doesn't support efficient removal).
        Skipped actions are excluded from get_due_actions().

        Args:
            action_id: ID of action to cancel
        """
        for action in self._heap:
            if action.action_id == action_id:
                action.mark_skipped("Canceled")
                break

    def size(self) -> int:
        """
        Return number of actions in queue.

        Returns:
            Total number of actions (including completed/skipped)
        """
        return len(self._heap)

    def is_empty(self) -> bool:
        """
        Check if queue is empty.

        Returns:
            True if queue has no actions
        """
        return len(self._heap) == 0
