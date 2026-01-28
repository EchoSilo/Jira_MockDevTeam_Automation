"""Sprint Scenario Models.

Defines the data structures for sprint-level scenarios that orchestrate
the simulation toward predetermined outcomes.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
import uuid
import pendulum

from pydantic import BaseModel, Field


class ScenarioArchetype(str, Enum):
    """Sprint scenario archetypes - predefined narrative patterns."""

    SMOOTH_SPRINT = "smooth_sprint"
    OVERLOADED_SPRINT = "overloaded_sprint"
    BLOCKER_HEAVY = "blocker_heavy"
    REWORK_SPRINT = "rework_sprint"
    CRUNCH_SPRINT = "crunch_sprint"
    RECOVERY_SPRINT = "recovery_sprint"


class EventType(str, Enum):
    """Types of events that can occur in a sprint script."""

    # Planning
    SPRINT_PLANNING = "sprint_planning"

    # Progress events
    DEV_PICKUP = "dev_pickup"
    DEV_PROGRESS = "dev_progress"
    PUSH_TO_REVIEW = "push_to_review"
    REVIEW_COMPLETE = "review_complete"
    PUSH_TO_QA = "push_to_qa"
    QA_APPROVE = "qa_approve"

    # Disruption events
    BLOCKER = "blocker"
    BLOCKER_DISCUSSION = "blocker_discussion"
    BLOCKER_RESOLVED = "blocker_resolved"
    QA_REJECTION = "qa_rejection"
    REWORK_IN_PROGRESS = "rework_in_progress"
    REWORK_COMPLETE = "rework_complete"
    SCOPE_CREEP = "scope_creep"
    CONTEXT_SWITCH = "context_switch"

    # Communication events
    ESCALATION_COMMENT = "escalation_comment"
    PM_PRESSURE_COMMENT = "pm_pressure_comment"
    RUSH_COMMENT = "rush_comment"
    OVERTIME_COMMENT = "overtime_comment"
    URGENCY_COMMENT = "urgency_comment"
    RELEASE_PREP_COMMENT = "release_prep_comment"
    FINAL_PUSH_COMMENT = "final_push_comment"
    DEV_FRUSTRATION_COMMENT = "dev_frustration_comment"
    RETRO_COMMENT = "retro_comment"
    PROCESS_IMPROVEMENT_COMMENT = "process_improvement_comment"
    TEAM_HEALTH_IMPROVED_COMMENT = "team_health_improved_comment"
    WORKAROUND_ATTEMPTED = "workaround_attempted"
    CATCH_UP_PROGRESS = "catch_up_progress"
    TECH_DEBT_WORK = "tech_debt_work"

    # Sprint lifecycle
    CARRYOVER = "carryover"
    RELEASE_READY = "release_ready"
    SPRINT_COMPLETE = "sprint_complete"


class MoodState(str, Enum):
    """Team mood states that influence comment tone."""

    ENERGIZED = "energized"
    OPTIMISTIC = "optimistic"
    AMBITIOUS = "ambitious"
    CONFIDENT = "confident"
    INTENSE = "intense"
    FOCUSED = "focused"
    STEADY = "steady"
    REFLECTIVE = "reflective"
    STRESSED = "stressed"
    FRUSTRATED = "frustrated"
    DEFLATED = "deflated"
    EXHAUSTED = "exhausted"
    EXHAUSTED_BUT_PUSHING = "exhausted_but_pushing"
    RELIEVED = "relieved"
    DETERMINED = "determined"
    CAUTIOUS = "cautious"
    SATISFIED = "satisfied"
    ACCOMPLISHED = "accomplished"
    HEALTHY = "healthy"


class ScriptEvent(BaseModel):
    """A single event in the sprint script."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    event_type: EventType
    day: int  # Which day this event should occur (1-7 for a 7-day sprint)

    # Target specification
    ticket_key: Optional[str] = None  # Specific ticket for this event
    ticket_keys: list[str] = Field(default_factory=list)  # Multiple tickets
    agent_id: Optional[str] = None  # Specific agent to perform action
    agent_type: Optional[str] = None  # Type of agent (developer, qa, etc.)

    # Event parameters
    count: int = 1  # How many items/actions
    coverage: Optional[float] = None  # Percentage coverage (e.g., 0.6 = 60%)
    percentage: Optional[float] = None  # For carryover percentage
    blocker_type: Optional[str] = None  # technical, dependency, etc.
    severity: Optional[str] = None  # low, medium, high
    rejection_reasons: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)

    # Execution tracking
    executed: bool = False
    executed_at: Optional[datetime] = None
    execution_result: Optional[dict[str, Any]] = None

    def mark_executed(self, result: Optional[dict[str, Any]] = None) -> None:
        """Mark this event as executed."""
        self.executed = True
        self.executed_at = pendulum.now("UTC")
        self.execution_result = result or {}


