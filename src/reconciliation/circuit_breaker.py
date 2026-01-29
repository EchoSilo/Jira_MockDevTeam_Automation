"""Circuit breaker wrapper for Jira API resilience.

This module provides ResilientJiraClient, a wrapper around JiraClient that
uses circuit breakers to prevent cascade failures when the Jira API is
unavailable or experiencing issues.

Two separate circuit breakers are used:
- jira_read_breaker: For read operations (fail_max=5, timeout=60s)
- jira_write_breaker: For write operations (fail_max=3, timeout=120s)

The distinction allows writes to be protected more aggressively since failed
writes can cause data inconsistency, while reads can tolerate more failures.

CircuitBreakerError is re-exported for convenience. Callers can import from
either this module or directly from pybreaker:
    from src.reconciliation.circuit_breaker import CircuitBreakerError
    # or
    from pybreaker import CircuitBreakerError

Example:
    >>> from src.reconciliation.circuit_breaker import ResilientJiraClient
    >>> from src.services.jira_client import JiraClient
    >>> from pybreaker import CircuitBreakerError
    >>>
    >>> jira = JiraClient()
    >>> resilient = ResilientJiraClient(jira)
    >>>
    >>> try:
    ...     issue = resilient.get_issue("ESCRUM-123")
    ... except CircuitBreakerError:
    ...     # Circuit is open - Jira API is unavailable
    ...     # Reschedule the action for later
    ...     pass
"""

import logging
from dataclasses import dataclass
from typing import Any

import pendulum
from pybreaker import CircuitBreaker, CircuitBreakerError, CircuitBreakerListener

from src.services.jira_client import JiraClient

logger = logging.getLogger(__name__)

__all__ = [
    "ResilientJiraClient",
    "jira_read_breaker",
    "jira_write_breaker",
    "CircuitBreakerError",
    "PerTicketCircuitBreaker",
    "TicketHealth",
]


class LoggingCircuitBreakerListener(CircuitBreakerListener):
    """Listener that logs circuit breaker state changes."""

    def state_change(self, cb: CircuitBreaker, old_state: Any, new_state: Any) -> None:
        """Log when circuit breaker changes state."""
        logger.warning(
            f"Circuit breaker '{cb.name}' changed from {old_state} to {new_state}"
        )

    def failure(self, cb: CircuitBreaker, exc: Exception) -> None:
        """Log failures recorded by circuit breaker."""
        logger.debug(f"Circuit breaker '{cb.name}' recorded failure: {exc}")

    def success(self, cb: CircuitBreaker) -> None:
        """Log successes recorded by circuit breaker."""
        logger.debug(f"Circuit breaker '{cb.name}' recorded success")


# Separate breakers for reads vs writes
# Reads: higher failure tolerance (5 failures), faster recovery (60s)
jira_read_breaker = CircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    name="jira_reads",
    listeners=[LoggingCircuitBreakerListener()],
)

# Writes: lower tolerance (3 failures), slower recovery (120s)
# More conservative because failed writes can cause state inconsistency
jira_write_breaker = CircuitBreaker(
    fail_max=3,
    reset_timeout=120,
    name="jira_writes",
    listeners=[LoggingCircuitBreakerListener()],
)


