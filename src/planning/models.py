"""
Planning models for sprint planning and horizon management.

Provides:
- SprintPlan: Tracks planned sprints with committed items and scenarios
- PlanningHorizon: Maintains 2-3 future sprint plans for continuous planning
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from enum import Enum
import pendulum
import uuid


class SprintPlanStatus(str, Enum):
    """Status of a planned sprint."""
    PLANNED = "planned"      # Future sprint, not yet started
    ACTIVE = "active"        # Currently running
    COMPLETED = "completed"  # Finished


class SprintPlan(BaseModel):
    """A planned sprint with committed items and scenario.

    Tracks sprint dates, committed backlog items, and scenario scripts
    for 2-3 sprint lookahead planning.
    """
    sprint_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    sprint_number: int
    start_date: pendulum.DateTime
    end_date: pendulum.DateTime

    # Committed items from backlog
    committed_items: List[str] = Field(default_factory=list)  # ticket_keys
    committed_points: int = 0

    # Scenario script for this sprint
    scenario_id: Optional[str] = None

    # Planning metadata
    status: SprintPlanStatus = SprintPlanStatus.PLANNED
    planned_at: pendulum.DateTime = Field(default_factory=lambda: pendulum.now("UTC"))
    velocity_estimate: Optional[int] = None  # Team velocity when planned

    @field_validator("start_date", "end_date", "planned_at", mode="before")
    @classmethod
    def _coerce_pendulum_datetime(cls, v):
        """Parse ISO strings back into pendulum.DateTime when reloading from state.

        Serialization writes these as ISO strings (see json_encoders), but with
        arbitrary_types_allowed pydantic will not coerce them back automatically,
        so reload of a PlanningHorizon fails with is_instance_of errors. This
        pre-validator restores the round-trip.
        """
        if isinstance(v, str):
            return pendulum.parse(v)
        return v

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            pendulum.DateTime: lambda v: v.isoformat()
        }


class PlanningHorizon(BaseModel):
    """Maintains 2-3 future sprint plans.

    Ensures there are always 2+ future sprints planned with at least
    14 days of planned work ahead. Triggers planning when horizon
    gets too short.
    """
    future_sprints: List[SprintPlan] = Field(default_factory=list)
    min_sprints: int = 3   # Minimum sprints to maintain (overridable from settings.planning_horizon_sprints)
    min_days_ahead: int = 14  # Minimum days of planned work

    # Estimated points at risk of spilling out of the active sprint, based on
    # its current burndown pace vs. ideal. Recomputed and overwritten every
    # tick (src/main.py _update_predicted_spillover) - safe to store here
    # since, unlike last_planned_for_sprint, it has no cross-tick persistence
    # requirement (this object is rebuilt from Jira every tick anyway).
    predicted_spillover_points: int = 0

    def get_sprint_count(self) -> int:
        """Get number of planned future sprints (not active/completed)."""
        return len([s for s in self.future_sprints if s.status == SprintPlanStatus.PLANNED])

    def needs_planning(self) -> bool:
        """Check if we need to plan more sprints.

        Returns True if:
        - Fewer than min_sprints planned sprints exist
        - OR farthest sprint ends in less than min_days_ahead
        """
        planned = [s for s in self.future_sprints if s.status == SprintPlanStatus.PLANNED]
        if len(planned) < self.min_sprints:
            return True

        # Also check if farthest sprint is far enough in future
        if planned:
            farthest_end = max(s.end_date for s in planned)
            days_until_end = (farthest_end - pendulum.now("UTC")).days
            return days_until_end < self.min_days_ahead

        return True

    def get_next_sprint_number(self, current_sprint: int) -> int:
        """Calculate next sprint number to plan."""
        if not self.future_sprints:
            return current_sprint + 1
        max_planned = max(s.sprint_number for s in self.future_sprints)
        return max_planned + 1

    def add_sprint_plan(self, plan: SprintPlan) -> None:
        """Add a new sprint plan to horizon."""
        self.future_sprints.append(plan)

    def activate_sprint(self, sprint_number: int) -> Optional[SprintPlan]:
        """Mark sprint as active and return it."""
        for sprint in self.future_sprints:
            if sprint.sprint_number == sprint_number:
                sprint.status = SprintPlanStatus.ACTIVE
                return sprint
        return None

    def complete_sprint(self, sprint_number: int) -> Optional[SprintPlan]:
        """Mark sprint as completed."""
        for sprint in self.future_sprints:
            if sprint.sprint_number == sprint_number:
                sprint.status = SprintPlanStatus.COMPLETED
                return sprint
        return None

    def get_active_plan(self) -> Optional[SprintPlan]:
        """Get the currently active sprint plan."""
        for sprint in self.future_sprints:
            if sprint.status == SprintPlanStatus.ACTIVE:
                return sprint
        return None

    def cleanup_old_sprints(self, days: int = 30) -> int:
        """Remove completed sprints older than days.

        Args:
            days: Keep completed sprints from last N days

        Returns:
            Number of sprints removed
        """
        cutoff = pendulum.now("UTC").subtract(days=days)
        original = len(self.future_sprints)
        self.future_sprints = [
            s for s in self.future_sprints
            if s.status != SprintPlanStatus.COMPLETED or s.end_date > cutoff
        ]
        return original - len(self.future_sprints)
