"""
Base agent class for all simulation agents.
Provides common functionality and interface.
"""

import random
from abc import ABC, abstractmethod
from typing import Optional

from crewai import Agent, Task, Crew

from ..services.jira_client import JiraClient
from ..services.llm_service import LLMService
from ..state.simulation_state import SimulationState


class BaseAgent(ABC):
    """Base class for all simulation agents."""

    def __init__(
        self,
        agent_id: str,
        config: dict,
        jira_client: JiraClient,
        llm_service: LLMService,
        templates: dict,
    ):
        self.agent_id = agent_id
        self.config = config
        self.jira = jira_client
        self.llm = llm_service
        self.templates = templates

        # Extract common config
        self.display_name = config.get("display_name", agent_id)
        self.team = config.get("team", "unknown")
        self.role = config.get("role", "unknown")
        self.persona = config.get("persona", "")
        self.behaviors = config.get("behaviors", [])
        self.activity_level = config.get("activity_level", "medium")
        self.jira_account_id = config.get("jira_account_id")

    def get_activity_probability(self) -> float:
        """Return probability of this agent acting in a given tick."""
        levels = {
            "high": 0.7,
            "medium": 0.5,
            "low": 0.3,
        }
        return levels.get(self.activity_level, 0.5)

    def should_act(self, state: SimulationState) -> bool:
        """Determine if this agent should act in this tick."""
        # Check if recently acted
        if state.did_agent_recently_act(self.agent_id, minutes=20):
            return False

        # Random chance based on activity level
        return random.random() < self.get_activity_probability()

    def pick_random_template(self, category: str, subcategory: str) -> str:
        """Pick a random comment template."""
        try:
            options = self.templates[category][subcategory]
            return random.choice(options)
        except (KeyError, IndexError):
            return ""

    def log_work_time(self, issue_key: str) -> Optional[dict]:
        """Log a random amount of work time."""
        # Random work time: 15m to 2h
        minutes = random.choice([15, 30, 45, 60, 90, 120])
        time_str = f"{minutes}m" if minutes < 60 else f"{minutes // 60}h"

        if minutes >= 60 and minutes % 60 > 0:
            time_str = f"{minutes // 60}h {minutes % 60}m"

        comment = self.pick_random_template("work_log", "templates")

        try:
            self.jira.log_work(issue_key, time_str, comment)
            return {
                "action": "log_work",
                "ticket": issue_key,
                "time": time_str,
                "agent": self.display_name,
            }
        except Exception as e:
            return None

    @abstractmethod
    async def select_action(self, state: SimulationState) -> Optional[dict]:
        """
        Select and return an action for this agent to take.
        Returns None if no appropriate action available.
        """
        pass

    @abstractmethod
    async def execute_action(self, action: dict, state: SimulationState) -> dict:
        """
        Execute the given action and return result.
        """
        pass

    async def act(self, state: SimulationState) -> Optional[dict]:
        """Main entry point: select and execute an action."""
        action = await self.select_action(state)
        if not action:
            return None

        result = await self.execute_action(action, state)

        # Record the action in state
        state.record_action(
            agent_id=self.agent_id,
            action=action.get("type", "unknown"),
            ticket=action.get("ticket"),
        )

        return result