class ResilientJiraClient:
    """JiraClient wrapper with circuit breaker protection.

    Wraps critical JiraClient methods with circuit breakers to prevent
    cascade failures when the Jira API is unavailable.

    Read operations use jira_read_breaker (fail_max=5, timeout=60s).
    Write operations use jira_write_breaker (fail_max=3, timeout=120s).

    Non-wrapped methods are passed through to the underlying client via
    __getattr__, so ResilientJiraClient can be used as a drop-in replacement.

    Attributes:
        _client: The underlying JiraClient instance.
    """

    def __init__(self, jira_client: JiraClient) -> None:
        """Initialize with a JiraClient instance.

        Args:
            jira_client: The JiraClient to wrap with circuit breaker protection.
        """
        self._client = jira_client

    # ==================== Read Operations ====================

    @jira_read_breaker
    def get_issue(self, issue_key: str) -> Any:
        """Fetch a single issue by key (protected by read breaker)."""
        return self._client.get_issue(issue_key)

    @jira_read_breaker
    def is_issue_in_active_sprint(self, issue_key: str) -> bool:
        """Check if issue is in active sprint (protected by read breaker)."""
        return self._client.is_issue_in_active_sprint(issue_key)

    @jira_read_breaker
    def get_project_issues(self, *args: Any, **kwargs: Any) -> list:
        """Fetch issues from project with filters (protected by read breaker)."""
        return self._client.get_project_issues(*args, **kwargs)

    @jira_read_breaker
    def get_active_sprint(self, *args: Any, **kwargs: Any) -> Any:
        """Get active sprint (protected by read breaker)."""
        return self._client.get_active_sprint(*args, **kwargs)

    @jira_read_breaker
    def get_transitions(self, issue_key: str) -> list:
        """Get available transitions for issue (protected by read breaker)."""
        return self._client.get_transitions(issue_key)

    # ==================== Write Operations ====================

    @jira_write_breaker
    def transition_issue(self, issue_key: str, transition_name: str) -> bool:
        """Transition an issue to a new status (protected by write breaker)."""
        return self._client.transition_issue(issue_key, transition_name)

    @jira_write_breaker
    def add_comment(self, issue_key: str, comment: str) -> None:
        """Add a comment to an issue (protected by write breaker)."""
        return self._client.add_comment(issue_key, comment)

    @jira_write_breaker
    def assign_issue(self, issue_key: str, account_id: str) -> None:
        """Assign an issue to a user (protected by write breaker)."""
        return self._client.assign_issue(issue_key, account_id)

    @jira_write_breaker
    def log_work(self, issue_key: str, time_spent: str, comment: str = None) -> None:
        """Log work time on an issue (protected by write breaker)."""
        return self._client.log_work(issue_key, time_spent, comment)

    @jira_write_breaker
    def create_issue(self, *args: Any, **kwargs: Any) -> Any:
        """Create a new issue (protected by write breaker)."""
        return self._client.create_issue(*args, **kwargs)

    @jira_write_breaker
    def update_issue(self, issue_key: str, fields: dict) -> None:
        """Update fields on an issue (protected by write breaker)."""
        return self._client.update_issue(issue_key, fields)

    # ==================== Circuit Breaker Status ====================

    def get_breaker_state(self) -> dict:
        """Get current state of both circuit breakers.

        Returns:
            Dict with 'reads' and 'writes' keys containing breaker state names.
            States are: 'closed' (normal), 'open' (failing), 'half-open' (testing).
        """
        return {
            "reads": jira_read_breaker.current_state,
            "writes": jira_write_breaker.current_state,
        }

    # ==================== Pass-through ====================

    def __getattr__(self, name: str) -> Any:
        """Pass through non-wrapped methods to underlying client.

        This allows ResilientJiraClient to be a drop-in replacement for
        JiraClient without explicitly wrapping every method.
        """
        return getattr(self._client, name)


@dataclass
class TicketHealth:
    """Health state for a single ticket."""
    ticket_key: str
    consecutive_failures: int = 0
    last_failure_reason: str | None = None
    last_failure_time: pendulum.DateTime | None = None
    is_healthy: bool = True