class ScriptDay(BaseModel):
    """A day in the sprint script with its events."""

    day: int  # 1-7 for a 7-day sprint
    events: list[ScriptEvent] = Field(default_factory=list)
    mood: Optional[MoodState] = None
    notes: Optional[str] = None

    def get_pending_events(self) -> list[ScriptEvent]:
        """Get events that haven't been executed yet."""
        return [e for e in self.events if not e.executed]

    def get_executed_events(self) -> list[ScriptEvent]:
        """Get events that have been executed."""
        return [e for e in self.events if e.executed]

    def all_events_executed(self) -> bool:
        """Check if all events for this day have been executed."""
        return all(e.executed for e in self.events)


class SprintScenario(BaseModel):
    """A sprint-level scenario that orchestrates the simulation.

    This replaces the old per-ticket ActiveScenario model with a
    sprint-level narrative that defines how the entire sprint unfolds.
    """

    # Identity
    scenario_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    sprint_id: int
    sprint_name: str

    # Archetype
    archetype: ScenarioArchetype
    archetype_name: str = ""  # Human-readable name

    # Targets
    target_completion_rate: float  # 0.0 - 1.0
    target_velocity: Optional[int] = None  # Story points target

    # Context
    release_context: Optional[str] = None  # "Final sprint before v1.2.0"
    team_notes: Optional[str] = None  # "Dev Alice on PTO days 3-5"
    previous_sprint_completion: Optional[float] = None

    # The Script
    script: list[ScriptDay] = Field(default_factory=list)

    # Sprint items (tickets in this sprint)
    sprint_items: list[str] = Field(default_factory=list)  # Ticket keys
    item_assignments: dict[str, str] = Field(default_factory=dict)  # ticket -> agent

    # Progress tracking
    current_day: int = 0
    events_executed: list[str] = Field(default_factory=list)  # Event IDs
    items_completed: list[str] = Field(default_factory=list)  # Ticket keys
    items_carried_over: list[str] = Field(default_factory=list)  # Ticket keys
    actual_completion_rate: float = 0.0

    # Current mood
    current_mood: Optional[MoodState] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def start(self) -> None:
        """Start the scenario."""
        self.started_at = pendulum.now("UTC")
        self.current_day = 1
        # Set initial mood from day 1 if available
        day_1 = self.get_day(1)
        if day_1 and day_1.mood:
            self.current_mood = day_1.mood

    def complete(self) -> None:
        """Complete the scenario."""
        self.completed_at = pendulum.now("UTC")
        # Calculate actual completion rate
        if self.sprint_items:
            self.actual_completion_rate = len(self.items_completed) / len(self.sprint_items)

    def advance_day(self) -> bool:
        """Advance to the next day. Returns False if sprint is complete."""
        max_day = max(d.day for d in self.script) if self.script else 7
        if self.current_day >= max_day:
            return False

        self.current_day += 1

        # Update mood if defined for new day
        current_day_script = self.get_day(self.current_day)
        if current_day_script and current_day_script.mood:
            self.current_mood = current_day_script.mood

        return True

    def get_day(self, day: int) -> Optional[ScriptDay]:
        """Get the script for a specific day."""
        for script_day in self.script:
            if script_day.day == day:
                return script_day
        return None

    def get_current_day_script(self) -> Optional[ScriptDay]:
        """Get the script for the current day."""
        return self.get_day(self.current_day)

    def get_pending_events_for_today(self) -> list[ScriptEvent]:
        """Get events for current day that haven't been executed."""
        day_script = self.get_current_day_script()
        if day_script:
            return day_script.get_pending_events()
        return []

    def get_all_pending_events(self) -> list[ScriptEvent]:
        """Get all pending events up to and including current day."""
        pending = []
        for script_day in self.script:
            if script_day.day <= self.current_day:
                pending.extend(script_day.get_pending_events())
        return pending

    def mark_event_executed(
        self, event_id: str, result: Optional[dict[str, Any]] = None
    ) -> bool:
        """Mark an event as executed. Returns True if found."""
        for script_day in self.script:
            for event in script_day.events:
                if event.event_id == event_id:
                    event.mark_executed(result)
                    self.events_executed.append(event_id)
                    return True
        return False

    def mark_item_completed(self, ticket_key: str) -> None:
        """Mark a sprint item as completed."""
        if ticket_key in self.sprint_items and ticket_key not in self.items_completed:
            self.items_completed.append(ticket_key)
            self.actual_completion_rate = len(self.items_completed) / len(self.sprint_items)

    def mark_item_carried_over(self, ticket_key: str) -> None:
        """Mark a sprint item as carried over to next sprint."""
        if ticket_key in self.sprint_items and ticket_key not in self.items_carried_over:
            self.items_carried_over.append(ticket_key)

    def is_on_track(self) -> bool:
        """Check if sprint is on track to meet target completion rate."""
        if not self.sprint_items or self.current_day == 0:
            return True

        # Calculate expected progress
        sprint_duration = max(d.day for d in self.script) if self.script else 7
        expected_rate = (self.current_day / sprint_duration) * self.target_completion_rate
        return self.actual_completion_rate >= expected_rate * 0.8  # 80% of expected

    def get_progress_summary(self) -> dict[str, Any]:
        """Get a summary of scenario progress."""
        total_events = sum(len(d.events) for d in self.script)
        executed_events = len(self.events_executed)

        return {
            "scenario_id": self.scenario_id,
            "sprint_id": self.sprint_id,
            "sprint_name": self.sprint_name,
            "archetype": self.archetype.value,
            "archetype_name": self.archetype_name,
            "current_day": self.current_day,
            "total_days": max(d.day for d in self.script) if self.script else 7,
            "current_mood": self.current_mood.value if self.current_mood else None,
            "target_completion_rate": self.target_completion_rate,
            "actual_completion_rate": self.actual_completion_rate,
            "is_on_track": self.is_on_track(),
            "total_items": len(self.sprint_items),
            "items_completed": len(self.items_completed),
            "items_carried_over": len(self.items_carried_over),
            "total_events": total_events,
            "events_executed": executed_events,
            "events_remaining": total_events - executed_events,
            "release_context": self.release_context,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def create(
        cls,
        sprint_id: int,
        sprint_name: str,
        archetype: ScenarioArchetype,
        script: list[ScriptDay],
        sprint_items: list[str],
        target_completion_rate: float,
        release_context: Optional[str] = None,
        previous_sprint_completion: Optional[float] = None,
    ) -> "SprintScenario":
        """Factory method to create a new sprint scenario."""
        archetype_names = {
            ScenarioArchetype.SMOOTH_SPRINT: "Smooth Sprint",
            ScenarioArchetype.OVERLOADED_SPRINT: "Overloaded Sprint",
            ScenarioArchetype.BLOCKER_HEAVY: "Blocker-Heavy Sprint",
            ScenarioArchetype.REWORK_SPRINT: "Rework Sprint",
            ScenarioArchetype.CRUNCH_SPRINT: "Crunch Sprint",
            ScenarioArchetype.RECOVERY_SPRINT: "Recovery Sprint",
        }

        return cls(
            sprint_id=sprint_id,
            sprint_name=sprint_name,
            archetype=archetype,
            archetype_name=archetype_names.get(archetype, archetype.value),
            script=script,
            sprint_items=sprint_items,
            target_completion_rate=target_completion_rate,
            release_context=release_context,
            previous_sprint_completion=previous_sprint_completion,
        )
