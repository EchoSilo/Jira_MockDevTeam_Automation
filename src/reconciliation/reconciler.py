"""Reconciliation engine for detecting and adapting to Jira state divergence.

This module provides the core logic for deciding how to handle situations
where the actual Jira state differs from what the simulation expected.
"""
from dataclasses import dataclass
from typing import Optional, Any
import logging

from .adapters import AdaptationStrategy


logger = logging.getLogger(__name__)


@dataclass
class ReconciliationResult:
    """Result of a reconciliation decision.

    Attributes:
        strategy: The adaptation strategy to apply
        reason: Human-readable explanation of the decision
        tombstone_reason: Why scenario was invalidated (only for CANCEL)
        new_plan: Recalculated action plan (only for RECALCULATE)
    """

    strategy: AdaptationStrategy
    reason: str
    tombstone_reason: Optional[str] = None
    new_plan: Optional[list] = None


class ReconciliationEngine:
    """Decides how to adapt when Jira state diverges from simulation plan.

    The engine implements reconciliation logic for three types of divergence:
    1. Status mismatch: Ticket status changed externally
    2. Sprint mismatch: Ticket sprint membership changed externally
    3. API failure: Jira API returned an error

    Example:
        engine = ReconciliationEngine()

        # Check status divergence
        result = engine.reconcile_status_mismatch(
            ticket_key="ESCRUM-123",
            expected_status="In Progress",
            actual_status="Done",
            action_type="transition"
        )
        if result.strategy == AdaptationStrategy.CANCEL:
            # Mark scenario as tombstoned
            log_tombstone(result.tombstone_reason)
    """

    # Status progression map for determining if ticket moved forward/backward
    # Higher numbers = further along in workflow
    STATUS_ORDER = {
        "To Do": 0,
        "In Progress": 1,
        "Code Review": 2,
        "In Review": 2,  # Alias for Code Review
        "Ready for QA": 3,
        "Testing": 3,  # Alias for Ready for QA
        "Done": 4,
        "Closed": 4,  # Alias for Done
        "Resolved": 4,  # Alias for Done
    }

    # Terminal statuses that indicate scenario completion
    TERMINAL_STATUSES = {"Done", "Closed", "Resolved"}

    # Transient error keywords that indicate temporary failures
    TRANSIENT_ERROR_KEYWORDS = {"timeout", "503", "429", "connection"}

    # Maximum retry count before giving up on transient errors
    MAX_RETRY_COUNT = 3

    def reconcile_status_mismatch(
        self,
        ticket_key: str,
        expected_status: str,
        actual_status: str,
        action_type: str,
    ) -> ReconciliationResult:
        """Decide how to handle a status mismatch.

        Adaptation logic:
        - If user moved ticket to terminal status: CANCEL (scenario complete)
        - If user moved ticket forward: SKIP (they did our work)
        - If user moved ticket backward: RECALCULATE (recalc from current state)
        - If unknown statuses: PROCEED (cautiously attempt action)

        Args:
            ticket_key: Jira ticket key (e.g., "ESCRUM-123")
            expected_status: The status we expected the ticket to be in
            actual_status: The status the ticket is actually in
            action_type: Type of action being attempted (e.g., "transition")

        Returns:
            ReconciliationResult with strategy and reason
        """
        # Terminal statuses - scenario is complete
        if actual_status in self.TERMINAL_STATUSES:
            return ReconciliationResult(
                strategy=AdaptationStrategy.CANCEL,
                reason=f"Ticket moved to terminal status '{actual_status}' externally",
                tombstone_reason=f"User completed ticket manually ({actual_status})",
            )

        # Get status ranks
        expected_rank = self.STATUS_ORDER.get(expected_status, -1)
        actual_rank = self.STATUS_ORDER.get(actual_status, -1)

        # Handle unknown statuses
        if expected_rank == -1 or actual_rank == -1:
            return ReconciliationResult(
                strategy=AdaptationStrategy.PROCEED,
                reason=f"Unknown status progression, attempting action cautiously",
            )

        # Ticket progressed ahead - skip our action
        if actual_rank > expected_rank:
            return ReconciliationResult(
                strategy=AdaptationStrategy.SKIP,
                reason=f"Ticket already progressed to '{actual_status}' externally",
            )

        # Ticket regressed - recalculate from current state
        if actual_rank < expected_rank:
            return ReconciliationResult(
                strategy=AdaptationStrategy.RECALCULATE,
                reason=f"Ticket regressed to '{actual_status}', recalculating plan",
            )

        # Same rank (e.g., "Code Review" vs "In Review") - proceed
        return ReconciliationResult(
            strategy=AdaptationStrategy.PROCEED,
            reason=f"Status rank unchanged, proceeding with action",
        )

    def reconcile_sprint_mismatch(
        self,
        ticket_key: str,
        expected_in_sprint: bool,
        actual_in_sprint: bool,
    ) -> ReconciliationResult:
        """Decide how to handle a sprint membership mismatch.

        Adaptation logic:
        - If expected in sprint but removed: CANCEL (user removed it)
        - If not expected but added: PROCEED (external addition is fine)
        - If matches: PROCEED (no divergence)

        Args:
            ticket_key: Jira ticket key (e.g., "ESCRUM-123")
            expected_in_sprint: Whether we expected ticket to be in active sprint
            actual_in_sprint: Whether ticket is actually in active sprint

        Returns:
            ReconciliationResult with strategy and reason
        """
        if expected_in_sprint and not actual_in_sprint:
            return ReconciliationResult(
                strategy=AdaptationStrategy.CANCEL,
                reason=f"Ticket removed from active sprint externally",
                tombstone_reason="Removed from sprint by user",
            )

        if not expected_in_sprint and actual_in_sprint:
            return ReconciliationResult(
                strategy=AdaptationStrategy.PROCEED,
                reason="Ticket added to sprint externally, proceeding",
            )

        # Matches (both True or both False)
        return ReconciliationResult(
            strategy=AdaptationStrategy.PROCEED,
            reason="Sprint membership matches expectation",
        )

    def reconcile_api_failure(
        self,
        error: Any,
        retry_count: int = 0,
    ) -> ReconciliationResult:
        """Decide how to handle a Jira API failure.

        Adaptation logic:
        - If transient error (timeout, 503, 429) and retry_count < 3: RESCHEDULE
        - If 404/not found: CANCEL (ticket deleted)
        - If other error: SKIP (continue with other actions)

        Args:
            error: The error that occurred (string or Exception)
            retry_count: How many times this action has been retried

        Returns:
            ReconciliationResult with strategy and reason
        """
        # Handle None error gracefully
        if error is None:
            return ReconciliationResult(
                strategy=AdaptationStrategy.SKIP,
                reason="Jira API error (None), skipping action",
            )

        # Convert to lowercase string for matching
        error_str = str(error).lower()

        # Check for transient errors
        is_transient = any(
            keyword in error_str for keyword in self.TRANSIENT_ERROR_KEYWORDS
        )

        if is_transient and retry_count < self.MAX_RETRY_COUNT:
            return ReconciliationResult(
                strategy=AdaptationStrategy.RESCHEDULE,
                reason=f"Transient error ({error}), will retry",
            )

        # Check for 404/not found
        if "404" in error_str or "not found" in error_str:
            return ReconciliationResult(
                strategy=AdaptationStrategy.CANCEL,
                reason=f"Ticket not found in Jira",
                tombstone_reason="Ticket deleted from Jira",
            )

        # Other errors - skip action but continue scenario
        return ReconciliationResult(
            strategy=AdaptationStrategy.SKIP,
            reason=f"Jira API error ({error}), skipping action",
        )
