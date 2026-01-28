"""Staleness detection and cleanup for unvalidated scenarios."""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.state import SimulationState

logger = logging.getLogger(__name__)


def cleanup_stale_scenarios(
    state: "SimulationState",
    staleness_threshold: int = 4
) -> list[dict]:
    """Remove scenarios that haven't been validated in N ticks.

    Args:
        state: SimulationState to clean
        staleness_threshold: Number of ticks without validation before removal

    Returns:
        List of tombstone records for removed scenarios
    """
    tombstones = []
    stale_ids = []

    for scenario_id, scenario in state.active_scenarios.items():
        if scenario.is_stale(staleness_threshold):
            stale_ids.append(scenario_id)
            tombstone = {
                "scenario_id": scenario_id,
                "ticket_key": scenario.ticket_key,
                "reason": f"Stale scenario (unvalidated for {scenario.validation_tick_count} ticks)",
                "last_phase": scenario.current_phase.value,
            }
            tombstones.append(tombstone)
            logger.warning(
                f"Removing stale scenario {scenario.ticket_key} "
                f"(unvalidated for {scenario.validation_tick_count} ticks)"
            )

    for scenario_id in stale_ids:
        state.complete_scenario(scenario_id)
        # Record tombstone in action history
        state.record_action(
            agent_id="system",
            agent_name="System",
            action_type="scenario_invalidated",
            scenario_id=scenario_id,
            details=f"Stale scenario (unvalidated for {staleness_threshold}+ ticks)"
        )

    return tombstones
