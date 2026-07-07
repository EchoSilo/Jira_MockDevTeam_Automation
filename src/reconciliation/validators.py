"""Pre-execution validators for Jira state verification.

This module provides validators that check Jira ticket state before action
execution. These validators are the foundation for reconciliation logic,
ensuring the simulation doesn't act on stale or changed state.

Validators:
    PreExecutionValidator: Validates status, sprint membership, and assignee.
    OptimisticLockingValidator: Validates using Jira's updated timestamp.

Requirements covered:
    RECON-01: Pre-execution validation checks Jira ticket state
    RECON-07: Optimistic locking via updated timestamp

Example:
    >>> from src.services.jira_client import JiraClient
    >>> from src.reconciliation.validators import PreExecutionValidator
    >>>
    >>> jira = JiraClient()
    >>> validator = PreExecutionValidator(jira_client=jira)
    >>>
    >>> result = validator.validate_status("ESCRUM-123", "In Progress")
    >>> if result.valid:
    ...     # Safe to proceed with action
    ...     pass
    >>> else:
    ...     # Handle divergence
    ...     print(f"Validation failed: {result.reason}")
"""

from typing import Optional, Union
import logging
import pendulum

from src.reconciliation.models import ValidationResult
from src.services.jira_client import JiraClient

logger = logging.getLogger(__name__)


class PreExecutionValidator:
    """Validates Jira state before action execution.

    This validator checks that the ticket is in the expected state before
    performing any action. This prevents the simulation from acting on
    tickets that have been modified by users or other processes.

    Attributes:
        jira: The JiraClient instance for API calls.

    Example:
        >>> validator = PreExecutionValidator(jira_client=jira)
        >>> result = validator.validate_status("ESCRUM-123", "In Progress")
        >>> if result.valid:
        ...     # Ticket is in expected status, safe to proceed
        ...     pass
    """

    def __init__(self, jira_client: JiraClient):
        """Initialize the validator with a JiraClient.

        Args:
            jira_client: The JiraClient instance for Jira API calls.
        """
        self.jira = jira_client

    def validate_status(
        self,
        ticket_key: str,
        expected_status: str,
    ) -> ValidationResult:
        """Validate ticket is in expected status.

        Args:
            ticket_key: Jira ticket key (e.g., "ESCRUM-123").
            expected_status: Expected status name (e.g., "In Progress").

        Returns:
            ValidationResult with valid=True if status matches, otherwise
            valid=False with descriptive reason.

        Example:
            >>> result = validator.validate_status("ESCRUM-123", "In Progress")
            >>> if result.valid:
            ...     print("Status matches, proceed with action")
            ... else:
            ...     print(f"Status mismatch: {result.reason}")
        """
        try:
            issue = self.jira.get_issue(ticket_key)
            actual_status = issue.fields.status.name

            # Case-insensitive: Jira workflows may name statuses in any case
            # (e.g. "CODE REVIEW"/"READY FOR QA") while the simulation uses
            # title case ("Code Review"/"Ready for QA").
            if actual_status.strip().lower() != expected_status.strip().lower():
                return ValidationResult(
                    valid=False,
                    reason=f"Status changed: expected '{expected_status}', got '{actual_status}'",
                    actual_state={"status": actual_status},
                    expected_state={"status": expected_status},
                )

            return ValidationResult(valid=True)

        except Exception as e:
            logger.warning(f"Jira API error validating status for {ticket_key}: {e}")
            return ValidationResult(
                valid=False,
                reason=f"Jira API error: {str(e)}",
            )

    def validate_sprint_membership(
        self,
        ticket_key: str,
        expected_in_sprint: bool = True,
    ) -> ValidationResult:
        """Validate ticket's sprint membership status.

        Args:
            ticket_key: Jira ticket key (e.g., "ESCRUM-123").
            expected_in_sprint: Whether the ticket should be in the active sprint.

        Returns:
            ValidationResult with valid=True if sprint membership matches,
            otherwise valid=False with descriptive reason.

        Example:
            >>> result = validator.validate_sprint_membership("ESCRUM-123", expected_in_sprint=True)
            >>> if not result.valid:
            ...     print("Ticket was removed from sprint!")
        """
        try:
            in_sprint = self.jira.is_issue_in_active_sprint(ticket_key)

            if in_sprint != expected_in_sprint:
                return ValidationResult(
                    valid=False,
                    reason=(
                        f"Sprint membership changed: expected in_sprint={expected_in_sprint}, "
                        f"got {in_sprint}"
                    ),
                    actual_state={"in_active_sprint": in_sprint},
                    expected_state={"in_active_sprint": expected_in_sprint},
                )

            return ValidationResult(valid=True)

        except Exception as e:
            logger.warning(
                f"Jira API error validating sprint membership for {ticket_key}: {e}"
            )
            return ValidationResult(
                valid=False,
                reason=f"Jira API error: {str(e)}",
            )

    def validate_assignee(
        self,
        ticket_key: str,
        expected_assignee_id: Optional[str] = None,
    ) -> ValidationResult:
        """Validate ticket's assignee.

        Args:
            ticket_key: Jira ticket key (e.g., "ESCRUM-123").
            expected_assignee_id: Expected assignee account ID, or None if
                expecting the ticket to be unassigned.

        Returns:
            ValidationResult with valid=True if assignee matches,
            otherwise valid=False with descriptive reason.

        Example:
            >>> result = validator.validate_assignee("ESCRUM-123", expected_assignee_id="user-123")
            >>> if not result.valid:
            ...     print("Ticket was reassigned!")
        """
        try:
            issue = self.jira.get_issue(ticket_key)
            actual_assignee = issue.fields.assignee
            actual_assignee_id = (
                actual_assignee.accountId if actual_assignee else None
            )

            if actual_assignee_id != expected_assignee_id:
                return ValidationResult(
                    valid=False,
                    reason=(
                        f"Assignee changed: expected '{expected_assignee_id}', "
                        f"got '{actual_assignee_id}'"
                    ),
                    actual_state={"assignee_id": actual_assignee_id},
                    expected_state={"assignee_id": expected_assignee_id},
                )

            return ValidationResult(valid=True)

        except Exception as e:
            logger.warning(f"Jira API error validating assignee for {ticket_key}: {e}")
            return ValidationResult(
                valid=False,
                reason=f"Jira API error: {str(e)}",
            )


