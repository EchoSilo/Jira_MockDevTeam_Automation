"""
Capacity planner for selecting backlog items based on velocity.

Selects backlog items that fit within velocity-derived capacity limits,
providing conservative sprint planning recommendations.
"""

from typing import List, Optional
from .velocity_tracker import VelocityTracker


class CapacityPlanner:
    """Select backlog items based on velocity-derived capacity."""

    def __init__(self, velocity_tracker: Optional[VelocityTracker] = None):
        """Initialize with optional VelocityTracker instance.

        Args:
            velocity_tracker: Optional tracker for velocity calculations.
                            If None, creates a new instance with no history.
        """
        self.velocity = velocity_tracker or VelocityTracker()

    def calculate_capacity(
        self,
        last_n_sprints: int = 3,
        buffer_percentage: float = 0.8
    ) -> int:
        """Calculate sprint capacity from velocity history.

        Returns 80% of average velocity (conservative buffer) by default.

        Args:
            last_n_sprints: Number of recent sprints to average (default: 3)
            buffer_percentage: Safety buffer multiplier (default: 0.8 = 80%)

        Returns:
            Recommended capacity in story points (0 if no history)
        """
        return self.velocity.get_capacity_recommendation(
            last_n_sprints=last_n_sprints,
            buffer_percentage=buffer_percentage,
        )

    def select_items(
        self,
        backlog: List[dict],
        capacity: int,
        max_items: int = 10
    ) -> List[dict]:
        """Select backlog items that fit within capacity.

        Args:
            backlog: List of items [{"key": "PROJ-100", "points": 5, ...}]
                     Assumes already sorted by priority (highest first)
            capacity: Maximum story points to commit
            max_items: Maximum number of items to select

        Returns:
            List of selected items that fit within capacity
        """
        selected = []
        total_points = 0

        for item in backlog:
            if len(selected) >= max_items:
                break

            item_points = item.get("points", 0) or item.get("story_points", 0)
            if item_points == 0:
                item_points = self._estimate_points(item)

            if total_points + item_points <= capacity:
                selected.append(item)
                total_points += item_points

        return selected

    def _estimate_points(self, item: dict) -> int:
        """Estimate points for unestimated items based on type.

        Provides reasonable defaults when items lack story point estimates.

        Args:
            item: Backlog item with optional "type" field

        Returns:
            Estimated story points (Bug: 2, Task: 3, Story: 5, Feature: 8)
        """
        item_type = item.get("type", "Story")
        estimates = {
            "Bug": 2,
            "Task": 3,
            "Story": 5,
            "Feature": 8,
        }
        return estimates.get(item_type, 3)

    def get_selection_summary(
        self,
        selected: List[dict]
    ) -> dict:
        """Get summary of selection for logging/display.

        Args:
            selected: List of selected backlog items

        Returns:
            Dict with item_count, total_points, and item keys
        """
        total_points = sum(
            item.get("points", 0) or item.get("story_points", 0) or self._estimate_points(item)
            for item in selected
        )
        return {
            "item_count": len(selected),
            "total_points": total_points,
            "items": [item.get("key") for item in selected],
        }
