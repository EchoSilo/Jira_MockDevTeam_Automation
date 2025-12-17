"""
Base Crew class with shared functionality for all scenario crews.
"""

import time
from typing import Optional, TYPE_CHECKING
from crewai import Crew, Task, Process

from ..agents import create_agent
from ..tools.jira_tools import JiraTools
from ..state import ActiveScenario, SimulationState

if TYPE_CHECKING:
    from ..logging import CrewAILoggingCallback


class BaseCrew:
    """
    Base class for all scenario crews.

    Provides common functionality for:
    - Agent creation from persona configs
    - Tool setup
    - LLM configuration
    - Crew execution
    """

    def __init__(
        self,
        personas: dict,
        jira_tools: JiraTools,
        llm_config: dict,
    ):
        """
        Initialize the base crew.

        Args:
            personas: Full personas config from personas.yaml
            jira_tools: Initialized JiraTools instance
            llm_config: LLM configuration with 'routine_model' and 'complex_model'
        """
        self.personas = personas
        self.jira_tools = jira_tools
        self.llm_config = llm_config

        # Optional CrewAI logging callback - set by orchestrator
        self.crewai_callback: "CrewAILoggingCallback | None" = None

        # Cache for created agents
        self._agent_cache: dict = {}

    def get_persona(self, agent_id: str) -> dict:
        """Get persona config for an agent."""
        persona = self.personas.get("agents", {}).get(agent_id, {})
        if not persona:
            raise ValueError(f"Unknown agent: {agent_id}")
        # Add the ID to the persona dict for convenience
        persona["id"] = agent_id
        return persona

    def get_agent(self, agent_id: str, use_complex_llm: bool = False) -> "Agent":
        """
        Get or create a CrewAI agent.

        Args:
            agent_id: The agent ID from personas.yaml
            use_complex_llm: If True, use the complex model (Sonnet)

        Returns:
            CrewAI Agent instance
        """
        cache_key = f"{agent_id}_{use_complex_llm}"

        if cache_key not in self._agent_cache:
            persona = self.get_persona(agent_id)
            role = persona.get("role", "developer")

            llm = (
                self.llm_config.get("complex_model")
                if use_complex_llm
                else self.llm_config.get("routine_model")
            )

            tools = self.jira_tools.get_tools_for_role(role)

            self._agent_cache[cache_key] = create_agent(
                role=role,
                persona_config=persona,
                tools=tools,
                llm=llm,
            )

        return self._agent_cache[cache_key]

    def get_team_agents(self, team: str) -> dict:
        """Get all agent IDs for a team, organized by role."""
        agents_by_role = {
            "pm": None,
            "tech_lead": None,
            "developer": [],
            "qa": None,
        }

        for agent_id, config in self.personas.get("agents", {}).items():
            if config.get("team") == team:
                role = config.get("role", "developer")
                if role in ["pm", "tech_lead", "qa"]:
                    agents_by_role[role] = agent_id
                else:
                    agents_by_role["developer"].append(agent_id)

        return agents_by_role

    def find_agent_by_jira_account(self, account_id: str) -> Optional[str]:
        """Find agent_id by Jira account ID."""
        for agent_id, config in self.personas.get("agents", {}).items():
            if config.get("jira_account_id") == account_id:
                return agent_id
        return None

    def execute_crew(
        self,
        agents: list,
        tasks: list,
        process: Process = Process.sequential,
        verbose: bool = False,
    ) -> str:
        """
        Execute a crew with the given agents and tasks.

        Args:
            agents: List of CrewAI agents
            tasks: List of CrewAI tasks
            process: Crew process type (sequential or hierarchical)
            verbose: Enable verbose output

        Returns:
            Crew execution result as string
        """
        if not agents or not tasks:
            return "No agents or tasks to execute"

        crew = Crew(
            agents=agents,
            tasks=tasks,
            process=process,
            verbose=verbose,
        )

        # Track execution time
        start_time = time.time()
        result = crew.kickoff()
        duration_ms = int((time.time() - start_time) * 1000)

        result_str = str(result)

        # Log usage metrics if callback is available
        if self.crewai_callback:
            try:
                usage_metrics = crew.calculate_usage_metrics()
                # Convert UsageMetrics to dict
                metrics_dict = {
                    "total_tokens": getattr(usage_metrics, "total_tokens", 0),
                    "prompt_tokens": getattr(usage_metrics, "prompt_tokens", 0),
                    "completion_tokens": getattr(usage_metrics, "completion_tokens", 0),
                }
                # Get model from first agent if available
                model = "unknown"
                if agents and hasattr(agents[0], "llm"):
                    model = str(agents[0].llm) if agents[0].llm else "unknown"

                self.crewai_callback.log_crew_usage(
                    usage_metrics=metrics_dict,
                    model=model,
                    duration_ms=duration_ms,
                    crew_output=result_str[:2000],
                )
            except Exception:
                # Don't let logging errors break the flow
                pass

        return result_str

    def create_simple_task(
        self,
        description: str,
        expected_output: str,
        agent,
        context: Optional[list] = None,
    ) -> Task:
        """
        Create a simple task with standard configuration.

        Args:
            description: Task description with instructions
            expected_output: What the task should produce
            agent: The agent to execute this task
            context: Optional list of dependent tasks

        Returns:
            CrewAI Task instance
        """
        return Task(
            description=description,
            expected_output=expected_output,
            agent=agent,
            context=context,
        )
