"""Dynamic chaos probability tuner with EMA feedback loop.

Adjusts chaos injection probabilities based on sprint completion feedback:
- Below 60% completion: Reduce chaos by 20%
- Above 85% completion: Increase chaos by 5%
- In between: No change

Uses Exponential Moving Average (EMA) smoothing to prevent oscillation.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TuningResult:
    """Result of a tuning adjustment."""
    previous_multiplier: float
    new_multiplier: float
    completion_rate: float
    adjustment_direction: str  # "decrease", "increase", "none"
    adjustment_applied: float


class DynamicChaosTuner:
    """Adjust chaos probabilities based on sprint completion feedback.

    Uses EMA smoothing to gradually adjust probabilities:
    - alpha=0.2: 20% new value, 80% previous value
    - Prevents wild oscillation between sprints

    Thresholds:
    - completion_rate < 0.6: Too much chaos, reduce by 20%
    - completion_rate > 0.85: System healthy, can increase by 5%
    - Otherwise: No change

    Bounds:
    - min_multiplier=0.2: Never reduce chaos below 20% of base
    - max_multiplier=2.0: Never increase chaos above 200% of base
    """

    def __init__(
        self,
        alpha: float = 0.2,
        target_completion_rate: float = 0.7,
        low_threshold: float = 0.6,
        high_threshold: float = 0.85,
        min_multiplier: float = 0.2,
        max_multiplier: float = 2.0,
        decrease_factor: float = -0.2,
        increase_factor: float = 0.05,
    ):
        self.alpha = alpha
        self.target_completion_rate = target_completion_rate
        self.low_threshold = low_threshold
        self.high_threshold = high_threshold
        self.min_multiplier = min_multiplier
        self.max_multiplier = max_multiplier
        self.decrease_factor = decrease_factor
        self.increase_factor = increase_factor

        # Current state
        self.current_multiplier = 1.0
        self._adjustment_history: list[TuningResult] = []

    def adjust(self, completion_rate: float) -> TuningResult:
        """Adjust chaos multiplier based on completion rate.

        Args:
            completion_rate: Sprint completion rate (0.0-1.0)

        Returns:
            TuningResult with adjustment details
        """
        previous = self.current_multiplier

        # Determine adjustment direction
        if completion_rate < self.low_threshold:
            adjustment_factor = self.decrease_factor
            direction = "decrease"
        elif completion_rate > self.high_threshold:
            adjustment_factor = self.increase_factor
            direction = "increase"
        else:
            adjustment_factor = 0.0
            direction = "none"

        # Calculate target multiplier
        target = self.current_multiplier * (1 + adjustment_factor)

        # Apply EMA smoothing
        self.current_multiplier = (
            self.alpha * target +
            (1 - self.alpha) * self.current_multiplier
        )

        # Clamp to bounds
        self.current_multiplier = max(
            self.min_multiplier,
            min(self.max_multiplier, self.current_multiplier)
        )

        result = TuningResult(
            previous_multiplier=previous,
            new_multiplier=self.current_multiplier,
            completion_rate=completion_rate,
            adjustment_direction=direction,
            adjustment_applied=self.current_multiplier - previous,
        )

        self._adjustment_history.append(result)
        logger.info(
            f"Chaos tuning: {direction} from {previous:.3f} to {self.current_multiplier:.3f} "
            f"(completion_rate={completion_rate:.2f})"
        )

        return result

    def get_adjusted_probabilities(
        self,
        base_probabilities: dict[str, float]
    ) -> dict[str, float]:
        """Apply current multiplier to base probabilities.

        Args:
            base_probabilities: Original event probabilities from ChaosConfig

        Returns:
            Adjusted probabilities (capped at 1.0)
        """
        return {
            event_type: min(1.0, prob * self.current_multiplier)
            for event_type, prob in base_probabilities.items()
        }

    def reset(self) -> None:
        """Reset multiplier to default (1.0)."""
        self.current_multiplier = 1.0
        self._adjustment_history.clear()

    @property
    def adjustment_history(self) -> list[TuningResult]:
        """Get history of adjustments."""
        return self._adjustment_history.copy()

    def to_dict(self) -> dict:
        """Serialize current state for persistence."""
        return {
            "current_multiplier": self.current_multiplier,
            "alpha": self.alpha,
            "low_threshold": self.low_threshold,
            "high_threshold": self.high_threshold,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DynamicChaosTuner":
        """Restore from persisted state."""
        tuner = cls(
            alpha=data.get("alpha", 0.2),
            low_threshold=data.get("low_threshold", 0.6),
            high_threshold=data.get("high_threshold", 0.85),
        )
        tuner.current_multiplier = data.get("current_multiplier", 1.0)
        return tuner
