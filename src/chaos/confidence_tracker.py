"""
Confidence tracker for scenario script fidelity.

Measures how closely execution matches the planned script and determines
when to trigger "accept reality" mode (abandon script due to divergence).
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.scenarios.sprint_scenario import SprintScenario


@dataclass
class ConfidenceScore:
    """
    Confidence score for a scenario's script fidelity.

    Tracks how many events executed as planned vs adapted,
    and whether accept reality mode should trigger.
    """

    script_fidelity: float  # 0.0-1.0: (executed_as_planned + positive) / total
    total_events: int
    executed_as_planned: int
    adapted_events: int
    external_overrides: int
    positive_adaptations: int  # Early completions, terminal status reached
    accept_reality: bool  # True if fidelity < threshold AND overrides >= limit


class ConfidenceTracker:
    """
    Tracks scenario confidence and determines when to accept reality.

    Accept reality mode triggers when:
    - Script fidelity < threshold (default 0.7)
    - AND external overrides >= override_limit (default 3)

    Positive adaptations (early completion, terminal status) count as
    executed_as_planned for fidelity calculation.
    """

    def __init__(self, threshold: float = 0.7, override_limit: int = 3):
        """
        Initialize confidence tracker.

        Args:
            threshold: Minimum fidelity to maintain script (default 0.7)
            override_limit: Minimum external overrides to trigger accept reality (default 3)
        """
        self.threshold = threshold
        self.override_limit = override_limit

    def calculate_confidence(self, scenario: "SprintScenario") -> ConfidenceScore:
        """
        Calculate confidence score for a scenario.

        Analyzes all events in the scenario script to determine:
        - How many executed as planned
        - How many were adapted
        - How many external overrides occurred
        - Whether accept reality should trigger

        Args:
            scenario: The sprint scenario to analyze

        Returns:
            ConfidenceScore with all metrics and accept_reality flag
        """
        total_events = 0
        executed_as_planned = 0
        adapted_events = 0
        external_overrides = 0
        positive_adaptations = 0

        # Count all events in script
        for script_day in scenario.script:
            for event in script_day.events:
                total_events += 1

                # Only count executed events in tallies
                if event.executed and event.execution_result:
                    result = event.execution_result

                    # Check if this is a positive adaptation
                    if result.get("positive_adaptation", False):
                        positive_adaptations += 1
                        adapted_events += 1
                    elif result.get("adapted", False):
                        # Regular adaptation (not positive)
                        adapted_events += 1
                    else:
                        # Executed as planned
                        executed_as_planned += 1

                    # Track external overrides separately (can overlap with adapted)
                    if result.get("external_override", False):
                        external_overrides += 1

        # Calculate fidelity
        if total_events == 0:
            # Empty scenario has perfect fidelity
            script_fidelity = 1.0
        else:
            # Fidelity = (executed as planned + positive adaptations) / total
            # Positive adaptations are good, so they count as "on script"
            script_fidelity = (executed_as_planned + positive_adaptations) / total_events

        # Determine if should accept reality
        # Both conditions must be met: low fidelity AND many overrides
        accept_reality = (
            script_fidelity < self.threshold and external_overrides >= self.override_limit
        )

        return ConfidenceScore(
            script_fidelity=script_fidelity,
            total_events=total_events,
            executed_as_planned=executed_as_planned,
            adapted_events=adapted_events,
            external_overrides=external_overrides,
            positive_adaptations=positive_adaptations,
            accept_reality=accept_reality,
        )

    def should_accept_reality(self, scenario: "SprintScenario") -> bool:
        """
        Convenience method to check if scenario should accept reality.

        Args:
            scenario: The sprint scenario to check

        Returns:
            True if accept reality mode should trigger
        """
        return self.calculate_confidence(scenario).accept_reality
