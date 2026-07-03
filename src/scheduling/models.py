"""Data models for scheduled actions."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from uuid import uuid4

import pendulum


class ActionStatus(str, Enum):
    """Status of a scheduled action."""
    PENDING = "pending"
    READY = "ready"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    ADAPTED = "adapted"


@dataclass(order=True)
class ScheduledAction:
    """
    A scheduled action with execution window and status tracking.

    Comparison is based on scheduled_time only (for heap ordering).
    """

    # Comparison key (for heap)
    scheduled_time: pendulum.DateTime

    # Non-comparison fields
    action_id: str = field(default_factory=lambda: str(uuid4())[:8], compare=False)
    action_type: str = field(default="", compare=False)
    agent_id: str = field(default="", compare=False)
    ticket_key: str = field(default="", compare=False)
    scenario_id: Optional[str] = field(default=None, compare=False)
    window_minutes: int = field(default=30, compare=False)
    # Precondition: the status the ticket MUST already be in for this action to fire.
    # Checked by PreExecutionValidator. Do NOT store the destination status here.
    expected_status: Optional[str] = field(default=None, compare=False)
    # Destination: the status this action moves the ticket TO. Informational only —
    # never validated as a precondition. Kept separate to avoid the semantic collision
    # that previously caused pathfinder-scheduled actions to fail validation forever.
    target_status: Optional[str] = field(default=None, compare=False)
    expected_assignee: Optional[str] = field(default=None, compare=False)
    status: ActionStatus = field(default=ActionStatus.PENDING, compare=False)
    executed_at: Optional[pendulum.DateTime] = field(default=None, compare=False)
    result: Optional[dict] = field(default=None, compare=False)
    params: dict = field(default_factory=dict, compare=False)
    created_at: pendulum.DateTime = field(
        default_factory=lambda: pendulum.now("UTC"),
        compare=False
    )

    def is_due(self, current_time: pendulum.DateTime) -> bool:
        """Check if action is due (within execution window)."""
        window_end = self.scheduled_time.add(minutes=self.window_minutes)
        return self.scheduled_time <= current_time <= window_end

    def is_overdue(self, current_time: pendulum.DateTime) -> bool:
        """Check if action is overdue (past execution window)."""
        window_end = self.scheduled_time.add(minutes=self.window_minutes)
        return current_time > window_end

    def mark_completed(self, result: dict) -> None:
        """Mark action as completed with result."""
        self.status = ActionStatus.COMPLETED
        self.executed_at = pendulum.now("UTC")
        self.result = result

    def mark_skipped(self, reason: str) -> None:
        """Mark action as skipped with reason."""
        self.status = ActionStatus.SKIPPED
        self.result = {"reason": reason}
