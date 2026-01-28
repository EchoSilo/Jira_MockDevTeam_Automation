"""Data models for the reconciliation module.

This module provides the core data structures for pre-execution validation
and state reconciliation.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ValidationResult:
    """Result of pre-execution validation.

    Attributes:
        valid: Whether the validation passed.
        reason: If invalid, a descriptive reason explaining why.
        actual_state: The actual state observed in Jira (for debugging/logging).
        expected_state: The expected state we were checking for.

    Examples:
        >>> # Valid result
        >>> result = ValidationResult(valid=True)
        >>> assert result.valid and result.reason is None

        >>> # Invalid result with context
        >>> result = ValidationResult(
        ...     valid=False,
        ...     reason="Status changed: expected 'In Progress', got 'Done'",
        ...     actual_state={"status": "Done"},
        ...     expected_state={"status": "In Progress"}
        ... )
        >>> assert not result.valid and "Status changed" in result.reason
    """

    valid: bool
    reason: Optional[str] = None
    actual_state: Optional[dict] = None
    expected_state: Optional[dict] = None
