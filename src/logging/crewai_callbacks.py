"""
CrewAI logging helpers for tracking LLM usage.

Provides context tracking and metrics logging for CrewAI crew executions.
"""

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .writer import AsyncLogWriter


class CrewAILoggingCallback:
    """
    Context manager for tracking CrewAI LLM usage.

    This class tracks context (agent, ticket, scenario) during crew execution
    and provides methods to log aggregated usage metrics after execution.
    """

    def __init__(self, log_writer: "AsyncLogWriter"):
        """
        Initialize the callback with a log writer.

        Args:
            log_writer: AsyncLogWriter instance for logging
        """
        self.log_writer = log_writer
        self._current_agent_id: Optional[str] = None
        self._current_agent_name: Optional[str] = None
        self._current_ticket_key: Optional[str] = None
        self._current_scenario_id: Optional[str] = None
        self._current_action_type: Optional[str] = None

    def set_context(
        self,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        ticket_key: Optional[str] = None,
        scenario_id: Optional[str] = None,
        action_type: Optional[str] = None,
    ) -> None:
        """
        Set context for the current operation.

        Call this before executing a crew to associate usage metrics
        with the relevant agent and ticket.
        """
        self._current_agent_id = agent_id
        self._current_agent_name = agent_name
        self._current_ticket_key = ticket_key
        self._current_scenario_id = scenario_id
        self._current_action_type = action_type

    def clear_context(self) -> None:
        """Clear the current context after operation completes."""
        self._current_agent_id = None
        self._current_agent_name = None
        self._current_ticket_key = None
        self._current_scenario_id = None
        self._current_action_type = None

    def log_crew_usage(
        self,
        usage_metrics: dict,
        model: str = "unknown",
        duration_ms: int = 0,
        crew_output: str = "",
    ) -> None:
        """
        Log aggregated usage metrics from a crew execution.

        Args:
            usage_metrics: Dict with total_tokens, prompt_tokens, completion_tokens
            model: The LLM model used
            duration_ms: Total execution time in milliseconds
            crew_output: The crew's output/result
        """
        try:
            input_tokens = usage_metrics.get("prompt_tokens", 0) or 0
            output_tokens = usage_metrics.get("completion_tokens", 0) or 0

            # Determine if this is a complex call based on action type in complex_actions list
            complex_actions = getattr(self, '_complex_actions', [
                'scenario_planning', 'create_story', 'create_epic',
                'architectural_comment', 'design_discussion', 'blocker_analysis',
                'dependency_identification', 'generate_release_notes'
            ])
            is_complex = self._current_action_type in complex_actions

            self.log_writer.log_llm_call(
                model=model,
                action_type=self._current_action_type or "crewai_crew_execution",
                prompt=f"[CrewAI Crew Execution - {self._current_action_type}]",
                response=crew_output[:2000] if crew_output else "",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=self._current_agent_name,
                ticket_key=self._current_ticket_key,
                scenario_id=self._current_scenario_id,
                is_complex=is_complex,
            )
        except Exception as e:
            # Don't let logging errors break the flow
            import sys
            print(f"Warning: Failed to log CrewAI usage: {e}", file=sys.stderr)


def setup_crewai_logging(log_writer: "AsyncLogWriter") -> CrewAILoggingCallback:
    """
    Set up CrewAI logging context manager.

    Args:
        log_writer: AsyncLogWriter instance

    Returns:
        The callback instance for context management
    """
    return CrewAILoggingCallback(log_writer)
