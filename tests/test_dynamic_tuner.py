"""Tests for dynamic chaos probability tuner."""

import pytest
from src.chaos.dynamic_tuner import DynamicChaosTuner, TuningResult


class TestDynamicChaosTuner:
    """Tests for DynamicChaosTuner feedback loop."""

    def test_low_completion_reduces_chaos(self):
        """Completion rate below 60% reduces chaos multiplier."""
        tuner = DynamicChaosTuner()
        result = tuner.adjust(0.5)  # 50% completion

        assert result.adjustment_direction == "decrease"
        assert result.new_multiplier < 1.0
        assert tuner.current_multiplier < 1.0

    def test_high_completion_increases_chaos(self):
        """Completion rate above 85% increases chaos multiplier."""
        tuner = DynamicChaosTuner()
        result = tuner.adjust(0.9)  # 90% completion

        assert result.adjustment_direction == "increase"
        assert result.new_multiplier > 1.0

    def test_normal_completion_no_change(self):
        """Completion rate between 60-85% makes minimal change."""
        tuner = DynamicChaosTuner()
        result = tuner.adjust(0.7)  # 70% completion

        assert result.adjustment_direction == "none"
        # Should be very close to 1.0 (only EMA smoothing effect)
        assert abs(result.new_multiplier - 1.0) < 0.01

    def test_ema_smoothing_prevents_oscillation(self):
        """Multiple adjustments show gradual change, not jumps."""
        tuner = DynamicChaosTuner(alpha=0.2)

        # Simulate 3 sprints with low completion
        for _ in range(3):
            tuner.adjust(0.5)

        # Should decrease gradually, not jump to minimum
        assert tuner.current_multiplier > 0.5  # Not too aggressive
        assert tuner.current_multiplier < 1.0  # But definitely decreased

    def test_multiplier_clamped_at_minimum(self):
        """Multiplier never goes below min_multiplier (0.2)."""
        tuner = DynamicChaosTuner(min_multiplier=0.2)

        # Many sprints with terrible completion
        for _ in range(50):
            tuner.adjust(0.1)  # 10% completion

        assert tuner.current_multiplier >= 0.2

    def test_multiplier_clamped_at_maximum(self):
        """Multiplier never exceeds max_multiplier (2.0)."""
        tuner = DynamicChaosTuner(max_multiplier=2.0)

        # Many sprints with excellent completion
        for _ in range(50):
            tuner.adjust(0.95)  # 95% completion

        assert tuner.current_multiplier <= 2.0

    def test_get_adjusted_probabilities(self):
        """Adjusted probabilities reflect current multiplier."""
        tuner = DynamicChaosTuner()
        tuner.current_multiplier = 0.5  # 50% of base

        base = {"urgent_bug": 0.1, "external_blocker": 0.2}
        adjusted = tuner.get_adjusted_probabilities(base)

        assert adjusted["urgent_bug"] == pytest.approx(0.05)
        assert adjusted["external_blocker"] == pytest.approx(0.1)

    def test_adjusted_probabilities_capped_at_one(self):
        """Adjusted probabilities don't exceed 1.0."""
        tuner = DynamicChaosTuner()
        tuner.current_multiplier = 2.0

        base = {"urgent_bug": 0.8}  # 0.8 * 2.0 = 1.6 -> capped to 1.0
        adjusted = tuner.get_adjusted_probabilities(base)

        assert adjusted["urgent_bug"] == 1.0

    def test_reset_restores_default(self):
        """Reset returns multiplier to 1.0."""
        tuner = DynamicChaosTuner()
        tuner.adjust(0.3)  # Decrease
        tuner.reset()

        assert tuner.current_multiplier == 1.0
        assert len(tuner.adjustment_history) == 0

    def test_serialization_roundtrip(self):
        """to_dict and from_dict preserve state."""
        tuner = DynamicChaosTuner()
        tuner.adjust(0.5)
        tuner.adjust(0.4)

        data = tuner.to_dict()
        restored = DynamicChaosTuner.from_dict(data)

        assert restored.current_multiplier == tuner.current_multiplier

    def test_requirement_perf04_feedback_loop(self):
        """PERF-04: Dynamic chaos adjustment via feedback loop.

        When sprint completion drops below 60%, chaos reduces by ~20%.
        """
        tuner = DynamicChaosTuner()

        # Simulate poor sprint
        result = tuner.adjust(0.55)  # 55% < 60% threshold

        # Verify decrease direction
        assert result.adjustment_direction == "decrease"
        # Verify ~20% reduction requested (EMA smoothes actual change)
        # With alpha=0.2, first adjustment moves 20% toward target
        # target = 1.0 * (1 - 0.2) = 0.8
        # new = 0.2 * 0.8 + 0.8 * 1.0 = 0.96
        assert result.new_multiplier < 1.0
