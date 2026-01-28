"""Adaptation strategies for reconciliation engine.

This module defines the strategies used when Jira state diverges from
simulation plan, enabling graceful degradation and adaptive execution.
"""
from enum import Enum


class AdaptationStrategy(str, Enum):
    """Strategies for adapting when Jira state diverges from plan.

    Each strategy indicates how the simulation should handle the divergence:
    - CANCEL: Stop tracking this scenario, mark as invalidated
    - RECALCULATE: Recompute the action plan from current Jira state
    - RESCHEDULE: Retry the action later (transient failure)
    - PROCEED: Minor divergence, safe to continue with action
    - SKIP: Skip this specific action but continue the scenario
    """

    CANCEL = "cancel"
    RECALCULATE = "recalculate"
    RESCHEDULE = "reschedule"
    PROCEED = "proceed"
    SKIP = "skip"
