"""TickExecutor for scheduled action execution with reconciliation."""

import logging
from typing import Optional, Callable, TYPE_CHECKING

import pendulum

from src.scheduling import Scheduler, ScheduledAction, ActionStatus
from src.reconciliation import (
    PreExecutionValidator,
    ReconciliationEngine,
    ExecutionTracker,
    AdaptationStrategy,
)
from src.reconciliation.circuit_breaker import ResilientJiraClient, CircuitBreakerError, PerTicketCircuitBreaker

if TYPE_CHECKING:
    from src.services.jira_client import JiraClient
    from src.state import SimulationState
    from src.chaos.pathfinding_adapter import PathfindingAdapter

logger = logging.getLogger(__name__)


class TickExecutor:
    """Execute scheduled actions within tick window.

    Replaces orchestrator's immediate execution with scheduled execution.
    Integrates with Phase 2 reconciliation for validation.

    The action_executor parameter bridges to existing CrewAI crews:
    - ScenarioOrchestrator._execute_action maps action_type to crew execution
    - TicketLifecycleCrew, BlockerCrew, ReworkCrew, etc. are preserved
    - This class adds timing/scheduling without replacing crew logic
    """

    def __init__(
        self,
        scheduler: Scheduler,
        jira_client: "JiraClient",
        max_actions_per_tick: int = 4,
        pathfinding_adapter: Optional["PathfindingAdapter"] = None,
        per_ticket_breaker: Optional[PerTicketCircuitBreaker] = None,
    ):
        self.scheduler = scheduler
        self.max_actions_per_tick = max_actions_per_tick
        self.pathfinding_adapter = pathfinding_adapter

        # Reconciliation components (from Phase 2)
        self.resilient_jira = ResilientJiraClient(jira_client)
        self.validator = PreExecutionValidator(self.resilient_jira)
        self.reconciler = ReconciliationEngine()
        self.execution_tracker = ExecutionTracker(cleanup_age_hours=48)

        # Per-ticket circuit breaker (Phase 5)
        self.per_ticket_breaker = per_ticket_breaker or PerTicketCircuitBreaker()

        # Tick metrics
        self._tick_metrics = {
            "executed": 0,
            "skipped": 0,
            "overdue_skipped": 0,
            "reconciliation_skips": 0,
            "recalculations": 0,
            "circuit_breaker_skips": 0,
        }

    def execute_tick(
        self,
        state: "SimulationState",
        action_executor: Callable[[dict, "SimulationState"], dict],
    ) -> dict:
        """Execute one simulation tick.

        Args:
            state: Current simulation state
            action_executor: Function to execute individual actions. This is typically
                            ScenarioOrchestrator._execute_action which maps action_type
                            to the appropriate CrewAI crew (TicketLifecycleCrew, etc.)
                            Signature: action_executor(action_dict, state) -> dict

        Returns:
            Dict with tick results
        """
        tick_start = self.scheduler.get_simulation_time()
        self._reset_metrics()

        results = {
            "tick_start": tick_start.isoformat(),
            "simulation_time": tick_start.isoformat(),
            "actions": [],
            "errors": [],
        }

        # Step 1: Mark overdue actions as skipped
        overdue_count = self.scheduler.mark_overdue_as_skipped()
        self._tick_metrics["overdue_skipped"] = overdue_count
        if overdue_count > 0:
            logger.info(f"Marked {overdue_count} overdue actions as skipped")

        # Step 2: Get due actions
        due_actions = self.scheduler.get_due_actions(
            max_actions=self.max_actions_per_tick
        )

        logger.info(
            f"Tick at {tick_start.format('YYYY-MM-DD HH:mm')}: "
            f"{len(due_actions)} actions due"
        )

        # Step 3: Execute each action with reconciliation
        for scheduled_action in due_actions:
            try:
                action_result = self._execute_scheduled_action(
                    scheduled_action,
                    state,
                    action_executor,
                )
                results["actions"].append(action_result)

            except Exception as e:
                logger.error(f"Action {scheduled_action.action_id} failed: {e}")
                results["errors"].append({
                    "action_id": scheduled_action.action_id,
                    "error": str(e),
                })
                self.scheduler.mark_action_skipped(
                    scheduled_action.action_id,
                    f"execution_error: {str(e)}"
                )

        # Step 4: Advance simulation time
        next_time = self.scheduler.advance_tick()

        results["tick_end"] = next_time.isoformat()
        results["next_simulation_time"] = next_time.isoformat()
        results["metrics"] = self._tick_metrics.copy()

        logger.info(
            f"Tick complete: executed={self._tick_metrics['executed']}, "
            f"skipped={self._tick_metrics['skipped']}"
        )

        return results

    def _execute_scheduled_action(
        self,
        scheduled_action: ScheduledAction,
        state: "SimulationState",
        action_executor: Callable[[dict, "SimulationState"], dict],
    ) -> dict:
        """Execute a single scheduled action with reconciliation.

        Returns action result dict.
        """
        action_id = scheduled_action.action_id
        ticket_key = scheduled_action.ticket_key
        action_type = scheduled_action.action_type

        # Check per-ticket circuit breaker FIRST (PERF-06)
        if not self.per_ticket_breaker.is_healthy(ticket_key):
            logger.warning(f"Skipping action for unhealthy ticket {ticket_key}")
            # Don't mark as skipped - keep pending for retry after reset
            self._tick_metrics["circuit_breaker_skips"] = (
                self._tick_metrics.get("circuit_breaker_skips", 0) + 1
            )
            return {
                "action_id": action_id,
                "action_type": action_type,
                "skipped": True,
                "reason": "per_ticket_circuit_breaker_open",
            }

        # Generate execution ID for idempotency
        execution_id = self.execution_tracker.generate_execution_id(
            action_type,
            ticket_key,
            scheduled_action.agent_id,
        )

        # Check idempotency
        if self.execution_tracker.is_executed(execution_id):
            logger.debug(f"Skipping duplicate execution: {execution_id}")
            self.scheduler.mark_action_skipped(action_id, "idempotent_skip")
            self._tick_metrics["skipped"] += 1
            return {
                "action_id": action_id,
                "action_type": action_type,
                "skipped": True,
                "reason": "idempotent_skip",
            }

        # Pre-execution validation (RECON-01)
        if scheduled_action.expected_status:
            try:
                validation = self.validator.validate_status(
                    ticket_key,
                    scheduled_action.expected_status,
                )

                if not validation.valid:
                    actual_status = validation.actual_state.get("status", "unknown")
                    reconciliation = self.reconciler.reconcile_status_mismatch(
                        ticket_key,
                        scheduled_action.expected_status,
                        actual_status,
                        action_type,
                    )

                    # Handle RECALCULATE strategy with pathfinding adapter
                    if reconciliation.strategy == AdaptationStrategy.RECALCULATE:
                        if self.pathfinding_adapter:
                            pathfinding_result = self.pathfinding_adapter.handle_reconciliation_result(
                                reconciliation,
                                scheduled_action,
                            )
                            if pathfinding_result:
                                logger.info(
                                    f"Recalculated path for {ticket_key}: "
                                    f"{pathfinding_result.to_dict()}"
                                )
                                self._tick_metrics["recalculations"] += 1
                        # Mark original action as skipped (handled by recalculation)
                        self.scheduler.mark_action_skipped(
                            action_id,
                            f"reconciliation_recalculate: {reconciliation.reason}"
                        )
                        self._tick_metrics["reconciliation_skips"] += 1
                        return {
                            "action_id": action_id,
                            "action_type": action_type,
                            "skipped": True,
                            "reason": reconciliation.reason,
                            "recalculated": True,
                        }

                    if reconciliation.strategy in [
                        AdaptationStrategy.CANCEL,
                        AdaptationStrategy.SKIP,
                    ]:
                        self.scheduler.mark_action_skipped(
                            action_id,
                            f"reconciliation_{reconciliation.strategy.value}"
                        )
                        self._tick_metrics["reconciliation_skips"] += 1
                        # Record failure to per-ticket circuit breaker
                        self.per_ticket_breaker.record_failure(ticket_key, reconciliation.reason)
                        return {
                            "action_id": action_id,
                            "action_type": action_type,
                            "skipped": True,
                            "reason": reconciliation.reason,
                        }

            except CircuitBreakerError:
                logger.warning(f"Circuit breaker open for {ticket_key}")
                # Don't mark as skipped - will retry next tick
                return {
                    "action_id": action_id,
                    "action_type": action_type,
                    "skipped": True,
                    "reason": "circuit_breaker_open",
                }

        # Convert ScheduledAction to action dict for executor
        # This dict format matches what ScenarioOrchestrator._execute_action expects
        action_dict = {
            "type": action_type,
            "ticket_key": ticket_key,
            "agent_id": scheduled_action.agent_id,
            "scenario_id": scheduled_action.scenario_id,
            **scheduled_action.params,
        }

        # Execute via provided executor (typically ScenarioOrchestrator._execute_action)
        # The executor maps action_type to CrewAI crews internally
        result = action_executor(action_dict, state)

        # Mark completed/skipped based on result
        if result.get("error") or result.get("skipped"):
            self.scheduler.mark_action_skipped(
                action_id,
                result.get("reason", result.get("error", "unknown"))
            )
            self._tick_metrics["skipped"] += 1
        else:
            self.scheduler.mark_action_completed(action_id, result)
            self.execution_tracker.record_execution(
                execution_id,
                action_type,
                ticket_key,
                "success",
            )
            # Record success to per-ticket circuit breaker
            self.per_ticket_breaker.record_success(ticket_key)
            self._tick_metrics["executed"] += 1

        result["action_id"] = action_id
        return result

    def _reset_metrics(self) -> None:
        """Reset tick metrics."""
        self._tick_metrics = {
            "executed": 0,
            "skipped": 0,
            "overdue_skipped": 0,
            "reconciliation_skips": 0,
            "recalculations": 0,
            "circuit_breaker_skips": 0,
        }
