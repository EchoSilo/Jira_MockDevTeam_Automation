"""Reconciliation module for Jira state validation and divergence adaptation.

This module provides infrastructure for:
- Validating Jira state before actions (RECON-01)
- Ensuring idempotency during execution with retry scenarios (RECON-04)
- Detecting divergence between expected and actual Jira state (RECON-02)
- Deciding adaptation strategies (cancel, recalculate, reschedule, skip, proceed) (RECON-03)
- Tracking tombstone reasons for cancelled scenarios (RECON-06)
- Optimistic locking via Jira's updated timestamp (RECON-07)

Core Components:
    ValidationResult: Data model for validation results.
    PreExecutionValidator: Validates status, sprint membership, and assignee.
    OptimisticLockingValidator: Validates using Jira's updated timestamp.
    ExecutionTracker: Tracks execution IDs for idempotency.
    ExecutionRecord: Record of an executed action.
    ReconciliationEngine: Decides adaptation strategies for divergence.
    ReconciliationResult: Result of reconciliation decision.
    AdaptationStrategy: Enum of adaptation strategies.

Example:
    >>> from src.reconciliation import PreExecutionValidator, ValidationResult
    >>> from src.services.jira_client import JiraClient
    >>>
    >>> jira = JiraClient()
    >>> validator = PreExecutionValidator(jira_client=jira)
    >>>
    >>> result = validator.validate_status("ESCRUM-123", "In Progress")
    >>> if result.valid:
    ...     # Safe to proceed
    ...     pass
    >>> else:
    ...     # Handle divergence
    ...     print(f"Validation failed: {result.reason}")
"""

from .models import ValidationResult
from .validators import PreExecutionValidator, OptimisticLockingValidator
from .adapters import AdaptationStrategy
from .execution_tracker import ExecutionTracker, ExecutionRecord
from .reconciler import ReconciliationEngine, ReconciliationResult
from .staleness import cleanup_stale_scenarios

__all__ = [
    # Validation models
    "ValidationResult",
    # Pre-execution validators
    "PreExecutionValidator",
    "OptimisticLockingValidator",
    # Adaptation strategies
    "AdaptationStrategy",
    # Execution tracking (idempotency)
    "ExecutionTracker",
    "ExecutionRecord",
    # Reconciliation engine
    "ReconciliationEngine",
    "ReconciliationResult",
    # Staleness detection
    "cleanup_stale_scenarios",
]
