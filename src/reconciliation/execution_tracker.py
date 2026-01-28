"""Execution ID tracker for idempotency guarantees.

This module provides tracking of action executions to prevent duplicate
actions during retries. Each action generates a unique execution ID that
is recorded upon completion, allowing subsequent execution attempts to
be detected and skipped.

Usage:
    from src.reconciliation import ExecutionTracker
    from src.time import RealClock

    tracker = ExecutionTracker(clock=RealClock())

    # Generate unique ID for an action
    exec_id = tracker.generate_execution_id("transition", "ESCRUM-123", "dev_alice")

    # Check if already executed (for retry scenarios)
    if tracker.is_executed(exec_id):
        return  # Skip duplicate

    # Perform action...

    # Record successful execution
    tracker.record_execution(exec_id, "transition", "ESCRUM-123", "success")
"""
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional
import uuid

import pendulum

from src.time import Clock, RealClock


@dataclass
class ExecutionRecord:
    """Record of a completed action execution.

    Attributes:
        execution_id: Unique identifier for this execution
        action_type: Type of action (e.g., "transition", "add_comment")
        ticket_key: Jira ticket key (e.g., "ESCRUM-123")
        executed_at: UTC timestamp when execution completed
        result: Execution outcome - "success", "failure", or "skipped"
    """

    execution_id: str
    action_type: str
    ticket_key: str
    executed_at: pendulum.DateTime
    result: str  # "success" | "failure" | "skipped"


class ExecutionTracker:
    """Tracks action executions for idempotency.

    Generates unique execution IDs, records completed executions, and
    detects duplicate execution attempts. Old records are automatically
    cleaned up to prevent unbounded memory growth.

    Attributes:
        cleanup_age_hours: Records older than this are automatically removed.
            Defaults to 48 hours.
    """

    def __init__(
        self,
        clock: Optional[Clock] = None,
        cleanup_age_hours: int = 48,
    ) -> None:
        """Initialize the execution tracker.

        Args:
            clock: Clock instance for timestamps. Defaults to RealClock.
            cleanup_age_hours: Hours after which records are cleaned up.
                Defaults to 48 hours.
        """
        self._clock = clock or RealClock()
        self._cleanup_age = timedelta(hours=cleanup_age_hours)
        self._executed: dict[str, ExecutionRecord] = {}

    def generate_execution_id(
        self,
        action_type: str,
        ticket_key: str,
        agent_id: str,
    ) -> str:
        """Generate a unique execution ID for an action.

        The ID format is: {action_type}:{ticket_key}:{agent_id}:{uuid8}

        The first three components form a deterministic prefix identifying
        the action context. The uuid8 suffix ensures uniqueness across
        multiple executions of the same action.

        Args:
            action_type: Type of action (e.g., "transition_to_in_progress")
            ticket_key: Jira ticket key (e.g., "ESCRUM-123")
            agent_id: Agent performing the action (e.g., "dev_alice")

        Returns:
            Unique execution ID string
        """
        unique_suffix = str(uuid.uuid4())[:8]
        return f"{action_type}:{ticket_key}:{agent_id}:{unique_suffix}"

    def is_executed(self, execution_id: str) -> bool:
        """Check if an execution ID has already been recorded.

        Use this before performing an action to prevent duplicates
        during retry scenarios.

        Args:
            execution_id: The execution ID to check

        Returns:
            True if the execution has been recorded, False otherwise
        """
        return execution_id in self._executed

    def record_execution(
        self,
        execution_id: str,
        action_type: str,
        ticket_key: str,
        result: str,
    ) -> None:
        """Record a completed execution.

        This marks the execution ID as executed, preventing future
        duplicate executions with the same ID. Also triggers cleanup
        of old records (piggyback pattern).

        Args:
            execution_id: The execution ID to record
            action_type: Type of action performed
            ticket_key: Jira ticket key
            result: Execution outcome - "success", "failure", or "skipped"
        """
        record = ExecutionRecord(
            execution_id=execution_id,
            action_type=action_type,
            ticket_key=ticket_key,
            executed_at=self._clock.now(),
            result=result,
        )
        self._executed[execution_id] = record
        self._cleanup_old_executions()

    def get_record(self, execution_id: str) -> Optional[ExecutionRecord]:
        """Retrieve an execution record by ID.

        Args:
            execution_id: The execution ID to look up

        Returns:
            The ExecutionRecord if found, None otherwise
        """
        return self._executed.get(execution_id)

    def _cleanup_old_executions(self) -> None:
        """Remove execution records older than cleanup_age.

        This runs on each record_execution() call (piggyback pattern)
        to prevent unbounded memory growth without requiring a
        separate cleanup process.
        """
        cutoff = self._clock.now() - self._cleanup_age
        self._executed = {
            k: v for k, v in self._executed.items() if v.executed_at > cutoff
        }
