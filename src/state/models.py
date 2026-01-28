"""
Enhanced state models for scenario-driven simulation.
Tracks tickets as scenarios with lifecycle phases and target timelines.

NOTE: The old per-ticket ActiveScenario model is deprecated.
Sprint-level scenarios are now managed via SprintScenario in src/scenarios/.
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional, TYPE_CHECKING
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, PrivateAttr
import uuid
import pendulum

if TYPE_CHECKING:
    from src.scenarios import SprintScenario


class ScenarioType(str, Enum):
    """Types of scenarios that can unfold on a ticket."""
    NORMAL_FLOW = "normal_flow"      # Standard Dev → Review → QA → Done
    BLOCKER = "blocker"              # Ticket gets blocked, then unblocked
    REWORK = "rework"                # QA rejects, dev fixes, re-test
    SCOPE_CREEP = "scope_creep"      # Mid-sprint story addition
    DEPENDENCY = "dependency"        # Cross-team dependency wait


class ScenarioPhase(str, Enum):
    """Phases a scenario can be in."""
    # Normal flow phases
    CREATED = "created"
    BACKLOG = "backlog"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    IN_TESTING = "in_testing"
    COMPLETED = "completed"

    # Blocker phases
    BLOCKED = "blocked"
    BLOCKER_DISCUSSED = "blocker_discussed"
    UNBLOCKING = "unblocking"

    # Rework phases
    REJECTED = "rejected"
    FIXING = "fixing"
    RE_REVIEW = "re_review"
    RE_TESTING = "re_testing"

    # Dependency phases
    WAITING_ON_DEPENDENCY = "waiting_on_dependency"
    DEPENDENCY_RESOLVED = "dependency_resolved"


class TicketComplexity(str, Enum):
    """Complexity levels that determine cycle time targets."""
    BUG = "bug"           # 1-3 days
    STORY = "story"       # 3-7 days
    FEATURE = "feature"   # 7-14 days


# Mapping from Jira issue types to complexity
ISSUE_TYPE_TO_COMPLEXITY = {
    "Bug": TicketComplexity.BUG,
    "Task": TicketComplexity.STORY,
    "Story": TicketComplexity.STORY,
    "Epic": TicketComplexity.FEATURE,
    "Feature": TicketComplexity.FEATURE,
}

# Cycle time ranges in days
CYCLE_TIME_RANGES = {
    TicketComplexity.BUG: (1, 3),
    TicketComplexity.STORY: (3, 7),
    TicketComplexity.FEATURE: (7, 14),
}

# Phase duration as fraction of total cycle time
PHASE_DURATION_FRACTIONS = {
    ScenarioPhase.ASSIGNED: 0.05,
    ScenarioPhase.IN_PROGRESS: 0.50,
    ScenarioPhase.IN_REVIEW: 0.15,
    ScenarioPhase.IN_TESTING: 0.20,
    ScenarioPhase.COMPLETED: 0.10,
    # Blocker adds extra time
    ScenarioPhase.BLOCKED: 0.30,
    ScenarioPhase.BLOCKER_DISCUSSED: 0.15,
    # Rework adds extra time
    ScenarioPhase.REJECTED: 0.05,
    ScenarioPhase.FIXING: 0.25,
    ScenarioPhase.RE_REVIEW: 0.10,
    ScenarioPhase.RE_TESTING: 0.15,
}

# Minimum hours required in each phase before advancement
PHASE_MINIMUM_HOURS = {
    ScenarioPhase.IN_PROGRESS: 24,      # 1 day minimum
    ScenarioPhase.IN_REVIEW: 4,         # 4 hours minimum
    ScenarioPhase.IN_TESTING: 4,        # 4 hours minimum
    ScenarioPhase.BLOCKED: 8,           # Half day minimum
    ScenarioPhase.FIXING: 8,            # Half day for rework
    ScenarioPhase.RE_REVIEW: 2,         # Quick re-review
    ScenarioPhase.RE_TESTING: 2,        # Quick re-test
}

# Maximum hours allowed in certain phases (prevents stale items)
PHASE_MAXIMUM_HOURS = {
    ScenarioPhase.IN_REVIEW: 24,        # 1 day max (unless rejected)
    ScenarioPhase.ASSIGNED: 8,          # Should be picked up quickly
}


# ========== Release Management Models ==========

class ReleaseVersion(BaseModel):
    """A planned release version managed by the Release Manager."""
    name: str                          # e.g., "v1.2.0"
    target_date: datetime
    status: str = "planned"            # planned | in_progress | released
    created_in_jira: bool = False
    assigned_tickets: list[str] = Field(default_factory=list)
    release_notes: Optional[str] = None
    sprint_number: Optional[int] = None  # Associated sprint


class ReleaseDirective(BaseModel):
    """An instruction from Release Manager to a PM agent."""
    directive_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    directive_type: str                # create_version | assign_version | release_reminder
    target_pm_id: str
    parameters: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: pendulum.now("UTC"))
    executed: bool = False
    execution_result: Optional[str] = None


class ReleaseState(BaseModel):
    """Release planning state managed by the Release Manager agent."""
    planned_releases: list[ReleaseVersion] = Field(default_factory=list)
    active_directives: list[ReleaseDirective] = Field(default_factory=list)
    compliance_metrics: dict = Field(default_factory=dict)
    last_compliance_check: Optional[datetime] = None

    def get_current_release(self) -> Optional[ReleaseVersion]:
        """Get the next planned release (not yet released)."""
        for release in self.planned_releases:
            if release.status != "released":
                return release
        return None

    def get_release_by_name(self, name: str) -> Optional[ReleaseVersion]:
        """Find a release by version name."""
        for release in self.planned_releases:
            if release.name == name:
                return release
        return None

    def add_release(self, release: ReleaseVersion) -> None:
        """Add a new planned release."""
        self.planned_releases.append(release)

    def mark_directive_executed(self, directive_id: str, result: Optional[str] = None) -> None:
        """Mark a directive as executed."""
        for directive in self.active_directives:
            if directive.directive_id == directive_id:
                directive.executed = True
                directive.execution_result = result
                break

    def get_pending_directives(self, pm_id: Optional[str] = None) -> list[ReleaseDirective]:
        """Get unexecuted directives, optionally filtered by PM."""
        directives = [d for d in self.active_directives if not d.executed]
        if pm_id:
            directives = [d for d in directives if d.target_pm_id == pm_id]
        return directives

    def cleanup_old_directives(self, max_age_hours: int = 48) -> int:
        """Remove executed directives older than max_age_hours."""
        cutoff = pendulum.now("UTC") - timedelta(hours=max_age_hours)
        original_count = len(self.active_directives)
        self.active_directives = [
            d for d in self.active_directives
            if not d.executed or d.created_at > cutoff
        ]
        return original_count - len(self.active_directives)

    def cleanup_duplicate_directives(self) -> int:
        """Remove duplicate pending directives, keeping only the first of each type/version combo."""
        seen = set()
        cleaned = []
        for directive in self.active_directives:
            # Keep executed directives as-is
            if directive.executed:
                cleaned.append(directive)
                continue
            # Create dedup key based on type and key parameters
            key = (
                directive.directive_type,
                directive.parameters.get("version_name"),
                directive.parameters.get("ticket_key"),
            )
            if key not in seen:
                seen.add(key)
                cleaned.append(directive)
        removed = len(self.active_directives) - len(cleaned)
        self.active_directives = cleaned
        return removed


class ActionRecord(BaseModel):
    """Record of an action taken within a scenario."""
    action_type: str
    agent_id: str
    timestamp: datetime = Field(default_factory=lambda: pendulum.now("UTC"))
    details: Optional[str] = None


class PlannedAction(BaseModel):
    """A single action in a scenario script (pre-planned journey)."""
    type: str
    target_status: Optional[str] = None
    role: Optional[str] = None
    optional: bool = False
    executed: bool = False
    context: Optional[str] = None  # Additional context (e.g., "scope_discussion")


class ActiveScenario(BaseModel):
    """A scenario in progress on a specific ticket."""
    scenario_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    ticket_key: str
    scenario_type: ScenarioType
    complexity: TicketComplexity

    # Timeline
    started: datetime = Field(default_factory=lambda: pendulum.now("UTC"))
    target_completion: datetime
    current_phase: ScenarioPhase
    phase_started: datetime = Field(default_factory=lambda: pendulum.now("UTC"))
    phase_target_end: datetime

    # Assignment
    assigned_agent: Optional[str] = None  # Primary developer
    qa_agent: Optional[str] = None  # QA tester assigned during testing phase
    involved_agents: list[str] = Field(default_factory=list)

    # Context for special scenarios
    blocker_reason: Optional[str] = None
    rejection_reason: Optional[str] = None
    dependency_ticket: Optional[str] = None
    dependency_team: Optional[str] = None

    # Release management
    fix_version: Optional[str] = None  # Target release version for this scenario

    # Tracking
    actions_taken: list[ActionRecord] = Field(default_factory=list)
    comments_added: int = 0
    times_rejected: int = 0

    # Pre-planned action script (sequence only, no timing)
    action_script: list[PlannedAction] = Field(default_factory=list)
    script_index: int = 0  # Current position in script

    @classmethod
    def create_normal_flow(
        cls,
        ticket_key: str,
        complexity: TicketComplexity,
        assigned_agent: Optional[str] = None,
        cycle_days: Optional[int] = None,
    ) -> "ActiveScenario":
        """Factory for creating a normal flow scenario."""
        if cycle_days is None:
            min_days, max_days = CYCLE_TIME_RANGES[complexity]
            import random
            cycle_days = random.randint(min_days, max_days)

        now = pendulum.now("UTC")
        target_completion = now + timedelta(days=cycle_days)

        # Initial phase duration
        phase_fraction = PHASE_DURATION_FRACTIONS.get(ScenarioPhase.ASSIGNED, 0.05)
        phase_duration = timedelta(days=cycle_days * phase_fraction)

        return cls(
            ticket_key=ticket_key,
            scenario_type=ScenarioType.NORMAL_FLOW,
            complexity=complexity,
            started=now,
            target_completion=target_completion,
            current_phase=ScenarioPhase.ASSIGNED,
            phase_started=now,
            phase_target_end=now + phase_duration,
            assigned_agent=assigned_agent,
            involved_agents=[assigned_agent] if assigned_agent else [],
        )

    def advance_to_phase(self, new_phase: ScenarioPhase) -> None:
        """Advance scenario to a new phase."""
        now = pendulum.now("UTC")

        # Record the phase transition
        self.actions_taken.append(ActionRecord(
            action_type=f"phase_transition_to_{new_phase.value}",
            agent_id=self.assigned_agent or "system",
            timestamp=now,
        ))

        self.current_phase = new_phase
        self.phase_started = now

        # Calculate new phase target
        remaining_time = self.target_completion - now
        phase_fraction = PHASE_DURATION_FRACTIONS.get(new_phase, 0.10)
        phase_duration = timedelta(seconds=remaining_time.total_seconds() * phase_fraction)

        # Minimum 4 hours in any phase
        min_phase_duration = timedelta(hours=4)
        phase_duration = max(phase_duration, min_phase_duration)

        self.phase_target_end = now + phase_duration

    def assign_qa(self, qa_agent_id: str) -> None:
        """Assign a QA agent to test this ticket."""
        self.qa_agent = qa_agent_id
        if qa_agent_id not in self.involved_agents:
            self.involved_agents.append(qa_agent_id)

    def unassign_qa(self) -> None:
        """Remove QA assignment (when testing is complete)."""
        self.qa_agent = None

    def inject_blocker(self, reason: str, agent_id: str) -> None:
        """Convert to blocker scenario."""
        self.scenario_type = ScenarioType.BLOCKER
        self.blocker_reason = reason
        self.advance_to_phase(ScenarioPhase.BLOCKED)

        # Extend target completion for blocker time
        blocker_extension = timedelta(days=2)  # 1-3 days typical
        self.target_completion += blocker_extension

        self.actions_taken.append(ActionRecord(
            action_type="blocker_injected",
            agent_id=agent_id,
            details=reason,
        ))

    def inject_rejection(self, reason: str, agent_id: str) -> None:
        """Convert to rework scenario after QA rejection."""
        self.scenario_type = ScenarioType.REWORK
        self.rejection_reason = reason
        self.times_rejected += 1
        self.advance_to_phase(ScenarioPhase.REJECTED)

        # Extend target completion for rework time
        rework_extension = timedelta(days=1.5)
        self.target_completion += rework_extension

        self.actions_taken.append(ActionRecord(
            action_type="qa_rejected",
            agent_id=agent_id,
            details=reason,
        ))

        if agent_id not in self.involved_agents:
            self.involved_agents.append(agent_id)

    def inject_dependency(
        self,
        dependency_ticket: str,
        dependency_team: str,
        agent_id: str,
    ) -> None:
        """Convert to dependency scenario."""
        self.scenario_type = ScenarioType.DEPENDENCY
        self.dependency_ticket = dependency_ticket
        self.dependency_team = dependency_team
        self.advance_to_phase(ScenarioPhase.WAITING_ON_DEPENDENCY)

        # Extend target completion for dependency wait
        dependency_extension = timedelta(days=3)
        self.target_completion += dependency_extension

        self.actions_taken.append(ActionRecord(
            action_type="dependency_identified",
            agent_id=agent_id,
            details=f"Waiting on {dependency_ticket} from {dependency_team}",
        ))

    def record_action(self, action_type: str, agent_id: str, details: Optional[str] = None) -> None:
        """Record an action taken on this scenario."""
        self.actions_taken.append(ActionRecord(
            action_type=action_type,
            agent_id=agent_id,
            details=details,
        ))
        if agent_id and agent_id not in self.involved_agents:
            self.involved_agents.append(agent_id)

    def is_phase_ready_to_advance(self) -> bool:
        """Check if current phase has exceeded its target duration and minimum time."""
        now = pendulum.now("UTC")
        time_in_phase = now - self.phase_started

        # Check minimum hours requirement for current phase
        min_hours = PHASE_MINIMUM_HOURS.get(self.current_phase, 4)  # Default 4 hours
        if time_in_phase < timedelta(hours=min_hours):
            return False

        # Check if target time has been reached
        return now >= self.phase_target_end

    def is_overdue(self) -> bool:
        """Check if scenario has exceeded target completion."""
        return pendulum.now("UTC") > self.target_completion

    def get_days_in_current_phase(self) -> float:
        """Get number of days in current phase."""
        delta = pendulum.now("UTC") - self.phase_started
        return delta.total_seconds() / 86400

    def get_total_cycle_days(self) -> float:
        """Get total days since scenario started."""
        delta = pendulum.now("UTC") - self.started
        return delta.total_seconds() / 86400

    # ========== Script Management ==========

    def get_next_script_action(self) -> Optional[PlannedAction]:
        """Get next unexecuted action from script."""
        for i, action in enumerate(self.action_script[self.script_index:], self.script_index):
            if not action.executed:
                return action
        return None

    def get_script_progress(self) -> tuple[int, int]:
        """Get (current_index, total_actions) for progress tracking."""
        executed = sum(1 for a in self.action_script if a.executed)
        return (executed, len(self.action_script))

    def advance_script(self) -> None:
        """Mark current script action as executed and advance index."""
        if self.script_index < len(self.action_script):
            self.action_script[self.script_index].executed = True
            self.script_index += 1

    def is_script_complete(self) -> bool:
        """Check if all script actions have been executed."""
        return all(a.executed for a in self.action_script)

    def inject_disruption(self, disruption_actions: list[dict]) -> None:
        """
        Inject disruption actions (blocker/rework) at current position.

        The disruption actions are inserted AFTER the current position,
        so the next action will be the first disruption action.
        """
        # Convert dicts to PlannedAction if needed
        new_actions = []
        for action in disruption_actions:
            if isinstance(action, dict):
                new_actions.append(PlannedAction(**action))
            else:
                new_actions.append(action)

        # Insert disruption actions after current position
        insert_pos = self.script_index + 1
        self.action_script = (
            self.action_script[:insert_pos]
            + new_actions
            + self.action_script[insert_pos:]
        )

    def replace_remaining_script(self, new_actions: list[dict]) -> None:
        """
        Replace remaining (unexecuted) script actions with new actions.

        Used when Jira state diverges and pathfinder recalculates.
        """
        # Keep executed actions, replace the rest
        executed = [a for a in self.action_script if a.executed]

        # Convert dicts to PlannedAction
        new_planned = []
        for action in new_actions:
            if isinstance(action, dict):
                new_planned.append(PlannedAction(**action))
            else:
                new_planned.append(action)

        self.action_script = executed + new_planned
        self.script_index = len(executed)

    def set_script(self, actions: list[dict]) -> None:
        """Set the action script (used at scenario creation)."""
        self.action_script = [
            PlannedAction(**a) if isinstance(a, dict) else a
            for a in actions
        ]
        self.script_index = 0


class AgentState(BaseModel):
    """State tracking for a single agent."""
    agent_id: str
    last_action: Optional[datetime] = None
    actions_today: int = 0
    assigned_tickets: list[str] = Field(default_factory=list)
    review_tickets: list[str] = Field(default_factory=list)  # Tickets being reviewed (for Tech Lead)

    # Calculated metrics
    current_workload: int = 0

    # Behavioral flags
    is_overloaded: bool = False  # 5+ tickets triggers slower progress

    # Performance tracking (for seniority-based rejection rates)
    recent_rejections: int = 0
    recent_completions: int = 0

    # Sprint-level assignment tracking for workload fairness
    sprint_assignments: int = 0  # Tickets assigned this sprint
    last_sprint_reset: int = 0   # Sprint number when counters were last reset

    def record_action(self, ticket_key: Optional[str] = None) -> None:
        """Record that agent took an action."""
        self.last_action = pendulum.now("UTC")
        self.actions_today += 1

    def _update_workload(self) -> None:
        """Update workload from assigned + review tickets."""
        self.current_workload = len(self.assigned_tickets) + len(self.review_tickets)
        self.is_overloaded = self.current_workload >= 5

    def assign_ticket(self, ticket_key: str) -> None:
        """Assign a ticket to this agent."""
        if ticket_key not in self.assigned_tickets:
            self.assigned_tickets.append(ticket_key)
            self.sprint_assignments += 1  # Track sprint-level assignments
        self._update_workload()

    def unassign_ticket(self, ticket_key: str) -> None:
        """Remove a ticket from this agent."""
        if ticket_key in self.assigned_tickets:
            self.assigned_tickets.remove(ticket_key)
        self._update_workload()

    def assign_review(self, ticket_key: str) -> None:
        """Assign a ticket for code review to this agent (Tech Lead)."""
        if ticket_key not in self.review_tickets:
            self.review_tickets.append(ticket_key)
        self._update_workload()

    def unassign_review(self, ticket_key: str) -> None:
        """Remove a review assignment from this agent."""
        if ticket_key in self.review_tickets:
            self.review_tickets.remove(ticket_key)
        self._update_workload()

    def record_rejection(self) -> None:
        """Record that agent's work was rejected."""
        self.recent_rejections += 1

    def record_completion(self) -> None:
        """Record that agent completed work successfully."""
        self.recent_completions += 1

    def get_rejection_rate(self) -> float:
        """Calculate recent rejection rate."""
        total = self.recent_rejections + self.recent_completions
        if total == 0:
            return 0.0
        return self.recent_rejections / total

    def reset_daily_counters(self) -> None:
        """Reset counters at start of new day."""
        self.actions_today = 0

    def reset_sprint_counters(self, sprint_number: int) -> None:
        """Reset sprint counters at start of new sprint."""
        if sprint_number != self.last_sprint_reset:
            self.sprint_assignments = 0
            self.last_sprint_reset = sprint_number


