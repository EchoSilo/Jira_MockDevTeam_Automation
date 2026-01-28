"""Sprint planning orchestrator integrating backlog, capacity, and scheduling.

Orchestrates full sprint planning flow:
1. Check if planning needed (horizon < 2 sprints)
2. Fetch backlog from Jira
3. Prioritize backlog using LLM
4. Select items within capacity
5. Generate scenario script
6. Schedule actions
7. Create sprint in Jira
8. Update planning horizon
"""

import logging
from typing import List, Optional, TYPE_CHECKING

import pendulum

from .models import SprintPlan, PlanningHorizon, SprintPlanStatus
from .velocity_tracker import VelocityTracker
from .capacity_planner import CapacityPlanner
from .scenario_scheduler import ScenarioScheduler

# Conditional import for BacklogPrioritizer (has litellm dependency)
try:
    from .backlog_prioritizer import BacklogPrioritizer
    _has_prioritizer = True
except ImportError:
    _has_prioritizer = False
    BacklogPrioritizer = None

if TYPE_CHECKING:
    from src.services.jira_client import JiraClient
    from src.services.llm_service import LLMService
    from src.state import SimulationState
    from src.scheduling import Scheduler, ScheduledAction

logger = logging.getLogger(__name__)


class SprintPlanner:
    """Orchestrate sprint planning: horizon check -> backlog -> capacity -> schedule.

    Flow:
    1. Check if planning needed (horizon < 2 sprints)
    2. Fetch backlog from Jira
    3. Prioritize backlog using LLM
    4. Select items within capacity
    5. Generate scenario script
    6. Schedule actions
    7. Create sprint in Jira
    8. Update planning horizon
    """

    def __init__(
        self,
        jira_client: "JiraClient",
        llm_service: "LLMService",
        scheduler: "Scheduler",
        settings: dict,
    ):
        """Initialize sprint planner.

        Args:
            jira_client: Jira client for backlog and sprint operations
            llm_service: LLM service for backlog prioritization
            scheduler: Scheduler for action scheduling
            settings: Configuration settings dict
        """
        self.jira = jira_client
        self.llm = llm_service
        self.scheduler = scheduler
        self.settings = settings

        # Sprint config
        sprint_config = settings.get("sprint", {})
        self.duration_days = sprint_config.get("duration_days", 7)
        self.start_day = sprint_config.get("start_day", "wednesday")
        self.capacity_buffer = sprint_config.get("capacity_buffer", 0.8)

        # Components
        self.capacity_planner = CapacityPlanner()
        if _has_prioritizer:
            self.prioritizer = BacklogPrioritizer(llm_service)
        else:
            self.prioritizer = None
        self.scenario_scheduler = ScenarioScheduler()

    def check_and_plan(
        self,
        state: "SimulationState",
        pm_agent_id: str,
    ) -> Optional[dict]:
        """Check if planning needed and execute if so.

        Args:
            state: Current simulation state
            pm_agent_id: PM agent responsible for planning

        Returns:
            Planning result dict if planning occurred, None otherwise
        """
        if not state.needs_sprint_planning():
            logger.debug("Sprint planning not needed - horizon sufficient")
            return None

        logger.info("Sprint planning triggered - horizon below minimum")
        return self.plan_next_sprint(state, pm_agent_id)

    def plan_next_sprint(
        self,
        state: "SimulationState",
        pm_agent_id: str,
    ) -> dict:
        """Plan the next sprint.

        Returns planning result with sprint plan and scheduled actions.
        """
        result = {
            "pm_agent_id": pm_agent_id,
            "success": False,
            "sprint_plan": None,
            "actions_scheduled": 0,
        }

        # Get current context
        horizon = state.get_planning_horizon()
        velocity = state.get_velocity_tracker()
        self.capacity_planner.velocity = velocity

        current_sprint = state.sprint.sprint_number
        next_sprint_number = horizon.get_next_sprint_number(current_sprint)

        # Calculate sprint dates
        sprint_start = self._calculate_sprint_start(
            current_sprint_number=current_sprint,
            next_sprint_number=next_sprint_number,
        )
        sprint_end = sprint_start.add(days=self.duration_days - 1)

        logger.info(
            f"Planning Sprint {next_sprint_number}: "
            f"{sprint_start.format('YYYY-MM-DD')} to {sprint_end.format('YYYY-MM-DD')}"
        )

        # Step 1: Fetch backlog
        backlog = self._fetch_backlog()
        if not backlog:
            result["error"] = "No backlog items available"
            return result

        # Step 2: Prioritize backlog using LLM (or fallback)
        prioritized = self._prioritize_backlog(backlog)

        # Step 3: Calculate capacity and select items
        capacity = self.capacity_planner.calculate_capacity(
            buffer_percentage=self.capacity_buffer
        )
        if capacity == 0:
            # New team - use default capacity
            capacity = 20
            logger.info("No velocity history - using default capacity of 20")

        selected = self.capacity_planner.select_items(prioritized, capacity)
        selection_summary = self.capacity_planner.get_selection_summary(selected)

        logger.info(
            f"Selected {selection_summary['item_count']} items "
            f"({selection_summary['total_points']} points) for Sprint {next_sprint_number}"
        )

        # Step 4: Create sprint plan
        sprint_plan = SprintPlan(
            sprint_number=next_sprint_number,
            start_date=sprint_start,
            end_date=sprint_end,
            committed_items=[item.get("key") for item in selected],
            committed_points=selection_summary["total_points"],
            velocity_estimate=velocity.get_average_velocity(),
        )

        # Step 5: Generate scenario and schedule actions
        scheduled_actions = self._schedule_sprint_actions(
            sprint_plan=sprint_plan,
            selected_items=selected,
            pm_agent_id=pm_agent_id,
        )

        # Step 6: Create sprint in Jira
        try:
            jira_sprint = self._create_jira_sprint(sprint_plan)
            if jira_sprint:
                sprint_plan.scenario_id = jira_sprint.get("id")
        except Exception as e:
            logger.error(f"Failed to create Jira sprint: {e}")
            result["error"] = f"Jira sprint creation failed: {e}"

        # Step 7: Update state
        horizon.add_sprint_plan(sprint_plan)
        state.set_planning_horizon(horizon)

        result["success"] = True
        result["sprint_plan"] = sprint_plan.model_dump(mode='json')
        result["actions_scheduled"] = len(scheduled_actions)

        return result

    def _calculate_sprint_start(
        self,
        current_sprint_number: int,
        next_sprint_number: int,
    ) -> pendulum.DateTime:
        """Calculate start date for next sprint.

        Sprints start on configured day (default: Wednesday).
        """
        # Get current simulation time
        now = self.scheduler.get_simulation_time()

        # Find next occurrence of start day
        day_map = {
            "monday": 0, "tuesday": 1, "wednesday": 2,
            "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
        }
        target_day = day_map.get(self.start_day.lower(), 2)  # Default Wednesday

        days_until_target = (target_day - now.day_of_week) % 7
        if days_until_target == 0:
            days_until_target = 7  # Next week if today is target day

        # Add weeks for sprints beyond immediate next
        sprints_ahead = next_sprint_number - current_sprint_number
        total_days = days_until_target + (sprints_ahead - 1) * self.duration_days

        sprint_start = now.add(days=total_days).at(9, 0, 0)
        return sprint_start

    def _fetch_backlog(self) -> List[dict]:
        """Fetch unassigned backlog items from Jira."""
        try:
            issues = self.jira.get_issues_not_in_sprint(
                issue_types=["Story", "Bug", "Task"]
            )
            return [
                {
                    "key": issue.key,
                    "type": issue.fields.issuetype.name,
                    "summary": issue.fields.summary,
                    "priority": (
                        issue.fields.priority.name
                        if issue.fields.priority else "Medium"
                    ),
                    "points": getattr(
                        issue.fields, "customfield_10016", None  # Story points
                    ) or 0,
                }
                for issue in issues
            ]
        except Exception as e:
            logger.error(f"Failed to fetch backlog: {e}")
            return []

    def _prioritize_backlog(self, backlog: List[dict]) -> List[dict]:
        """Prioritize backlog using LLM or fallback to type-based.

        Args:
            backlog: List of backlog items

        Returns:
            Prioritized list (highest priority first)
        """
        if self.prioritizer:
            try:
                return self.prioritizer.prioritize(backlog)
            except Exception as e:
                logger.warning(f"LLM prioritization failed: {e}, using fallback")
                return self._fallback_prioritize(backlog)
        else:
            return self._fallback_prioritize(backlog)

    def _fallback_prioritize(self, backlog: List[dict]) -> List[dict]:
        """Fallback prioritization by type (Bug > Task > Story > Feature)."""
        priority_order = {"Bug": 0, "Task": 1, "Story": 2, "Feature": 3}
        return sorted(
            backlog,
            key=lambda item: priority_order.get(item.get("type"), 99)
        )

    def _schedule_sprint_actions(
        self,
        sprint_plan: SprintPlan,
        selected_items: List[dict],
        pm_agent_id: str,
    ) -> List["ScheduledAction"]:
        """Generate and schedule actions for sprint items."""
        from src.scheduling import ScheduledAction

        all_actions = []

        for item in selected_items:
            ticket_key = item.get("key")

            # Generate simple scenario script (pick up -> progress -> review -> qa)
            script = self._generate_item_script(item)

            # Convert to scheduled actions
            actions = self.scenario_scheduler.convert_scenario_to_actions(
                scenario_script=script,
                sprint_start_date=sprint_plan.start_date,
                ticket_key=ticket_key,
                scenario_id=sprint_plan.sprint_id,
            )

            # Schedule actions
            self.scheduler.schedule_actions(actions)
            all_actions.extend(actions)

        logger.info(f"Scheduled {len(all_actions)} actions for sprint")
        return all_actions

    def _generate_item_script(self, item: dict) -> List[dict]:
        """Generate basic scenario script for an item.

        More sophisticated scripts can be generated by SprintScenario.
        """
        # Simple lifecycle: pick up -> work -> review -> QA
        return [
            {"day": 1, "type": "pick_up_task", "expected_status": "To Do"},
            {"day": 3, "type": "progress_to_review", "expected_status": "In Progress"},
            {"day": 4, "type": "complete_review", "expected_status": "Code Review"},
            {"day": 5, "type": "qa_approve", "expected_status": "Ready for QA"},
        ]

    def _create_jira_sprint(self, sprint_plan: SprintPlan) -> Optional[dict]:
        """Create sprint in Jira."""
        sprint_name = f"Sprint {sprint_plan.sprint_number}"
        try:
            result = self.jira.create_sprint(
                name=sprint_name,
                start_date=sprint_plan.start_date.isoformat(),
                end_date=sprint_plan.end_date.isoformat(),
            )
            logger.info(f"Created Jira sprint: {sprint_name}")
            return result
        except Exception as e:
            logger.error(f"Failed to create Jira sprint: {e}")
            return None

    def record_sprint_completion(
        self,
        state: "SimulationState",
        sprint_number: int,
        committed: int,
        completed: int,
    ) -> None:
        """Record sprint completion for velocity tracking."""
        velocity = state.get_velocity_tracker()
        velocity.record_sprint(sprint_number, committed, completed)
        state.set_velocity_tracker(velocity)

        horizon = state.get_planning_horizon()
        horizon.complete_sprint(sprint_number)
        state.set_planning_horizon(horizon)

        logger.info(
            f"Sprint {sprint_number} completed: {completed}/{committed} points"
        )
