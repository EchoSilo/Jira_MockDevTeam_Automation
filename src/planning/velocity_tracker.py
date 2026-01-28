"""
Velocity tracker for sprint capacity planning.

Tracks historical sprint velocity (story points completed) and provides
capacity recommendations based on the last 3 completed sprints.
"""

from pydantic import BaseModel, Field
from typing import List


class SprintVelocityRecord(BaseModel):
    """Record of a completed sprint's velocity.

    Tracks committed vs completed story points for velocity trending
    and capacity planning.
    """
    sprint_number: int
    committed: int  # Story points committed at sprint start
    completed: int  # Story points actually completed
    status: str = "completed"  # completed | in_progress

    @property
    def completion_rate(self) -> float:
        """Calculate completion rate (0-1).

        Returns:
            Ratio of completed to committed points (0.0 if no commitment)
        """
        if self.committed == 0:
            return 0.0
        return self.completed / self.committed


class VelocityTracker(BaseModel):
    """Track sprint velocity for capacity planning.

    Maintains historical velocity records and calculates rolling averages
    for capacity recommendations. Excludes in-progress sprints from
    calculations to avoid distortion.
    """
    sprint_history: List[SprintVelocityRecord] = Field(default_factory=list)

    def record_sprint(
        self,
        sprint_number: int,
        committed: int,
        completed: int,
        status: str = "completed"
    ) -> None:
        """Record sprint results.

        Updates existing record if sprint already exists, otherwise adds new.

        Args:
            sprint_number: Sprint identifier
            committed: Story points committed at sprint start
            completed: Story points completed by sprint end
            status: "completed" or "in_progress"
        """
        # Update if exists, otherwise add
        for record in self.sprint_history:
            if record.sprint_number == sprint_number:
                record.committed = committed
                record.completed = completed
                record.status = status
                return
        self.sprint_history.append(SprintVelocityRecord(
            sprint_number=sprint_number,
            committed=committed,
            completed=completed,
            status=status,
        ))

    def get_average_velocity(self, last_n_sprints: int = 3) -> int:
        """Calculate average velocity from last N COMPLETED sprints.

        Excludes in-progress sprints to avoid distortion from partial work.

        Args:
            last_n_sprints: Number of recent sprints to average (default: 3)

        Returns:
            Average story points completed per sprint (0 if no completed sprints)
        """
        completed_sprints = [
            s for s in self.sprint_history
            if s.status == "completed"
        ]
        if not completed_sprints:
            return 0

        # Get last N completed sprints
        recent = sorted(completed_sprints, key=lambda s: s.sprint_number)[-last_n_sprints:]
        if not recent:
            return 0

        total_completed = sum(s.completed for s in recent)
        return total_completed // len(recent)

    def get_completion_rate(self, last_n_sprints: int = 3) -> float:
        """Calculate average completion rate from last N completed sprints.

        Args:
            last_n_sprints: Number of recent sprints to average (default: 3)

        Returns:
            Average completion rate (0.0-1.0, or 0.0 if no completed sprints)
        """
        completed_sprints = [
            s for s in self.sprint_history
            if s.status == "completed"
        ]
        if not completed_sprints:
            return 0.0

        recent = sorted(completed_sprints, key=lambda s: s.sprint_number)[-last_n_sprints:]
        if not recent:
            return 0.0

        total_rate = sum(s.completion_rate for s in recent)
        return total_rate / len(recent)

    def get_capacity_recommendation(
        self,
        last_n_sprints: int = 3,
        buffer_percentage: float = 0.8
    ) -> int:
        """Get recommended capacity for next sprint.

        Returns conservative estimate (80% of average velocity by default)
        to provide buffer for unknowns and dependencies.

        Args:
            last_n_sprints: Number of recent sprints to average (default: 3)
            buffer_percentage: Safety buffer multiplier (default: 0.8 = 80%)

        Returns:
            Recommended story points to commit (0 if no history)
        """
        avg_velocity = self.get_average_velocity(last_n_sprints)
        return int(avg_velocity * buffer_percentage)
