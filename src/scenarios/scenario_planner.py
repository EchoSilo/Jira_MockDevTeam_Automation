"""Sprint Scenario Planner.

Generates sprint-level scenarios based on backlog content, team capacity,
and release context. Selects appropriate archetypes and creates day-by-day
scripts that map to actual tickets.
"""

import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml

from .sprint_scenario import (
    EventType,
    MoodState,
    ScenarioArchetype,
    ScriptDay,
    ScriptEvent,
    SprintScenario,
)

logger = logging.getLogger(__name__)


class ScenarioPlanner:
    """Plans sprint scenarios based on backlog content and context."""

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize the planner with archetype configuration.

        Args:
            config_path: Path to scenario_archetypes.yaml. Defaults to config/scenario_archetypes.yaml.
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "scenario_archetypes.yaml"

        self.config = self._load_config(config_path)
        self.archetypes = self.config.get("archetypes", {})
        self.events_config = self.config.get("events", {})
        self.comment_templates = self.config.get("comment_templates", {})

    def _load_config(self, config_path: Path) -> dict[str, Any]:
        """Load archetype configuration from YAML."""
        try:
            with open(config_path) as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to load scenario archetypes config: {e}")
            return {}

    def plan_scenario(
        self,
        sprint_id: int,
        sprint_name: str,
        sprint_items: list[dict[str, Any]],
        team_capacity: int,
        release_context: Optional[str] = None,
        previous_sprint_completion: Optional[float] = None,
        sprint_duration_days: int = 7,
    ) -> SprintScenario:
        """Plan a scenario for the upcoming sprint.

        Args:
            sprint_id: The sprint ID/number.
            sprint_name: The sprint name.
            sprint_items: List of tickets in the sprint with their details.
            team_capacity: Team's capacity in story points.
            release_context: Optional release context (e.g., "Sprint before v1.2.0").
            previous_sprint_completion: Completion rate of the previous sprint.
            sprint_duration_days: Length of the sprint in days.

        Returns:
            A SprintScenario with day-by-day script.
        """
        # Analyze sprint content
        analysis = self._analyze_sprint_content(
            sprint_items,
            team_capacity,
            release_context,
            previous_sprint_completion,
        )

        # Select archetype based on analysis
        archetype = self._select_archetype(analysis)
        logger.info(f"Selected archetype '{archetype.value}' for sprint {sprint_id}")

        # Get target completion rate from archetype config
        archetype_config = self.archetypes.get(archetype.value, {})
        completion_range = archetype_config.get("target_completion_rate", {"min": 0.7, "max": 0.8})
        target_completion = random.uniform(completion_range["min"], completion_range["max"])

        # Generate script from archetype template
        script = self._generate_script(
            archetype,
            sprint_items,
            sprint_duration_days,
            analysis,
        )

        # Get ticket keys
        ticket_keys = [item.get("key", "") for item in sprint_items if item.get("key")]

        # Create the scenario
        scenario = SprintScenario.create(
            sprint_id=sprint_id,
            sprint_name=sprint_name,
            archetype=archetype,
            script=script,
            sprint_items=ticket_keys,
            target_completion_rate=target_completion,
            release_context=release_context,
            previous_sprint_completion=previous_sprint_completion,
        )

        return scenario

    def _analyze_sprint_content(
        self,
        sprint_items: list[dict[str, Any]],
        team_capacity: int,
        release_context: Optional[str],
        previous_sprint_completion: Optional[float],
    ) -> dict[str, Any]:
        """Analyze sprint content to inform archetype selection.

        Returns analysis including:
        - item_count: Total items
        - total_points: Total story points
        - capacity_ratio: Points/capacity
        - bug_ratio: Percentage of bugs
        - high_priority_ratio: Percentage of high priority items
        - has_release_pressure: Whether approaching a release
        - previous_was_rough: Whether previous sprint had low completion
        """
        item_count = len(sprint_items)
        total_points = sum(item.get("story_points", 0) or 0 for item in sprint_items)
        capacity_ratio = total_points / team_capacity if team_capacity > 0 else 1.0

        # Count by type
        bugs = sum(1 for item in sprint_items if item.get("type", "").lower() == "bug")
        bug_ratio = bugs / item_count if item_count > 0 else 0

        # Count by priority
        high_priority = sum(
            1 for item in sprint_items
            if item.get("priority", "").lower() in ["highest", "high", "critical"]
        )
        high_priority_ratio = high_priority / item_count if item_count > 0 else 0

        # Release pressure
        has_release_pressure = release_context is not None and any(
            word in release_context.lower()
            for word in ["release", "deadline", "launch", "final"]
        )

        # Previous sprint analysis
        previous_was_rough = (
            previous_sprint_completion is not None and previous_sprint_completion < 0.6
        )

        return {
            "item_count": item_count,
            "total_points": total_points,
            "capacity_ratio": capacity_ratio,
            "bug_ratio": bug_ratio,
            "high_priority_ratio": high_priority_ratio,
            "has_release_pressure": has_release_pressure,
            "previous_was_rough": previous_was_rough,
            "sprint_items": sprint_items,
        }

    def _select_archetype(self, analysis: dict[str, Any]) -> ScenarioArchetype:
        """Select the best archetype based on sprint analysis.

        Uses weighted random selection influenced by sprint conditions.
        """
        weights: dict[ScenarioArchetype, float] = {}

        for archetype_key, archetype_config in self.archetypes.items():
            try:
                archetype = ScenarioArchetype(archetype_key)
            except ValueError:
                continue

            # Start with base weight
            weight = archetype_config.get("selection_weight", 10)

            # Apply condition modifiers
            conditions = archetype_config.get("selection_conditions", [])
            for condition in conditions:
                condition_name = condition.get("condition", "")
                modifier = condition.get("weight_modifier", 0)

                if self._check_condition(condition_name, analysis):
                    weight += modifier
                    logger.debug(f"Archetype {archetype_key}: +{modifier} for {condition_name}")

            weights[archetype] = max(weight, 0)  # Ensure non-negative

        # Weighted random selection
        total_weight = sum(weights.values())
        if total_weight == 0:
            return ScenarioArchetype.SMOOTH_SPRINT

        rand = random.uniform(0, total_weight)
        cumulative = 0
        for archetype, weight in weights.items():
            cumulative += weight
            if rand <= cumulative:
                return archetype

        return ScenarioArchetype.SMOOTH_SPRINT

    def _check_condition(self, condition: str, analysis: dict[str, Any]) -> bool:
        """Check if a selection condition is met."""
        conditions_map = {
            "balanced_workload": lambda a: a["capacity_ratio"] <= 1.0,
            "items_exceed_capacity": lambda a: a["capacity_ratio"] > 1.3,
            "low_bug_ratio": lambda a: a["bug_ratio"] < 0.2,
            "high_bug_ratio": lambda a: a["bug_ratio"] > 0.3,
            "many_high_priority": lambda a: a["high_priority_ratio"] > 0.5,
            "high_complexity_items": lambda a: (
                a["total_points"] / a["item_count"] > 5 if a["item_count"] > 0 else False
            ),
            "cross_team_dependencies": lambda a: False,  # TODO: Implement when we have dependency data
            "pre_release_sprint": lambda a: a["has_release_pressure"],
            "deadline_pressure": lambda a: a["has_release_pressure"],
            "previous_sprint_low_completion": lambda a: a["previous_was_rough"],
            "high_carryover": lambda a: a["previous_was_rough"],
            "new_feature_area": lambda a: False,  # TODO: Implement with epic analysis
        }

        check_func = conditions_map.get(condition)
        if check_func:
            return check_func(analysis)
        return False

    def _generate_script(
        self,
        archetype: ScenarioArchetype,
        sprint_items: list[dict[str, Any]],
        sprint_duration_days: int,
        analysis: dict[str, Any],
    ) -> list[ScriptDay]:
        """Generate a day-by-day script from the archetype template.

        Maps template events to actual tickets from the sprint.
        """
        archetype_config = self.archetypes.get(archetype.value, {})
        template = archetype_config.get("script_template", {})
        mood_progression = archetype_config.get("mood_progression", [])

        # Build mood map
        mood_map = {item["day"]: MoodState(item["mood"]) for item in mood_progression}

        # Get ticket keys for assignment
        ticket_keys = [item.get("key", "") for item in sprint_items if item.get("key")]
        available_tickets = ticket_keys.copy()
        random.shuffle(available_tickets)

        # Ticket pool for different event types
        tickets_for_events: dict[str, list[str]] = {
            "dev_pickup": available_tickets.copy(),
            "blocker": available_tickets.copy(),
            "qa_rejection": available_tickets.copy(),
            "push_to_review": available_tickets.copy(),
            "push_to_qa": available_tickets.copy(),
            "qa_approve": available_tickets.copy(),
            "carryover": available_tickets.copy(),
        }

        script_days = []

        for day in range(1, sprint_duration_days + 1):
            day_key = f"day_{day}"
            day_template = template.get(day_key, [])

            events = []
            for event_template in day_template:
                event = self._create_event_from_template(
                    event_template,
                    day,
                    tickets_for_events,
                    analysis,
                )
                if event:
                    events.append(event)

            # Get mood for this day
            mood = mood_map.get(day)

            script_days.append(ScriptDay(
                day=day,
                events=events,
                mood=mood,
            ))

        return script_days

    def _create_event_from_template(
        self,
        template: dict[str, Any],
        day: int,
        ticket_pools: dict[str, list[str]],
        analysis: dict[str, Any],
    ) -> Optional[ScriptEvent]:
        """Create a ScriptEvent from a template definition."""
        event_name = template.get("event")
        if not event_name:
            return None

        # Map template event name to EventType
        event_type_map = {
            "sprint_planning": EventType.SPRINT_PLANNING,
            "dev_pickup": EventType.DEV_PICKUP,
            "dev_progress": EventType.DEV_PROGRESS,
            "push_to_review": EventType.PUSH_TO_REVIEW,
            "review_complete": EventType.REVIEW_COMPLETE,
            "push_to_qa": EventType.PUSH_TO_QA,
            "qa_approve": EventType.QA_APPROVE,
            "qa_rejection": EventType.QA_REJECTION,
            "blocker": EventType.BLOCKER,
            "blocker_discussion": EventType.BLOCKER_DISCUSSION,
            "blocker_resolved": EventType.BLOCKER_RESOLVED,
            "scope_creep": EventType.SCOPE_CREEP,
            "context_switch": EventType.CONTEXT_SWITCH,
            "escalation_comment": EventType.ESCALATION_COMMENT,
            "pm_pressure_comment": EventType.PM_PRESSURE_COMMENT,
            "rush_comment": EventType.RUSH_COMMENT,
            "overtime_comment": EventType.OVERTIME_COMMENT,
            "urgency_comment": EventType.URGENCY_COMMENT,
            "release_prep_comment": EventType.RELEASE_PREP_COMMENT,
            "final_push_comment": EventType.FINAL_PUSH_COMMENT,
            "dev_frustration_comment": EventType.DEV_FRUSTRATION_COMMENT,
            "retro_comment": EventType.RETRO_COMMENT,
            "process_improvement_comment": EventType.PROCESS_IMPROVEMENT_COMMENT,
            "team_health_improved_comment": EventType.TEAM_HEALTH_IMPROVED_COMMENT,
            "workaround_attempted": EventType.WORKAROUND_ATTEMPTED,
            "catch_up_progress": EventType.CATCH_UP_PROGRESS,
            "tech_debt_work": EventType.TECH_DEBT_WORK,
            "rework_in_progress": EventType.REWORK_IN_PROGRESS,
            "rework_complete": EventType.REWORK_COMPLETE,
            "carryover": EventType.CARRYOVER,
            "release_ready": EventType.RELEASE_READY,
            "sprint_complete": EventType.SPRINT_COMPLETE,
        }

        event_type = event_type_map.get(event_name)
        if not event_type:
            logger.warning(f"Unknown event type: {event_name}")
            return None

        # Extract parameters
        count = template.get("count", 1)
        coverage = template.get("coverage")
        percentage = template.get("percentage")
        blocker_type = template.get("blocker_type")
        severity = template.get("severity")
        rejection_reasons = template.get("rejection_reasons", [])

        # Assign tickets based on event type
        ticket_keys: list[str] = []
        pool_key = event_name if event_name in ticket_pools else None

        if pool_key and ticket_pools.get(pool_key):
            if coverage:
                # Coverage-based: take percentage of remaining tickets
                pool = ticket_pools[pool_key]
                take_count = max(1, int(len(pool) * coverage))
                ticket_keys = pool[:take_count]
            elif count > 1:
                # Count-based: take specific number
                pool = ticket_pools[pool_key]
                ticket_keys = pool[:count]
                # Remove used tickets from pool to avoid reuse
                for tk in ticket_keys:
                    if tk in ticket_pools[pool_key]:
                        ticket_pools[pool_key].remove(tk)
            else:
                # Single ticket
                pool = ticket_pools[pool_key]
                if pool:
                    ticket_keys = [pool[0]]
                    # Remove for certain events that "consume" a ticket
                    if event_name in ["qa_approve", "blocker", "qa_rejection"]:
                        ticket_pools[pool_key].remove(pool[0])

        event = ScriptEvent(
            event_type=event_type,
            day=day,
            ticket_keys=ticket_keys,
            ticket_key=ticket_keys[0] if len(ticket_keys) == 1 else None,
            count=count,
            coverage=coverage,
            percentage=percentage,
            blocker_type=blocker_type,
            severity=severity,
            rejection_reasons=rejection_reasons,
            details=template.get("details", {}),
        )

        return event

    def get_archetype_info(self, archetype: ScenarioArchetype) -> dict[str, Any]:
        """Get information about an archetype."""
        config = self.archetypes.get(archetype.value, {})
        return {
            "key": archetype.value,
            "name": config.get("name", archetype.value),
            "description": config.get("description", ""),
            "target_completion_rate": config.get("target_completion_rate", {}),
            "selection_weight": config.get("selection_weight", 10),
        }

    def list_archetypes(self) -> list[dict[str, Any]]:
        """List all available archetypes with their info."""
        return [
            self.get_archetype_info(archetype)
            for archetype in ScenarioArchetype
        ]
