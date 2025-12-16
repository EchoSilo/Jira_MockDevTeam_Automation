"""
Agent module for the Jira Team Simulator.

Provides both legacy agent classes (for backwards compatibility)
and new CrewAI agent factories (for the scenario-driven system).
"""

# Legacy agents (will be deprecated)
from .base_agent import BaseAgent
from .pm_agent import PMAgent
from .developer_agent import DeveloperAgent
from .qa_agent import QAAgent
from .tech_lead_agent import TechLeadAgent

# New CrewAI agent factories
from .agent_factories import (
    create_agent,
    create_pm_agent,
    create_developer_agent,
    create_qa_agent,
    create_tech_lead_agent,
    get_agent_display_info,
    AGENT_FACTORIES,
)

__all__ = [
    # Legacy classes
    "BaseAgent",
    "PMAgent",
    "DeveloperAgent",
    "QAAgent",
    "TechLeadAgent",
    # New factories
    "create_agent",
    "create_pm_agent",
    "create_developer_agent",
    "create_qa_agent",
    "create_tech_lead_agent",
    "get_agent_display_info",
    "AGENT_FACTORIES",
]