class OptimisticLockingValidator:
    """Validates using Jira's updated timestamp for optimistic locking.

    Optimistic locking detects when a ticket has been modified since we last
    read it, preventing race conditions where we might act on stale state.

    This validator compares Jira's `updated` field against a known timestamp
    to detect concurrent modifications.

    Attributes:
        jira: The JiraClient instance for API calls.

    Example:
        >>> validator = OptimisticLockingValidator(jira_client=jira)
        >>> result = validator.validate_with_timestamp(
        ...     ticket_key="ESCRUM-123",
        ...     expected_status="In Progress",
        ...     last_known_updated="2026-01-28T10:00:00+00:00"
        ... )
        >>> if not result.valid:
        ...     print("Ticket was modified by another process!")
    """

    def __init__(self, jira_client: JiraClient):
        """Initialize the validator with a JiraClient.

        Args:
            jira_client: The JiraClient instance for Jira API calls.
        """
        self.jira = jira_client

    def validate_with_timestamp(
        self,
        ticket_key: str,
        expected_status: str,
        last_known_updated: Union[str, pendulum.DateTime],
    ) -> ValidationResult:
        """Validate ticket hasn't changed since last_known_updated.

        This is optimistic locking: we assume no conflict, but verify
        before writing by comparing timestamps. If the ticket's `updated`
        field is newer than `last_known_updated`, we know someone else
        modified it.

        Args:
            ticket_key: Jira ticket key (e.g., "ESCRUM-123").
            expected_status: Expected status name (e.g., "In Progress").
            last_known_updated: ISO 8601 timestamp or pendulum DateTime of
                when we last read the ticket.

        Returns:
            ValidationResult with valid=True if no modifications detected,
            otherwise valid=False with descriptive reason.

        Example:
            >>> # Using ISO 8601 string
            >>> result = validator.validate_with_timestamp(
            ...     "ESCRUM-123",
            ...     "In Progress",
            ...     "2026-01-28T10:00:00+00:00"
            ... )
            >>>
            >>> # Using pendulum DateTime
            >>> last_seen = pendulum.datetime(2026, 1, 28, 10, 0, tz="UTC")
            >>> result = validator.validate_with_timestamp(
            ...     "ESCRUM-123",
            ...     "In Progress",
            ...     last_seen
            ... )
        """
        try:
            issue = self.jira.get_issue(ticket_key)

            # Parse Jira's updated timestamp
            # Format: "2026-01-28T10:30:45.123+0000"
            current_updated = pendulum.parse(issue.fields.updated)

            # Parse last_known if it's a string
            if isinstance(last_known_updated, str):
                last_known = pendulum.parse(last_known_updated)
            else:
                last_known = last_known_updated

            # Check if modified since last read (optimistic locking)
            if current_updated > last_known:
                return ValidationResult(
                    valid=False,
                    reason=(
                        f"Optimistic lock failed: ticket modified at "
                        f"{current_updated.isoformat()} "
                        f"(last known: {last_known.isoformat()})"
                    ),
                    actual_state={
                        "updated": current_updated.isoformat(),
                        "status": issue.fields.status.name,
                    },
                    expected_state={
                        "updated_before": last_known.isoformat(),
                        "status": expected_status,
                    },
                )

            # Also check status still matches
            actual_status = issue.fields.status.name
            if actual_status != expected_status:
                return ValidationResult(
                    valid=False,
                    reason=(
                        f"Status changed: expected '{expected_status}', "
                        f"got '{actual_status}'"
                    ),
                    actual_state={"status": actual_status},
                    expected_state={"status": expected_status},
                )

            return ValidationResult(valid=True)

        except Exception as e:
            logger.warning(
                f"Jira API error validating with timestamp for {ticket_key}: {e}"
            )
            return ValidationResult(
                valid=False,
                reason=f"Jira API error: {str(e)}",
            )
