"""
Simulation state management.
Persists state between runs to maintain continuity and avoid repetitive actions.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field


class AgentState(BaseModel):
    """State for a single agent."""
    last_action: Optional[datetime] = None
    actions_today: int = 0
    assigned_tickets: list[str] = Field(default_factory=list)
    recent_comments: list[str] = Field(default_factory=list)  # ticket keys commented on recently


class TicketState(BaseModel):
    """Tracked state for an active ticket."""
    assigned_to: Optional[str] = None
    status: str = "To Do"
    started: Optional[datetime] = None
    blocked: bool = False
    comments_count: int = 0
    last_action: Optional[datetime] = None


class SprintState(BaseModel):
    """Current sprint tracking."""
    name: str = "Sprint 1"
    day: int = 1
    total_days: int = 14
    start_date: Optional[datetime] = None


class RecentAction(BaseModel):
    """Record of a recent action for avoiding repetition."""
    agent_id: str
    action: str
    ticket: Optional[str] = None
    timestamp: datetime


class SimulationState(BaseModel):
    """Complete simulation state."""
    last_run: Optional[datetime] = None
    simulation_day: int = 1
    current_sprint: SprintState = Field(default_factory=SprintState)
    agents: dict[str, AgentState] = Field(default_factory=dict)
    active_tickets: dict[str, TicketState] = Field(default_factory=dict)
    recent_actions: list[RecentAction] = Field(default_factory=list)

    def get_agent_state(self, agent_id: str) -> AgentState:
        """Get or create agent state."""
        if agent_id not in self.agents:
            self.agents[agent_id] = AgentState()
        return self.agents[agent_id]

    def record_action(
        self,
        agent_id: str,
        action: str,
        ticket: Optional[str] = None,
    ) -> None:
        """Record an action taken by an agent."""
        now = datetime.utcnow()

        # Update agent state
        agent = self.get_agent_state(agent_id)
        agent.last_action = now
        agent.actions_today += 1

        if ticket and action == "comment":
            agent.recent_comments.append(ticket)
            # Keep only last 5
            agent.recent_comments = agent.recent_comments[-5:]

        # Add to recent actions
        self.recent_actions.append(
            RecentAction(
                agent_id=agent_id,
                action=action,
                ticket=ticket,
                timestamp=now,
            )
        )

        # Keep only last 50 actions
        self.recent_actions = self.recent_actions[-50:]

        self.last_run = now

    def track_ticket(self, ticket_key: str, status: str, assigned_to: Optional[str] = None) -> None:
        """Start tracking or update a ticket."""
        if ticket_key not in self.active_tickets:
            self.active_tickets[ticket_key] = TicketState(
                status=status,
                assigned_to=assigned_to,
                started=datetime.utcnow() if status == "In Progress" else None,
            )
        else:
            ticket = self.active_tickets[ticket_key]
            ticket.status = status
            if assigned_to:
                ticket.assigned_to = assigned_to
            if status == "In Progress" and not ticket.started:
                ticket.started = datetime.utcnow()
            ticket.last_action = datetime.utcnow()

    def get_agent_workload(self, agent_id: str) -> int:
        """Count how many active tickets an agent has."""
        count = 0
        for ticket in self.active_tickets.values():
            if ticket.assigned_to == agent_id and ticket.status not in ["Done", "Closed"]:
                count += 1
        return count

    def reset_daily_counters(self) -> None:
        """Reset daily action counters (call at start of new day)."""
        for agent in self.agents.values():
            agent.actions_today = 0

    def advance_sprint_day(self) -> None:
        """Advance the sprint day counter."""
        self.current_sprint.day += 1
        if self.current_sprint.day > self.current_sprint.total_days:
            # Start new sprint
            sprint_num = int(self.current_sprint.name.split()[-1]) + 1
            self.current_sprint = SprintState(
                name=f"Sprint {sprint_num}",
                day=1,
                total_days=14,
                start_date=datetime.utcnow(),
            )
        self.simulation_day += 1

    def is_new_day(self) -> bool:
        """Check if this is a new simulation day."""
        if not self.last_run:
            return True
        now = datetime.utcnow()
        return now.date() > self.last_run.date()

    def did_agent_recently_act(self, agent_id: str, minutes: int = 30) -> bool:
        """Check if agent acted recently (to avoid back-to-back actions)."""
        agent = self.get_agent_state(agent_id)
        if not agent.last_action:
            return False
        threshold = datetime.utcnow() - timedelta(minutes=minutes)
        return agent.last_action > threshold

    def did_agent_comment_on_ticket(self, agent_id: str, ticket_key: str) -> bool:
        """Check if agent recently commented on a ticket."""
        agent = self.get_agent_state(agent_id)
        return ticket_key in agent.recent_comments


def load_state(path: str = "data/state.json") -> SimulationState:
    """Load state from disk, or create new if doesn't exist."""
    state_path = Path(path)

    if state_path.exists():
        with open(state_path, "r") as f:
            data = json.load(f)
        return SimulationState.model_validate(data)

    return SimulationState()


def save_state(state: SimulationState, path: str = "data/state.json") -> None:
    """Save state to disk."""
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    with open(state_path, "w") as f:
        json.dump(state.model_dump(mode="json"), f, indent=2, default=str)