class RecentAction(BaseModel):
    """Record of a recent action for avoiding repetition."""
    agent_id: str
    agent_name: str
    action_type: str
    ticket_key: Optional[str] = None
    scenario_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: pendulum.now("UTC"))
    details: Optional[str] = None


class SprintState(BaseModel):
    """Sprint tracking - derives sprint_number/day from Jira (source of truth).

    The sprint_number and sprint_day are computed from Jira's active sprint data,
    not stored as independent counters. This prevents drift between local state
    and Jira's actual sprint.

    Raw Jira data is stored for offline fallback when Jira is unavailable.
    """

    # Configuration (stored in state.json)
    total_days: int = 14  # Sprint length (2 weeks: Monday to Sunday)

    # Raw Jira data (stored for offline fallback)
    jira_sprint_name: Optional[str] = None  # e.g., "ESCRUM Sprint 7"
    jira_start_date: Optional[str] = None   # ISO format from Jira
    jira_end_date: Optional[str] = None     # ISO format from Jira

    # Cached derived values (NOT serialized - computed at tick start)
    _sprint_number: Optional[int] = PrivateAttr(default=None)
    _sprint_day: Optional[int] = PrivateAttr(default=None)
    _initialized: bool = PrivateAttr(default=False)

    @classmethod
    def model_validate(cls, obj, **kwargs):
        """Handle migration from old format with sprint_number/sprint_day fields."""
        if isinstance(obj, dict):
            # Migrate from legacy "name" field
            if "name" in obj and "jira_sprint_name" not in obj:
                obj["jira_sprint_name"] = obj["name"]

            # Migrate from old sprint_number/sprint_day format
            if "sprint_number" in obj and "jira_sprint_name" not in obj:
                obj["jira_sprint_name"] = f"Sprint {obj.get('sprint_number', 1)}"

            # Migrate start_date to jira_start_date
            if "start_date" in obj and "jira_start_date" not in obj:
                start_date = obj["start_date"]
                if isinstance(start_date, str):
                    obj["jira_start_date"] = start_date
                elif hasattr(start_date, 'isoformat'):
                    obj["jira_start_date"] = start_date.isoformat()

            # Remove old fields that are no longer stored
            obj.pop("sprint_number", None)
            obj.pop("sprint_day", None)
            obj.pop("day", None)  # Old alias
            obj.pop("start_date", None)
            obj.pop("name", None)

        return super().model_validate(obj, **kwargs)

    def inject_jira_sprint(self, jira_sprint: Optional[dict], current_time: Optional[datetime] = None) -> None:
        """Inject Jira sprint data and compute derived values.

        Call this at the start of each tick with the active sprint from Jira.
        If jira_sprint is None (no active sprint or Jira unavailable),
        uses cached data from previous run as fallback.
        """
        if jira_sprint:
            self.jira_sprint_name = jira_sprint.get("name")
            self.jira_start_date = jira_sprint.get("start_date")
            self.jira_end_date = jira_sprint.get("end_date")
        # Compute derived values (uses cached data if jira_sprint was None)
        self._compute_derived_values(current_time)
        self._initialized = True

    def _compute_derived_values(self, current_time: Optional[datetime] = None) -> None:
        """Compute sprint_number and sprint_day from Jira data."""
        # Parse sprint number from name (e.g., "ESCRUM Sprint 7" -> 7)
        if self.jira_sprint_name:
            try:
                self._sprint_number = int(self.jira_sprint_name.split()[-1])
            except (ValueError, IndexError):
                self._sprint_number = 1
        else:
            self._sprint_number = 1

        # Calculate sprint day from start date
        if self.jira_start_date:
            try:
                from datetime import timezone
                # Parse start date (handle various formats)
                start_str = self.jira_start_date
                if "T" in start_str:
                    start_date = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                else:
                    start_date = datetime.fromisoformat(start_str)

                # Calculate days since sprint started (1-indexed)
                if current_time:
                    now = current_time
                else:
                    now = pendulum.now("UTC")

                if start_date.tzinfo is None:
                    start_date = start_date.replace(tzinfo=timezone.utc)

                # Ensure now is timezone aware if start_date is
                if now.tzinfo is None and start_date.tzinfo:
                    now = now.replace(tzinfo=timezone.utc)

                days_elapsed = (now.date() - start_date.date()).days + 1  # +1 for 1-indexed
                # Clamp to valid range [1, total_days]
                self._sprint_day = max(1, min(days_elapsed, self.total_days))
            except Exception:
                self._sprint_day = 1
        else:
            self._sprint_day = 1

    @property
    def sprint_number(self) -> int:
        """Get sprint number (derived from Jira sprint name)."""
        if not self._initialized:
            self._compute_derived_values()
            self._initialized = True
        return self._sprint_number or 1

    @property
    def sprint_day(self) -> int:
        """Get sprint day (derived from Jira start_date)."""
        if not self._initialized:
            self._compute_derived_values()
            self._initialized = True
        return self._sprint_day or 1

    def is_mid_sprint(self) -> bool:
        """Check if we're in the middle of the sprint (days 4-11 for 14-day sprint)."""
        # Middle portion is roughly 25%-75% of sprint
        quarter = self.total_days // 4
        return quarter < self.sprint_day <= (self.total_days - quarter)

    def is_sprint_end(self) -> bool:
        """Check if we're near sprint end (last 3 days for 14-day sprint)."""
        end_days = max(2, self.total_days // 5)  # ~3 days for 14-day sprint
        return self.sprint_day > self.total_days - end_days

    def is_sprint_planning_day(self) -> bool:
        """Check if it's sprint planning day (day 1 = Monday)."""
        return self.sprint_day == 1

    def is_sprint_start(self) -> bool:
        """Check if we're at the start of the sprint (first 3 days for 14-day sprint)."""
        start_days = max(2, self.total_days // 5)  # ~3 days for 14-day sprint
        return self.sprint_day <= start_days

    def is_sprint_complete_day(self) -> bool:
        """Check if it's sprint completion day (last day = Sunday)."""
        return self.sprint_day == self.total_days


class ScenarioDistribution(BaseModel):
    """Track distribution of scenario types for balance."""
    normal_flow: int = 0
    blocker: int = 0
    rework: int = 0
    scope_creep: int = 0
    dependency: int = 0

    def increment(self, scenario_type: ScenarioType) -> None:
        """Increment count for a scenario type."""
        if scenario_type == ScenarioType.NORMAL_FLOW:
            self.normal_flow += 1
        elif scenario_type == ScenarioType.BLOCKER:
            self.blocker += 1
        elif scenario_type == ScenarioType.REWORK:
            self.rework += 1
        elif scenario_type == ScenarioType.SCOPE_CREEP:
            self.scope_creep += 1
        elif scenario_type == ScenarioType.DEPENDENCY:
            self.dependency += 1

    def get_total(self) -> int:
        """Get total scenarios."""
        return self.normal_flow + self.blocker + self.rework + self.scope_creep + self.dependency

    def get_percentages(self) -> dict[str, float]:
        """Get percentage distribution."""
        total = self.get_total()
        if total == 0:
            return {t.value: 0.0 for t in ScenarioType}
        return {
            ScenarioType.NORMAL_FLOW.value: self.normal_flow / total,
            ScenarioType.BLOCKER.value: self.blocker / total,
            ScenarioType.REWORK.value: self.rework / total,
            ScenarioType.SCOPE_CREEP.value: self.scope_creep / total,
            ScenarioType.DEPENDENCY.value: self.dependency / total,
        }


class SimulationState(BaseModel):
    """Complete simulation state with scenario tracking."""
    model_config = ConfigDict(extra="ignore")

    # Timing
    last_run: Optional[datetime] = None
    simulation_day: int = 1

    # Sprint tracking (accepts both "sprint" and "current_sprint" for backwards compatibility)
    sprint: SprintState = Field(default_factory=SprintState, validation_alias=AliasChoices("sprint", "current_sprint"))

    # Core scenario tracking
    active_scenarios: dict[str, ActiveScenario] = Field(default_factory=dict)
    completed_scenarios: list[str] = Field(default_factory=list)  # scenario_ids

    # Agent states
    agents: dict[str, AgentState] = Field(default_factory=dict)

    # Distribution tracking
    scenario_distribution: ScenarioDistribution = Field(default_factory=ScenarioDistribution)

    # Release management state
    release_state: ReleaseState = Field(default_factory=ReleaseState)

    # NEW: Sprint-level scenario (replaces per-ticket active_scenarios)
    # Stored as dict for JSON serialization, converted to SprintScenario when accessed

    sprint_scenario: Optional[dict[str, Any]] = None
    completed_sprint_scenarios: list[str] = Field(default_factory=list)  # scenario_ids

    # History for LLM context and avoiding repetition
    recent_actions: list[RecentAction] = Field(default_factory=list)
    recent_narrative: str = ""  # LLM's last planning reasoning

    # ========== Sprint Scenario Management (NEW) ==========

    def get_sprint_scenario(self) -> Optional["SprintScenario"]:
        """Get the current sprint scenario as a SprintScenario object."""
        if self.sprint_scenario is None:
            return None
        # Import here to avoid circular dependency
        from src.scenarios import SprintScenario
        return SprintScenario.model_validate(self.sprint_scenario)

    def set_sprint_scenario(self, scenario: "SprintScenario") -> None:
        """Set the current sprint scenario."""
        self.sprint_scenario = scenario.model_dump()

    def clear_sprint_scenario(self) -> None:
        """Clear the current sprint scenario (e.g., when sprint ends)."""
        if self.sprint_scenario:
            scenario_id = self.sprint_scenario.get("scenario_id")
            if scenario_id:
                self.completed_sprint_scenarios.append(scenario_id)
        self.sprint_scenario = None

    def has_active_sprint_scenario(self) -> bool:
        """Check if there's an active sprint scenario."""
        return self.sprint_scenario is not None

    # ========== Legacy Scenario Management (DEPRECATED) ==========

    def add_scenario(self, scenario: ActiveScenario) -> None:
        """Add a new active scenario."""
        self.active_scenarios[scenario.scenario_id] = scenario
        self.scenario_distribution.increment(scenario.scenario_type)

    def complete_scenario(self, scenario_id: str) -> Optional[ActiveScenario]:
        """Mark a scenario as completed and remove from active."""
        if scenario_id in self.active_scenarios:
            scenario = self.active_scenarios.pop(scenario_id)
            self.completed_scenarios.append(scenario_id)

            # Update agent state
            if scenario.assigned_agent and scenario.assigned_agent in self.agents:
                self.agents[scenario.assigned_agent].unassign_ticket(scenario.ticket_key)
                self.agents[scenario.assigned_agent].record_completion()

            return scenario
        return None

    def get_scenario_by_ticket(self, ticket_key: str) -> Optional[ActiveScenario]:
        """Find active scenario for a ticket."""
        for scenario in self.active_scenarios.values():
            if scenario.ticket_key == ticket_key:
                return scenario
        return None

    def get_scenarios_by_phase(self, phase: ScenarioPhase) -> list[ActiveScenario]:
        """Get all scenarios in a specific phase."""
        return [s for s in self.active_scenarios.values() if s.current_phase == phase]

    def get_scenarios_by_agent(self, agent_id: str) -> list[ActiveScenario]:
        """Get all scenarios assigned to an agent."""
        return [s for s in self.active_scenarios.values() if s.assigned_agent == agent_id]

    def sync_agent_workloads(self) -> None:
        """Sync agent workloads from active scenarios.

        Ensures assigned_tickets matches the tickets in active scenarios.
        Call after loading state to fix any inconsistencies.
        """
        # Build a map of agent_id -> assigned ticket keys from scenarios
        agent_tickets: dict[str, list[str]] = {}
        for scenario in self.active_scenarios.values():
            if scenario.current_phase == ScenarioPhase.COMPLETED:
                continue

            # Sync developer assignments
            if scenario.assigned_agent:
                if scenario.assigned_agent not in agent_tickets:
                    agent_tickets[scenario.assigned_agent] = []
                agent_tickets[scenario.assigned_agent].append(scenario.ticket_key)

            # Sync QA assignments for tickets in testing phases
            if scenario.qa_agent and scenario.current_phase in [
                ScenarioPhase.IN_TESTING, ScenarioPhase.RE_TESTING
            ]:
                if scenario.qa_agent not in agent_tickets:
                    agent_tickets[scenario.qa_agent] = []
                agent_tickets[scenario.qa_agent].append(scenario.ticket_key)

        # Update each agent's assigned_tickets and workload
        for agent_id, tickets in agent_tickets.items():
            agent = self.get_agent_state(agent_id)
            for ticket in tickets:
                if ticket not in agent.assigned_tickets:
                    agent.assign_ticket(ticket)

    def get_scenarios_ready_to_advance(self) -> list[ActiveScenario]:
        """Get scenarios that have exceeded their phase target."""
        return [s for s in self.active_scenarios.values() if s.is_phase_ready_to_advance()]

    # ========== Agent Management ==========

    def get_agent_state(self, agent_id: str) -> AgentState:
        """Get or create agent state."""
        if agent_id not in self.agents:
            self.agents[agent_id] = AgentState(agent_id=agent_id)
        return self.agents[agent_id]

    def did_agent_recently_act(self, agent_id: str, minutes: int = 20) -> bool:
        """Check if agent acted recently."""
        agent = self.get_agent_state(agent_id)
        if not agent.last_action:
            return False
        threshold = pendulum.now("UTC") - timedelta(minutes=minutes)
        return agent.last_action > threshold

    # ========== Action Recording ==========

    def record_action(
        self,
        agent_id: str,
        agent_name: str,
        action_type: str,
        ticket_key: Optional[str] = None,
        scenario_id: Optional[str] = None,
        details: Optional[str] = None,
    ) -> None:
        """Record an action in history."""
        action = RecentAction(
            agent_id=agent_id,
            agent_name=agent_name,
            action_type=action_type,
            ticket_key=ticket_key,
            scenario_id=scenario_id,
            details=details,
        )
        self.recent_actions.append(action)

        # Keep only last 50 actions
        if len(self.recent_actions) > 50:
            self.recent_actions = self.recent_actions[-50:]

        # Update agent state
        agent = self.get_agent_state(agent_id)
        agent.record_action(ticket_key)

        # Update scenario if provided
        if scenario_id and scenario_id in self.active_scenarios:
            self.active_scenarios[scenario_id].record_action(action_type, agent_id, details)

        self.last_run = pendulum.now("UTC")

    # ========== Day/Sprint Management ==========

    def is_new_day(self) -> bool:
        """Check if this is a new simulation day."""
        if not self.last_run:
            return True
        return pendulum.now("UTC").date() > self.last_run.date()

    def advance_day(self) -> None:
        """Advance to new simulation day, reset daily counters.

        Note: Sprint day is derived from Jira's start_date, not incremented locally.
        Sprint transitions are detected by comparing sprint_number before/after
        Jira sprint injection in the /trigger endpoint.
        """
        self.simulation_day += 1

        # Reset agent daily counters
        for agent in self.agents.values():
            agent.reset_daily_counters()

    def handle_sprint_transition(self, previous_sprint_number: int) -> bool:
        """Handle sprint transition by resetting agent counters.

        Call after inject_jira_sprint() to detect and handle sprint changes.
        Returns True if a sprint transition occurred.
        """
        current = self.sprint.sprint_number
        if current != previous_sprint_number:
            # Reset agent sprint counters for new sprint
            for agent in self.agents.values():
                agent.reset_sprint_counters(current)
            return True
        return False

    # ========== Serialization Helpers ==========

    def get_board_summary(self) -> dict:
        """Get summary of current board state for LLM context."""
        phases = {}
        for scenario in self.active_scenarios.values():
            phase = scenario.current_phase.value
            if phase not in phases:
                phases[phase] = []
            phases[phase].append({
                "ticket": scenario.ticket_key,
                "type": scenario.scenario_type.value,
                "agent": scenario.assigned_agent,
                "days_in_phase": round(scenario.get_days_in_current_phase(), 1),
                "ready_to_advance": scenario.is_phase_ready_to_advance(),
            })
        return phases

    def get_agent_summary(self) -> dict:
        """Get summary of agent states for LLM context."""
        return {
            agent_id: {
                "workload": agent.current_workload,
                "overloaded": agent.is_overloaded,
                "actions_today": agent.actions_today,
                "assigned": agent.assigned_tickets,
            }
            for agent_id, agent in self.agents.items()
        }

    def get_developer_workload_stats(self, personas: dict) -> dict:
        """Calculate workload statistics for all developers.

        Returns dict with agent_id -> {
            'current_workload': int,
            'sprint_assignments': int,
            'display_name': str,
            'team': str,
            'seniority': str,
            'fairness_score': float  # 0-1, higher = needs more work
        }
        """
        stats = {}
        developers = []

        # Collect all developers from personas
        for agent_id, config in personas.get("agents", {}).items():
            if config.get("role") == "developer":
                agent_state = self.get_agent_state(agent_id)
                developers.append({
                    "agent_id": agent_id,
                    "current_workload": agent_state.current_workload,
                    "sprint_assignments": agent_state.sprint_assignments,
                    "display_name": config.get("display_name", agent_id),
                    "team": config.get("team", "unknown"),
                    "seniority": config.get("seniority", "mid"),
                })

        if not developers:
            return stats

        # Calculate fairness scores (0-1, higher means agent needs more work)
        max_assignments = max(d["sprint_assignments"] for d in developers) or 1
        avg_assignments = sum(d["sprint_assignments"] for d in developers) / len(developers)

        for dev in developers:
            # Score based on how far below average they are
            if avg_assignments > 0:
                relative_deficit = (avg_assignments - dev["sprint_assignments"]) / avg_assignments
            else:
                relative_deficit = 1.0 if dev["sprint_assignments"] == 0 else 0.0

            # Clamp between 0 and 1
            fairness_score = max(0.0, min(1.0, (relative_deficit + 1) / 2))

            # Boost score if they have 0 assignments this sprint
            if dev["sprint_assignments"] == 0:
                fairness_score = 1.0

            stats[dev["agent_id"]] = {
                **dev,
                "fairness_score": round(fairness_score, 2),
            }

        return stats
