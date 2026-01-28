"""Planning module for sprint planning and velocity tracking."""

from .models import SprintPlan, PlanningHorizon, SprintPlanStatus
from .velocity_tracker import VelocityTracker, SprintVelocityRecord
from .capacity_planner import CapacityPlanner
from .scenario_scheduler import ScenarioScheduler

# BacklogPrioritizer has missing dependency (litellm) - import conditionally
try:
    from .backlog_prioritizer import BacklogPrioritizer
    _has_backlog = True
except ImportError:
    _has_backlog = False

__all__ = [
    "SprintPlan",
    "PlanningHorizon",
    "SprintPlanStatus",
    "VelocityTracker",
    "SprintVelocityRecord",
    "CapacityPlanner",
    "ScenarioScheduler",
]

if _has_backlog:
    __all__.append("BacklogPrioritizer")
