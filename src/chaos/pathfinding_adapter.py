"""
PathfindingAdapter handles RECALCULATE strategy by using WorkflowPathfinder.

Integrates adaptive pathfinding with the reconciliation system to automatically
recalculate workflow paths when Jira ticket status diverges from expected state.
"""

from dataclasses import dataclass, field
from typing import Optional
import logging
import re

import pendulum

from src.scheduling.scheduler import Scheduler
from src.scheduling.models import ScheduledAction, ActionStatus
from src.orchestrator.pathfinder import WorkflowPathfinder
from src.reconciliation.reconciler import ReconciliationResult
from src.reconciliation.adapters import AdaptationStrategy

logger = logging.getLogger(__name__)


@dataclass
class PathfindingResult:
    """Result of pathfinding recalculation."""
    ticket_key: str
    actions_scheduled: list[ScheduledAction] = field(default_factory=list)
    actions_adapted: list[str] = field(default_factory=list)  # action_ids marked ADAPTED
    summary: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for logging/reporting."""
        return {
            "ticket_key": self.ticket_key,
            "scheduled_count": len(self.actions_scheduled),
            "adapted_count": len(self.actions_adapted),
            "summary": self.summary,
        }


class PathfindingAdapter:
    """
    Handles RECALCULATE strategy by using WorkflowPathfinder to compute new paths.

    Integrates with TickExecutor for adaptive workflow handling:
    1. Receives RECALCULATE decision from reconciliation
    2. Uses WorkflowPathfinder to compute new action sequence
    3. Marks original actions as ADAPTED
    4. Schedules new actions in the queue
    """

    # Role mapping for agent assignment (simple fallback)
    ROLE_TO_AGENT = {
        "developer": "developer",
        "tech_lead": "tech_lead",
        "qa": "qa",
        "pm": "pm",
    }

    def __init__(
        self,
        scheduler: Scheduler,
        pathfinder: WorkflowPathfinder,
        agent_pool: Optional[dict] = None,
    ):
        """Initialize adapter with scheduler and pathfinder.

        Args:
            scheduler: Scheduler to modify actions through
            pathfinder: WorkflowPathfinder for computing new paths
            agent_pool: Dict mapping roles to available agents (optional)
        """
        self.scheduler = scheduler
        self.pathfinder = pathfinder
        self.agent_pool = agent_pool or self.ROLE_TO_AGENT

    def handle_reconciliation_result(
        self,
        reconciliation: ReconciliationResult,
        scheduled_action: ScheduledAction,
    ) -> Optional[PathfindingResult]:
        """
        Process reconciliation result and trigger recalculation if needed.

        Args:
            reconciliation: ReconciliationResult from reconciliation engine
            scheduled_action: The scheduled action that triggered reconciliation

        Returns:
            PathfindingResult if recalculation occurred, None otherwise
        """
        if reconciliation.strategy != AdaptationStrategy.RECALCULATE:
            return None

        # Extract current status from reconciliation reason
        current_status = self._extract_status_from_reason(reconciliation.reason)
        if not current_status:
            logger.warning(
                f"Cannot extract status from reason: {reconciliation.reason}"
            )
            return None

        # Recalculate remaining script
        return self.handle_recalculate(
            ticket_key=scheduled_action.ticket_key,
            current_status=current_status,
            scenario_id=scheduled_action.scenario_id,
        )

    def handle_recalculate(
        self,
        ticket_key: str,
        current_status: str,
        target_status: str = "done",
        scenario_id: Optional[str] = None,
    ) -> PathfindingResult:
        """
        Handle RECALCULATE strategy by computing new path and scheduling actions.

        Args:
            ticket_key: Jira ticket key (e.g., "ESCRUM-123")
            current_status: Current actual status from Jira
            target_status: Target status to reach (default: "done")
            scenario_id: Scenario ID to associate with new actions

        Returns:
            PathfindingResult with scheduled and adapted actions
        """
        result = PathfindingResult(ticket_key=ticket_key)

        # Step 1: Compute new path using pathfinder
        new_actions = self.pathfinder.recalculate_remaining_script(
            current_status=current_status,
            target_status=target_status,
        )

        if not new_actions:
            logger.warning(
                f"No path found from '{current_status}' to '{target_status}' "
                f"for ticket {ticket_key}"
            )
            result.summary = f"No path found from '{current_status}' to '{target_status}'"
            return result

        # Step 2: Mark all pending actions for this ticket as ADAPTED
        adapted_count = self._mark_pending_actions_adapted(
            ticket_key=ticket_key,
            reason=f"Status divergence detected, recalculating from '{current_status}'",
        )
        result.actions_adapted = [
            f"{ticket_key}_{i}" for i in range(adapted_count)
        ]  # Placeholder IDs

        # Step 3: Schedule new actions
        current_time = self.scheduler.get_simulation_time()
        for i, action_spec in enumerate(new_actions):
            # Find agent for role
            agent_id = self._get_agent_for_role(action_spec.get("role"))
            if not agent_id:
                logger.warning(
                    f"No agent found for role {action_spec.get('role')}, "
                    f"skipping action {action_spec.get('type')}"
                )
                continue

            # Schedule action with staggered timing
            scheduled_action = ScheduledAction(
                scheduled_time=current_time.add(minutes=15 * (i + 1)),
                action_type=action_spec["type"],
                agent_id=agent_id,
                ticket_key=ticket_key,
                scenario_id=scenario_id,
                window_minutes=30,
                expected_status=action_spec.get("target_status"),
                params={
                    "recalculated": True,
                    "from_status": current_status,
                    "to_status": action_spec.get("target_status"),
                },
            )
            self.scheduler.schedule_action(scheduled_action)
            result.actions_scheduled.append(scheduled_action)

        result.summary = (
            f"Recalculated path from '{current_status}' to '{target_status}': "
            f"scheduled {len(result.actions_scheduled)} actions, "
            f"marked {adapted_count} actions as adapted"
        )
        logger.info(f"Pathfinding recalculation for {ticket_key}: {result.to_dict()}")

        return result

    def _extract_status_from_reason(self, reason: str) -> Optional[str]:
        """
        Extract current status from reconciliation reason string.

        Expects format like: "Ticket regressed to 'In Progress', recalculating plan"

        Args:
            reason: Reconciliation reason string

        Returns:
            Extracted status or None if not found
        """
        # Pattern: look for status in single quotes
        match = re.search(r"regressed to '([^']+)'", reason)
        if match:
            return match.group(1)

        # Alternative pattern: look for "to 'Status'"
        match = re.search(r"to '([^']+)'", reason)
        if match:
            return match.group(1)

        return None

    def _mark_pending_actions_adapted(
        self,
        ticket_key: str,
        reason: str,
    ) -> int:
        """
        Mark all pending actions for a ticket as ADAPTED.

        Args:
            ticket_key: Jira ticket key
            reason: Reason for adaptation

        Returns:
            Count of actions marked
        """
        adapted_count = 0
        pending_actions = self._get_pending_actions_for_ticket(ticket_key)

        for action in pending_actions:
            action.status = ActionStatus.ADAPTED
            action.result = {"reason": reason}
            self.scheduler.store.update_status(
                action.action_id,
                ActionStatus.ADAPTED,
                result=action.result,
                executed_at=pendulum.now("UTC"),
            )
            adapted_count += 1

        return adapted_count

    def _get_pending_actions_for_ticket(self, ticket_key: str) -> list[ScheduledAction]:
        """
        Get all pending actions for a specific ticket.

        Args:
            ticket_key: Jira ticket key

        Returns:
            List of pending actions for the ticket
        """
        pending = []
        for action in self.scheduler.queue._heap:
            if (
                action.status == ActionStatus.PENDING
                and action.ticket_key == ticket_key
            ):
                pending.append(action)
        return pending

    def _get_agent_for_role(self, role: Optional[str]) -> Optional[str]:
        """
        Get agent ID for a given role.

        Args:
            role: Role name (e.g., "developer", "qa")

        Returns:
            Agent ID or None if role not found
        """
        if not role:
            return None
        return self.agent_pool.get(role)
