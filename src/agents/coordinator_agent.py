"""
Coordinator Agent - Base class for meta-level coordination agents.

Coordinator agents operate at a higher level than regular agents (PM, Dev, QA).
They do NOT have direct Jira access and instead work through directives that
inject actions into other agents' queues.

Key differences from BaseAgent:
- No JiraClient (works through directives)
- Has LLMService for persona-driven communications
- Generates ReleaseDirective objects instead of Jira actions
- Operates during a special COORDINATE phase in the orchestrator
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from ..services.llm_service import LLMService
from ..state import SimulationState, ReleaseDirective


class CoordinatorAgent(ABC):
    """
    Base class for coordination-level agents.

    These agents coordinate other agents through directives rather than
    directly interacting with Jira. They operate at an organizational
    level, ensuring process compliance and coordination.
    """

    def __init__(
        self,
        agent_id: str,
        config: dict,
        llm_service: LLMService,
    ):
        """
        Initialize a coordinator agent.

        Args:
            agent_id: Unique identifier for the agent
            config: Agent configuration from personas.yaml
            llm_service: LLM service for generating communications
        """
        self.agent_id = agent_id
        self.config = config
        self.llm = llm_service

        # Extract persona information
        self.display_name = config.get("display_name", agent_id)
        self.persona = config.get("persona", "")
        self.behaviors = config.get("behaviors", [])
        self.activity_level = config.get("activity_level", "medium")

    @abstractmethod
    async def analyze(
        self,
        state: SimulationState,
        board_snapshot: dict,
    ) -> dict:
        """
        Analyze current state and return findings.

        This method should:
        - Examine the board snapshot for relevant issues
        - Check state for compliance/coordination needs
        - Calculate metrics relevant to the coordinator's responsibility

        Args:
            state: Current simulation state
            board_snapshot: Current Jira board state from analyzer

        Returns:
            Analysis dict with findings, metrics, and issues detected
        """
        pass

    @abstractmethod
    async def generate_directives(
        self,
        analysis: dict,
        state: SimulationState,
    ) -> list[ReleaseDirective]:
        """
        Generate directives for other agents based on analysis.

        Directives are instructions that will be converted into actions
        for specific agents (usually PMs) during the planning phase.

        Args:
            analysis: Results from the analyze() method
            state: Current simulation state

        Returns:
            List of ReleaseDirective objects to be executed
        """
        pass

    def create_directive(
        self,
        directive_type: str,
        target_pm_id: str,
        parameters: dict,
    ) -> ReleaseDirective:
        """
        Create a new directive for another agent.

        Args:
            directive_type: Type of directive (e.g., 'create_version', 'assign_version')
            target_pm_id: The PM agent ID who should execute this directive
            parameters: Directive-specific parameters

        Returns:
            ReleaseDirective object
        """
        return ReleaseDirective(
            directive_type=directive_type,
            target_pm_id=target_pm_id,
            parameters=parameters,
        )

    def get_activity_probability(self) -> float:
        """
        Get probability that coordinator should act this tick.

        Based on activity_level configuration.

        Returns:
            Probability between 0 and 1
        """
        probabilities = {
            "high": 0.9,
            "medium": 0.7,
            "low": 0.5,
        }
        return probabilities.get(self.activity_level, 0.7)

    def should_act(self, state: SimulationState) -> bool:
        """
        Determine if coordinator should take action this tick.

        Coordinators typically act on every tick when there's work to do,
        but this method allows for activity level modulation.

        Args:
            state: Current simulation state

        Returns:
            True if coordinator should analyze and generate directives
        """
        import random
        return random.random() < self.get_activity_probability()

    async def coordinate(
        self,
        state: SimulationState,
        board_snapshot: dict,
    ) -> dict:
        """
        Main entry point for coordination cycle.

        Combines analyze and generate_directives into a single workflow.

        Args:
            state: Current simulation state
            board_snapshot: Current Jira board state

        Returns:
            Dict with analysis results and generated directives
        """
        # Analyze current state
        analysis = await self.analyze(state, board_snapshot)

        # Generate directives based on analysis
        directives = await self.generate_directives(analysis, state)

        return {
            "analysis": analysis,
            "directives": directives,
            "coordinator_id": self.agent_id,
            "coordinator_name": self.display_name,
            "timestamp": datetime.utcnow().isoformat(),
        }