class PerTicketCircuitBreaker:
    """Per-ticket circuit breaker to prevent unbounded retry loops.

    Unlike the global circuit breaker (ResilientJiraClient) which protects
    the Jira API connection, this tracks failures per individual ticket.

    When a ticket fails precondition checks 3 times consecutively:
    1. Mark ticket as unhealthy
    2. Skip future actions for that ticket
    3. Log warning with failure reason

    This prevents retry storms where a broken ticket (moved externally,
    deleted, permission changed) causes repeated failures.

    The circuit breaker does NOT mark actions as permanently skipped -
    they stay pending in case the issue resolves. Manual intervention
    can reset a ticket's health.

    Attributes:
        failure_threshold: Failures before marking unhealthy (default: 3)
        reset_timeout_hours: Hours before auto-resetting unhealthy ticket
        _ticket_health: Dict tracking health per ticket_key
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        reset_timeout_hours: float = 24.0,
    ):
        self.failure_threshold = failure_threshold
        self.reset_timeout_hours = reset_timeout_hours
        self._ticket_health: dict[str, TicketHealth] = {}

    def is_healthy(self, ticket_key: str) -> bool:
        """Check if ticket is healthy for action execution.

        Returns True if:
        - Ticket has no recorded failures
        - Ticket has fewer than threshold failures
        - Ticket's circuit breaker has timed out and reset

        Args:
            ticket_key: Jira issue key (e.g., "ESCRUM-123")

        Returns:
            True if ticket is healthy, False if circuit is open
        """
        if ticket_key not in self._ticket_health:
            return True

        health = self._ticket_health[ticket_key]

        # Check for timeout-based reset
        if not health.is_healthy and health.last_failure_time:
            age_hours = (pendulum.now("UTC") - health.last_failure_time).total_hours()
            if age_hours >= self.reset_timeout_hours:
                logger.info(
                    f"Per-ticket circuit breaker reset for {ticket_key} "
                    f"after {age_hours:.1f} hours"
                )
                health.is_healthy = True
                health.consecutive_failures = 0
                return True

        return health.is_healthy

    def record_failure(self, ticket_key: str, reason: str) -> bool:
        """Record a failure for a ticket.

        Args:
            ticket_key: Jira issue key
            reason: Why the action failed

        Returns:
            True if circuit breaker is now open (ticket unhealthy)
        """
        if ticket_key not in self._ticket_health:
            self._ticket_health[ticket_key] = TicketHealth(ticket_key=ticket_key)

        health = self._ticket_health[ticket_key]
        health.consecutive_failures += 1
        health.last_failure_reason = reason
        health.last_failure_time = pendulum.now("UTC")

        if health.consecutive_failures >= self.failure_threshold:
            if health.is_healthy:  # Only log on transition
                logger.warning(
                    f"Per-ticket circuit breaker OPEN for {ticket_key}: "
                    f"{health.consecutive_failures} consecutive failures. "
                    f"Reason: {reason}"
                )
            health.is_healthy = False
            return True

        logger.debug(
            f"Ticket {ticket_key} failure #{health.consecutive_failures}: {reason}"
        )
        return False

    def record_success(self, ticket_key: str) -> None:
        """Record a successful action for a ticket.

        Resets consecutive failure count and marks healthy.
        """
        if ticket_key not in self._ticket_health:
            return  # No failures recorded, nothing to reset

        health = self._ticket_health[ticket_key]
        if health.consecutive_failures > 0 or not health.is_healthy:
            logger.debug(f"Ticket {ticket_key} recovered, resetting circuit breaker")
        health.consecutive_failures = 0
        health.is_healthy = True

    def get_unhealthy_tickets(self) -> list[str]:
        """Get list of currently unhealthy ticket keys."""
        return [
            key for key, health in self._ticket_health.items()
            if not health.is_healthy
        ]

    def get_ticket_health(self, ticket_key: str) -> TicketHealth | None:
        """Get health status for a specific ticket."""
        return self._ticket_health.get(ticket_key)

    def reset_ticket(self, ticket_key: str) -> None:
        """Manually reset a ticket's circuit breaker."""
        if ticket_key in self._ticket_health:
            logger.info(f"Manually resetting circuit breaker for {ticket_key}")
            del self._ticket_health[ticket_key]

    def reset_all(self) -> None:
        """Reset all ticket circuit breakers."""
        count = len(self._ticket_health)
        self._ticket_health.clear()
        logger.info(f"Reset all per-ticket circuit breakers ({count} tickets)")

    def get_stats(self) -> dict:
        """Get statistics about circuit breaker state."""
        unhealthy = [h for h in self._ticket_health.values() if not h.is_healthy]
        return {
            "total_tracked": len(self._ticket_health),
            "unhealthy_count": len(unhealthy),
            "unhealthy_tickets": [h.ticket_key for h in unhealthy],
        }
