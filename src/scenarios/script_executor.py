"""Script Executor.

Converts sprint scenario script events into orchestrator actions
that agents can execute.
"""

import logging
import random
from typing import Any, Optional

from .sprint_scenario import EventType, ScriptEvent, SprintScenario

logger = logging.getLogger(__name__)


class ScriptExecutor:
    """Executes sprint scenario scripts by converting events to actions."""

    # Map event types to orchestrator action types
    EVENT_TO_ACTION_MAP = {
        EventType.SPRINT_PLANNING: "sprint_planning",
        EventType.DEV_PICKUP: "pick_up_task",
        EventType.DEV_PROGRESS: "log_work",
        EventType.PUSH_TO_REVIEW: "progress_to_review",
        EventType.REVIEW_COMPLETE: "complete_review",
        EventType.PUSH_TO_QA: "progress_to_qa",
        EventType.QA_APPROVE: "qa_approve",
        EventType.QA_REJECTION: "qa_reject",
        EventType.BLOCKER: "inject_blocker",
        EventType.BLOCKER_DISCUSSION: "add_comment",
        EventType.BLOCKER_RESOLVED: "resolve_blocker",
        EventType.REWORK_IN_PROGRESS: "log_work",
        EventType.REWORK_COMPLETE: "progress_to_review",
        EventType.SCOPE_CREEP: "add_to_sprint",
        EventType.CONTEXT_SWITCH: "add_comment",
        EventType.CARRYOVER: "carryover_items",
        EventType.RELEASE_READY: "add_comment",
        EventType.SPRINT_COMPLETE: "complete_sprint",
        # Comment events
        EventType.ESCALATION_COMMENT: "add_comment",
        EventType.PM_PRESSURE_COMMENT: "add_comment",
        EventType.RUSH_COMMENT: "add_comment",
        EventType.OVERTIME_COMMENT: "add_comment",
        EventType.URGENCY_COMMENT: "add_comment",
        EventType.RELEASE_PREP_COMMENT: "add_comment",
        EventType.FINAL_PUSH_COMMENT: "add_comment",
        EventType.DEV_FRUSTRATION_COMMENT: "add_comment",
        EventType.RETRO_COMMENT: "add_comment",
        EventType.PROCESS_IMPROVEMENT_COMMENT: "add_comment",
        EventType.TEAM_HEALTH_IMPROVED_COMMENT: "add_comment",
        EventType.WORKAROUND_ATTEMPTED: "add_comment",
        EventType.CATCH_UP_PROGRESS: "log_work",
        EventType.TECH_DEBT_WORK: "log_work",
    }

    # Map event types to preferred agent types
    EVENT_AGENT_TYPES = {
        EventType.SPRINT_PLANNING: ["pm"],
        EventType.DEV_PICKUP: ["developer", "tech_lead"],
        EventType.DEV_PROGRESS: ["developer", "tech_lead"],
        EventType.PUSH_TO_REVIEW: ["developer"],
        EventType.REVIEW_COMPLETE: ["tech_lead"],
        EventType.PUSH_TO_QA: ["developer", "tech_lead"],
        EventType.QA_APPROVE: ["qa"],
        EventType.QA_REJECTION: ["qa"],
        EventType.BLOCKER: ["developer", "tech_lead"],
        EventType.BLOCKER_DISCUSSION: ["developer", "tech_lead", "pm"],
        EventType.BLOCKER_RESOLVED: ["developer", "tech_lead"],
        EventType.REWORK_IN_PROGRESS: ["developer"],
        EventType.REWORK_COMPLETE: ["developer"],
        EventType.SCOPE_CREEP: ["pm"],
        EventType.CONTEXT_SWITCH: ["developer"],
        EventType.CARRYOVER: ["pm"],
        EventType.RELEASE_READY: ["pm"],
        EventType.SPRINT_COMPLETE: ["pm"],
        EventType.ESCALATION_COMMENT: ["developer", "tech_lead"],
        EventType.PM_PRESSURE_COMMENT: ["pm"],
        EventType.RUSH_COMMENT: ["developer"],
        EventType.OVERTIME_COMMENT: ["developer", "tech_lead"],
        EventType.URGENCY_COMMENT: ["pm"],
        EventType.RELEASE_PREP_COMMENT: ["pm"],
        EventType.FINAL_PUSH_COMMENT: ["pm", "tech_lead"],
        EventType.DEV_FRUSTRATION_COMMENT: ["developer"],
        EventType.RETRO_COMMENT: ["pm", "tech_lead"],
        EventType.PROCESS_IMPROVEMENT_COMMENT: ["tech_lead"],
        EventType.TEAM_HEALTH_IMPROVED_COMMENT: ["pm"],
        EventType.WORKAROUND_ATTEMPTED: ["developer", "tech_lead"],
        EventType.CATCH_UP_PROGRESS: ["developer"],
        EventType.TECH_DEBT_WORK: ["developer", "tech_lead"],
    }

    def __init__(self, agents: list[dict[str, Any]]):
        """Initialize executor with available agents.

        Args:
            agents: List of agent dicts with id, type, team, etc.
        """
        self.agents = agents
        self.agents_by_type: dict[str, list[dict[str, Any]]] = {}

        # Organize agents by type
        for agent in agents:
            agent_type = agent.get("type", "developer")
            if agent_type not in self.agents_by_type:
                self.agents_by_type[agent_type] = []
            self.agents_by_type[agent_type].append(agent)

    def get_actions_for_tick(
        self,
        scenario: SprintScenario,
        max_actions: int = 5,
    ) -> list[dict[str, Any]]:
        """Get orchestrator actions for the current tick.

        Looks at pending events for the current day and converts them
        to executable actions.

        Args:
            scenario: The current sprint scenario.
            max_actions: Maximum number of actions to return.

        Returns:
            List of action dicts for the orchestrator to execute.
        """
        pending_events = scenario.get_pending_events_for_today()

        if not pending_events:
            logger.debug(f"No pending events for day {scenario.current_day}")
            return []

        actions = []
        for event in pending_events[:max_actions]:
            action = self.convert_event_to_action(event, scenario)
            if action:
                actions.append(action)

        return actions

    def convert_event_to_action(
        self,
        event: ScriptEvent,
        scenario: SprintScenario,
    ) -> Optional[dict[str, Any]]:
        """Convert a script event to an orchestrator action.

        Args:
            event: The script event to convert.
            scenario: The parent scenario for context.

        Returns:
            Action dict for the orchestrator, or None if conversion fails.
        """
        action_type = self.EVENT_TO_ACTION_MAP.get(event.event_type)
        if not action_type:
            logger.warning(f"No action mapping for event type: {event.event_type}")
            return None

        # Select agent for this action
        agent_id = self._select_agent_for_event(event, scenario)
        if not agent_id and action_type not in ["add_to_sprint", "carryover_items", "complete_sprint"]:
            logger.warning(f"No agent available for event: {event.event_type}")
            return None

        # Build base action
        action: dict[str, Any] = {
            "type": action_type,
            "agent_id": agent_id,
            "from_scenario": True,
            "scenario_id": scenario.scenario_id,
            "event_id": event.event_id,
        }

        # Add ticket information
        if event.ticket_key:
            action["ticket_key"] = event.ticket_key
        elif event.ticket_keys:
            # For multi-ticket events, we may need to create multiple actions
            # For now, just use the first ticket
            action["ticket_key"] = event.ticket_keys[0] if event.ticket_keys else None
            action["all_ticket_keys"] = event.ticket_keys

        # Add event-specific parameters
        action = self._add_event_specific_params(action, event, scenario)

        return action

    def _select_agent_for_event(
        self,
        event: ScriptEvent,
        scenario: SprintScenario,
    ) -> Optional[str]:
        """Select an appropriate agent for the event.

        Uses the event's preferred agent types and available agents.
        """
        # If event specifies an agent, use it
        if event.agent_id:
            return event.agent_id

        # Get preferred agent types for this event
        preferred_types = self.EVENT_AGENT_TYPES.get(event.event_type, ["developer"])

        # Find available agents of preferred types
        for agent_type in preferred_types:
            agents = self.agents_by_type.get(agent_type, [])
            if agents:
                # If event has a ticket, try to find assigned agent
                if event.ticket_key:
                    assigned = scenario.item_assignments.get(event.ticket_key)
                    if assigned:
                        return assigned

                # Otherwise, pick a random agent of the right type
                return random.choice(agents)["id"]

        return None

    def _add_event_specific_params(
        self,
        action: dict[str, Any],
        event: ScriptEvent,
        scenario: SprintScenario,
    ) -> dict[str, Any]:
        """Add event-specific parameters to the action."""
        event_type = event.event_type

        # Comment events
        if event_type in [
            EventType.ESCALATION_COMMENT,
            EventType.PM_PRESSURE_COMMENT,
            EventType.RUSH_COMMENT,
            EventType.OVERTIME_COMMENT,
            EventType.URGENCY_COMMENT,
            EventType.RELEASE_PREP_COMMENT,
            EventType.FINAL_PUSH_COMMENT,
            EventType.DEV_FRUSTRATION_COMMENT,
            EventType.RETRO_COMMENT,
            EventType.PROCESS_IMPROVEMENT_COMMENT,
            EventType.TEAM_HEALTH_IMPROVED_COMMENT,
            EventType.WORKAROUND_ATTEMPTED,
            EventType.BLOCKER_DISCUSSION,
            EventType.RELEASE_READY,
            EventType.CONTEXT_SWITCH,
        ]:
            action["comment_type"] = event_type.value
            action["mood"] = scenario.current_mood.value if scenario.current_mood else "focused"
            action["use_llm"] = True  # Let LLM generate the comment

        # Blocker events
        elif event_type == EventType.BLOCKER:
            action["blocker_type"] = event.blocker_type or "technical"
            action["severity"] = event.severity or "medium"
            action["use_llm"] = True  # Let LLM generate blocker reason

        # QA rejection
        elif event_type == EventType.QA_REJECTION:
            action["rejection_reasons"] = event.rejection_reasons or [
                "Acceptance criteria not fully met"
            ]
            action["use_llm"] = True

        # Carryover
        elif event_type == EventType.CARRYOVER:
            action["percentage"] = event.percentage or 0.3
            action["ticket_keys"] = event.ticket_keys or scenario.sprint_items

        # Work logging
        elif event_type in [EventType.DEV_PROGRESS, EventType.CATCH_UP_PROGRESS, EventType.TECH_DEBT_WORK]:
            action["work_type"] = event_type.value
            action["use_llm"] = True

        # Add any extra details from the event
        action.update(event.details)

        return action

    def mark_event_executed(
        self,
        scenario: SprintScenario,
        event_id: str,
        result: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Mark an event as executed in the scenario.

        Args:
            scenario: The scenario containing the event.
            event_id: The ID of the event to mark.
            result: Optional execution result to store.

        Returns:
            True if the event was found and marked.
        """
        return scenario.mark_event_executed(event_id, result)

    def check_day_complete(self, scenario: SprintScenario) -> bool:
        """Check if all events for the current day are complete.

        Args:
            scenario: The scenario to check.

        Returns:
            True if all events for current day are executed.
        """
        day_script = scenario.get_current_day_script()
        if day_script:
            return day_script.all_events_executed()
        return True

    def should_advance_day(
        self,
        scenario: SprintScenario,
        simulation_day: int,
        sprint_start_day: int,
    ) -> bool:
        """Determine if the scenario should advance to the next day.

        Args:
            scenario: The current scenario.
            simulation_day: The current simulation day number.
            sprint_start_day: The day the sprint started.

        Returns:
            True if the scenario should advance to the next day.
        """
        # Calculate expected scenario day based on simulation day
        expected_day = simulation_day - sprint_start_day + 1

        # Advance if we're behind
        if scenario.current_day < expected_day:
            return True

        # Or if current day is complete
        if self.check_day_complete(scenario):
            return True

        return False

    def get_progress_report(self, scenario: SprintScenario) -> dict[str, Any]:
        """Get a progress report for the scenario.

        Returns summary of executed vs pending events, completion status, etc.
        """
        total_events = 0
        executed_events = 0
        events_by_day: dict[int, dict[str, int]] = {}

        for script_day in scenario.script:
            day = script_day.day
            day_total = len(script_day.events)
            day_executed = len(script_day.get_executed_events())

            events_by_day[day] = {
                "total": day_total,
                "executed": day_executed,
                "pending": day_total - day_executed,
            }

            total_events += day_total
            executed_events += day_executed

        return {
            "scenario_id": scenario.scenario_id,
            "sprint_id": scenario.sprint_id,
            "current_day": scenario.current_day,
            "archetype": scenario.archetype.value,
            "total_events": total_events,
            "executed_events": executed_events,
            "pending_events": total_events - executed_events,
            "progress_percentage": (executed_events / total_events * 100) if total_events > 0 else 0,
            "events_by_day": events_by_day,
            "is_on_track": scenario.is_on_track(),
            "items_completed": len(scenario.items_completed),
            "items_total": len(scenario.sprint_items),
        }
