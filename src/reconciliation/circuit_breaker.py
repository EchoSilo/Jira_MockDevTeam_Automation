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
from typing import Any

from pybreaker import CircuitBreaker, CircuitBreakerError, CircuitBreakerListener

from src.services.jira_client import JiraClient

logger = logging.getLogger(__name__)

__all__ = [
    "ResilientJiraClient",
    "jira_read_breaker",
    "jira_write_breaker",
    "CircuitBreakerError",
]


class LoggingCircuitBreakerListener(CircuitBreakerListener):
    """Listener that logs circuit breaker state changes."""

    def state_change(self, cb: CircuitBreaker, old_state: Any, new_state: Any) -> None:
        """Log when circuit breaker changes state."""
        logger.warning(
            f"Circuit breaker '{cb.name}' changed from {old_state.name} to {new_state.name}"
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
            "reads": jira_read_breaker.current_state.name,
            "writes": jira_write_breaker.current_state.name,
        }

    # ==================== Pass-through ====================

    def __getattr__(self, name: str) -> Any:
        """Pass through non-wrapped methods to underlying client.

        This allows ResilientJiraClient to be a drop-in replacement for
        JiraClient without explicitly wrapping every method.
        """
        return getattr(self._client, name)
