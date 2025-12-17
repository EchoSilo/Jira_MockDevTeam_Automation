"""
Enhanced state models for scenario-driven simulation.
Tracks tickets as scenarios with lifecycle phases and target timelines.
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid


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


class ActionRecord(BaseModel):
    """Record of an action taken within a scenario."""
    action_type: str
    agent_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    details: Optional[str] = None


class ActiveScenario(BaseModel):
    """A scenario in progress on a specific ticket."""
    scenario_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    ticket_key: str
    scenario_type: ScenarioType
    complexity: TicketComplexity

    # Timeline
    started: datetime = Field(default_factory=datetime.utcnow)
    target_completion: datetime
    current_phase: ScenarioPhase
    phase_started: datetime = Field(default_factory=datetime.utcnow)
    phase_target_end: datetime

    # Assignment
    assigned_agent: Optional[str] = None
    involved_agents: list[str] = Field(default_factory=list)

    # Context for special scenarios
    blocker_reason: Optional[str] = None
    rejection_reason: Optional[str] = None
    dependency_ticket: Optional[str] = None
    dependency_team: Optional[str] = None

    # Tracking
    actions_taken: list[ActionRecord] = Field(default_factory=list)
    comments_added: int = 0
    times_rejected: int = 0

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

        now = datetime.utcnow()
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
        now = datetime.utcnow()

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
        """Check if current phase has exceeded its target duration."""
        return datetime.utcnow() >= self.phase_target_end

    def is_overdue(self) -> bool:
        """Check if scenario has exceeded target completion."""
        return datetime.utcnow() > self.target_completion

    def get_days_in_current_phase(self) -> float:
        """Get number of days in current phase."""
        delta = datetime.utcnow() - self.phase_started
        return delta.total_seconds() / 86400

    def get_total_cycle_days(self) -> float:
        """Get total days since scenario started."""
        delta = datetime.utcnow() - self.started
        return delta.total_seconds() / 86400


class AgentState(BaseModel):
    """State tracking for a single agent."""
    agent_id: str
    last_action: Optional[datetime] = None
    actions_today: int = 0
    assigned_tickets: list[str] = Field(default_factory=list)

    # Calculated metrics
    current_workload: int = 0

    # Behavioral flags
    is_overloaded: bool = False  # 5+ tickets triggers slower progress

    # Performance tracking (for seniority-based rejection rates)
    recent_rejections: int = 0
    recent_completions: int = 0

    def record_action(self, ticket_key: Optional[str] = None) -> None:
        """Record that agent took an action."""
        self.last_action = datetime.utcnow()
        self.actions_today += 1

    def assign_ticket(self, ticket_key: str) -> None:
        """Assign a ticket to this agent."""
        if ticket_key not in self.assigned_tickets:
            self.assigned_tickets.append(ticket_key)
        self.current_workload = len(self.assigned_tickets)
        self.is_overloaded = self.current_workload >= 5

    def unassign_ticket(self, ticket_key: str) -> None:
        """Remove a ticket from this agent."""
        if ticket_key in self.assigned_tickets:
            self.assigned_tickets.remove(ticket_key)
        self.current_workload = len(self.assigned_tickets)
        self.is_overloaded = self.current_workload >= 5

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


class RecentAction(BaseModel):
    """Record of a recent action for avoiding repetition."""
    agent_id: str
    agent_name: str
    action_type: str
    ticket_key: Optional[str] = None
    scenario_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    details: Optional[str] = None


class SprintState(BaseModel):
    """Current sprint tracking."""
    sprint_number: int = 1
    sprint_day: int = Field(default=1, validation_alias="day")
    total_days: int = 7  # 1-week sprints (Monday to Friday)
    start_date: Optional[datetime] = Field(default_factory=datetime.utcnow)

    @classmethod
    def model_validate(cls, obj, **kwargs):
        """Handle legacy format with 'name' field instead of 'sprint_number'."""
        if isinstance(obj, dict) and "name" in obj and "sprint_number" not in obj:
            # Parse sprint number from name like "Sprint 1"
            try:
                obj["sprint_number"] = int(obj["name"].split()[-1])
            except (ValueError, IndexError):
                obj["sprint_number"] = 1
        return super().model_validate(obj, **kwargs)

    def advance_day(self) -> bool:
        """Advance sprint day, returns True if new sprint started."""
        self.sprint_day += 1
        if self.sprint_day > self.total_days:
            self.sprint_number += 1
            self.sprint_day = 1
            self.start_date = datetime.utcnow()
            return True
        return False

    def is_mid_sprint(self) -> bool:
        """Check if we're in the middle of the sprint (days 3-5 for 7-day sprint)."""
        return 3 <= self.sprint_day <= 5

    def is_sprint_end(self) -> bool:
        """Check if we're near sprint end (last 2 days for 7-day sprint)."""
        return self.sprint_day > self.total_days - 2

    def is_sprint_planning_day(self) -> bool:
        """Check if it's sprint planning day (day 1 = Monday)."""
        return self.sprint_day == 1

    def is_sprint_start(self) -> bool:
        """Check if we're at the start of the sprint (first 2 days)."""
        return self.sprint_day <= 2

    def is_sprint_complete_day(self) -> bool:
        """Check if it's sprint completion day (last day of sprint)."""
        return self.sprint_day == self.total_days  # day 7


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
    # Timing
    last_run: Optional[datetime] = None
    simulation_day: int = 1

    # Sprint tracking (alias for backwards compatibility with old state.json)
    sprint: SprintState = Field(default_factory=SprintState, validation_alias="current_sprint")

    # Core scenario tracking
    active_scenarios: dict[str, ActiveScenario] = Field(default_factory=dict)
    completed_scenarios: list[str] = Field(default_factory=list)  # scenario_ids

    # Agent states
    agents: dict[str, AgentState] = Field(default_factory=dict)

    # Distribution tracking
    scenario_distribution: ScenarioDistribution = Field(default_factory=ScenarioDistribution)

    # History for LLM context and avoiding repetition
    recent_actions: list[RecentAction] = Field(default_factory=list)
    recent_narrative: str = ""  # LLM's last planning reasoning

    # ========== Scenario Management ==========

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
        threshold = datetime.utcnow() - timedelta(minutes=minutes)
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

        self.last_run = datetime.utcnow()

    # ========== Day/Sprint Management ==========

    def is_new_day(self) -> bool:
        """Check if this is a new simulation day."""
        if not self.last_run:
            return True
        return datetime.utcnow().date() > self.last_run.date()

    def advance_day(self) -> None:
        """Advance to new day, reset counters."""
        self.simulation_day += 1

        # Reset agent daily counters
        for agent in self.agents.values():
            agent.reset_daily_counters()

        # Advance sprint
        self.sprint.advance_day()

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
