"""
Pydantic models for structured logging.

Captures all LLM interactions, Jira API calls, agent decisions,
and orchestrator events for debugging and observability.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field
import uuid


class LogCategory(str, Enum):
    """Categories of log entries."""
    LLM_CALL = "llm_call"
    JIRA_API = "jira_api"
    AGENT_DECISION = "agent_decision"
    ORCHESTRATOR = "orchestrator"
    SESSION = "session"
    SYSTEM = "system"


class LLMCallLog(BaseModel):
    """Log entry for LLM API calls - captures full prompt and response."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    category: LogCategory = LogCategory.LLM_CALL
    session_id: str
    tick_id: str

    # LLM specifics
    model: str
    action_type: str  # e.g., "generate_comment", "scenario_planning"
    is_complex: bool  # True if using Sonnet

    # Message content - full text
    prompt: str
    response: str

    # Request config
    max_tokens: int = 0

    # Token usage
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    # Response metadata
    stop_reason: Optional[str] = None  # e.g., "end_turn", "max_tokens"

    # Context
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    ticket_key: Optional[str] = None
    scenario_id: Optional[str] = None

    # Timing
    duration_ms: int = 0

    # Error tracking
    error: Optional[str] = None
    success: bool = True


class JiraAPILog(BaseModel):
    """Log entry for Jira API calls."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    category: LogCategory = LogCategory.JIRA_API
    session_id: str
    tick_id: str

    # API specifics
    method: str  # e.g., "add_comment", "transition_issue", "create_issue"
    endpoint: Optional[str] = None

    # Request details
    parameters: dict = Field(default_factory=dict)
    ticket_key: Optional[str] = None

    # Response
    status_code: Optional[int] = None
    response_summary: Optional[str] = None

    # Context
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    scenario_id: Optional[str] = None

    # Timing
    duration_ms: int = 0

    # Error tracking
    error: Optional[str] = None
    success: bool = True


class AgentDecisionLog(BaseModel):
    """Log entry for agent decision making."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    category: LogCategory = LogCategory.AGENT_DECISION
    session_id: str
    tick_id: str

    # Agent info
    agent_id: str
    agent_name: str
    agent_role: str
    team: str

    # Decision details
    decision_type: str  # e.g., "action_selection", "should_act"
    action_selected: Optional[str] = None
    alternatives_considered: list[str] = Field(default_factory=list)
    reasoning: Optional[str] = None

    # Context
    ticket_key: Optional[str] = None
    scenario_id: Optional[str] = None
    scenario_phase: Optional[str] = None


class OrchestratorLog(BaseModel):
    """Log entry for orchestrator decisions and phases."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    category: LogCategory = LogCategory.ORCHESTRATOR
    session_id: str
    tick_id: str

    # Phase info
    phase: str  # "analyze", "plan", "execute", "action_result", "update", "complete"

    # Content varies by phase
    intensity: Optional[str] = None
    analysis_summary: Optional[dict] = None
    planned_actions: Optional[list[dict]] = None
    planning_reasoning: Optional[str] = None
    action_type: Optional[str] = None
    action_result: Optional[dict] = None

    # Context
    ticket_key: Optional[str] = None
    scenario_id: Optional[str] = None
    agent_id: Optional[str] = None

    # Errors
    error: Optional[str] = None
    success: bool = True


class SessionLog(BaseModel):
    """Top-level session/tick log - one per /trigger call."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tick_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    category: LogCategory = LogCategory.SESSION

    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None

    # Tick metadata
    intensity: str = "normal"
    simulation_day: int = 0
    sprint_day: int = 0
    sprint_number: int = 0

    # Summary statistics (updated at end)
    llm_calls: int = 0
    jira_calls: int = 0
    actions_planned: int = 0
    actions_completed: int = 0
    errors: int = 0

    # Token totals
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    # Outcome
    success: bool = True
    error_summary: Optional[str] = None


# Union type for all log entries
LogEntry = LLMCallLog | JiraAPILog | AgentDecisionLog | OrchestratorLog | SessionLog
