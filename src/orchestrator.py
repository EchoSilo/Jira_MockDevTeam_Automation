"""
Orchestrator - decides which agents act each tick and coordinates execution.
"""

import random
from typing import Optional

from .agents import PMAgent, DeveloperAgent, QAAgent, TechLeadAgent, BaseAgent
from .services.jira_client import JiraClient
from .services.llm_service import LLMService
from .state.simulation_state import SimulationState


class Orchestrator:
    """Coordinates agent actions for each simulation tick."""

    def __init__(
        self,
        settings: dict,
        personas: dict,
        templates: dict,
        jira_client: JiraClient,
        llm_service: LLMService,
    ):
        self.settings = settings
        self.personas = personas
        self.templates = templates
        self.jira = jira_client
        self.llm = llm_service

        # Initialize agents from config
        self.agents: dict[str, BaseAgent] = {}
        self._initialize_agents()

    def _initialize_agents(self) -> None:
        """Create agent instances from persona config."""
        agent_configs = self.personas.get("agents", {})

        for agent_id, config in agent_configs.items():
            role = config.get("role", "developer")

            # Create appropriate agent type
            if role == "pm":
                agent = PMAgent(
                    agent_id=agent_id,
                    config=config,
                    jira_client=self.jira,
                    llm_service=self.llm,
                    templates=self.templates,
                )
            elif role == "tech_lead":
                agent = TechLeadAgent(
                    agent_id=agent_id,
                    config=config,
                    jira_client=self.jira,
                    llm_service=self.llm,
                    templates=self.templates,
                )
            elif role == "qa":
                agent = QAAgent(
                    agent_id=agent_id,
                    config=config,
                    jira_client=self.jira,
                    llm_service=self.llm,
                    templates=self.templates,
                )
            else:  # developer
                agent = DeveloperAgent(
                    agent_id=agent_id,
                    config=config,
                    jira_client=self.jira,
                    llm_service=self.llm,
                    templates=self.templates,
                )

            self.agents[agent_id] = agent

    def _select_agents_for_tick(
        self,
        state: SimulationState,
        intensity: str,
    ) -> list[BaseAgent]:
        """Select which agents will act this tick."""
        # Determine how many agents act based on intensity
        sim_settings = self.settings.get("simulation", {})
        agents_per_tick = sim_settings.get("agents_per_tick", {"min": 2, "max": 5})

        intensity_multipliers = {
            "light": 0.5,
            "normal": 1.0,
            "busy": 1.5,
        }
        multiplier = intensity_multipliers.get(intensity, 1.0)

        min_agents = max(1, int(agents_per_tick["min"] * multiplier))
        max_agents = min(len(self.agents), int(agents_per_tick["max"] * multiplier))

        target_count = random.randint(min_agents, max_agents)

        # Select agents based on:
        # 1. Haven't acted recently
        # 2. Their activity level (high activity = more likely)
        # 3. Some randomness

        candidates = []
        for agent_id, agent in self.agents.items():
            if agent.should_act(state):
                # Weight by activity level
                weight = {"high": 3, "medium": 2, "low": 1}.get(agent.activity_level, 2)
                candidates.extend([agent] * weight)

        # Shuffle and pick
        random.shuffle(candidates)

        # Deduplicate while preserving some order
        selected = []
        seen = set()
        for agent in candidates:
            if agent.agent_id not in seen and len(selected) < target_count:
                selected.append(agent)
                seen.add(agent.agent_id)

        return selected

    async def run_tick(
        self,
        state: SimulationState,
        intensity: str = "normal",
    ) -> list[dict]:
        """
        Run one simulation tick.
        Returns list of action results.
        """
        results = []

        # Select agents for this tick
        agents = self._select_agents_for_tick(state, intensity)

        if not agents:
            return [{"message": "No agents selected for this tick"}]

        # Execute each agent's action
        for agent in agents:
            try:
                result = await agent.act(state)
                if result:
                    results.append(result)
            except Exception as e:
                results.append({
                    "agent": agent.display_name,
                    "error": str(e),
                    "status": "failed",
                })

        return results

    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """Get an agent by ID."""
        return self.agents.get(agent_id)

    def list_agents(self) -> list[dict]:
        """List all configured agents."""
        return [
            {
                "id": agent_id,
                "name": agent.display_name,
                "team": agent.team,
                "role": agent.role,
            }
            for agent_id, agent in self.agents.items()
        ]
