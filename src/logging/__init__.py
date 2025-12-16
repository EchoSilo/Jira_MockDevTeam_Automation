"""
Logging module for Jira Team Simulator.

Provides comprehensive logging of all LLM interactions, Jira API calls,
agent decisions, and orchestrator events.
"""

from .models import (
    LogCategory,
    LogEntry,
    LLMCallLog,
    JiraAPILog,
    AgentDecisionLog,
    OrchestratorLog,
    SessionLog,
)
from .database import LogDatabase
from .writer import AsyncLogWriter
from .logged_llm_service import LoggedLLMService
from .logged_jira_client import LoggedJiraClient
from .query import LogQueryService
from .api import router as logs_router

__all__ = [
    # Models
    "LogCategory",
    "LogEntry",
    "LLMCallLog",
    "JiraAPILog",
    "AgentDecisionLog",
    "OrchestratorLog",
    "SessionLog",
    # Database
    "LogDatabase",
    # Writer
    "AsyncLogWriter",
    # Wrapped services
    "LoggedLLMService",
    "LoggedJiraClient",
    # Query
    "LogQueryService",
    # API Router
    "logs_router",
]
