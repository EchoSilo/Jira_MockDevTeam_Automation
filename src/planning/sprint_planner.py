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
        personas: Optional[dict] = None,
    ):
        """Initialize sprint planner.

        Args:
            jira_client: Jira client for backlog and sprint operations
            llm_service: LLM service for backlog prioritization
            scheduler: Scheduler for action scheduling
            settings: Configuration settings dict
            personas: Persona config (used to assign real agents to the scheduled
                lifecycle steps so they aren't created ownerless)
        """
        self.jira = jira_client
        self.llm = llm_service
        self.scheduler = scheduler
        self.settings = settings
        self.personas = personas or {}

        # Sprint config (fallbacks only - real cadence/naming is derived from the
        # live active sprint on the board in plan_next_sprint)
        sprint_config = settings.get("sprint", {})
        self.duration_days = sprint_config.get("duration_days", 7)
        self.start_day = sprint_config.get("start_day", "wednesday")
        self.capacity_buffer = sprint_config.get("capacity_buffer", 0.8)
        # Number of future sprints to keep planned ahead
        self.planning_horizon_sprints = sprint_config.get("planning_horizon_sprints", 3)

        # Execution window (minutes) for scheduled lifecycle steps. Wide enough
        # that a normal ~45-min tick reliably lands inside it (a 30-min window
        # is routinely overshot). Configurable via settings.scheduler.
        scheduler_config = settings.get("scheduler", {})
        self.scenario_window_minutes = scheduler_config.get(
            "scenario_window_minutes", 480
        )

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

        # Derive cadence & naming from the live active sprint (board is source of
        # truth), chaining dates off the farthest already-planned future sprint.
        length_days = self._derive_sprint_length(state)
        name_prefix = self._derive_sprint_prefix(state)
        sprint_start = self._derive_next_sprint_start(state, horizon)
        sprint_end = sprint_start.add(days=length_days - 1)

        logger.info(
            "Planning %s %s: %s to %s",
            name_prefix, next_sprint_number,
            sprint_start.format('YYYY-MM-DD'), sprint_end.format('YYYY-MM-DD'),
        )

        # Steps 1-3: fetch, prioritize, and capacity-select the backlog.
        capacity = self._calculate_target_capacity(velocity)
        selected, selection_summary = self._select_from_backlog(capacity)
        if not selected:
            result["error"] = "No backlog items available"
            return result

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

        # Step 6: Create sprint in Jira. If this fails, nothing was actually
        # committed in Jira, so don't persist a phantom sprint plan into the
        # horizon - that would show committed points for a sprint that
        # doesn't even exist on the board.
        try:
            jira_sprint = self._create_jira_sprint(sprint_plan, name_prefix)
        except Exception as e:  # pylint: disable=broad-except
            logger.error("Failed to create Jira sprint: %s", e)
            jira_sprint = None

        if not jira_sprint:
            result["error"] = "Jira sprint creation failed"
            return result

        sprint_id = jira_sprint.get("id")
        sprint_plan.scenario_id = str(sprint_id) if sprint_id is not None else None
        try:
            added_keys = self._populate_jira_sprint(
                sprint_id, sprint_plan.committed_items
            )
        except Exception as e:  # pylint: disable=broad-except
            logger.error("Failed to populate Jira sprint %s: %s", sprint_id, e)
            added_keys = []

        # Only commit what Jira actually confirmed. If population failed
        # partially or fully, recompute committed_items/points down to just
        # the items that were really added instead of the full aspirational
        # selection - otherwise the dashboard shows points for items that
        # never made it into the Jira sprint.
        items_added = len(added_keys)
        if items_added < len(sprint_plan.committed_items):
            points_by_key = {
                item.get("key"): item.get("points", 0) or item.get("story_points", 0)
                for item in selected
            }
            sprint_plan.committed_items = added_keys
            sprint_plan.committed_points = sum(
                points_by_key.get(key, 0) for key in added_keys
            )

        # Step 7: Update state
        horizon.add_sprint_plan(sprint_plan)
        state.set_planning_horizon(horizon)

        result["success"] = True
        result["sprint_plan"] = sprint_plan.model_dump(mode='json')
        result["actions_scheduled"] = len(scheduled_actions)
        result["items_added"] = items_added
        result["sprint_name"] = f"{name_prefix} {next_sprint_number}"

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

    def _calculate_target_capacity(self, velocity: VelocityTracker) -> int:
        """Compute this planning pass's capacity budget from velocity history,
        falling back to a flat default when there's no history yet."""
        self.capacity_planner.velocity = velocity
        capacity = self.capacity_planner.calculate_capacity(
            buffer_percentage=self.capacity_buffer
        )
        if capacity == 0:
            # New team - use default capacity
            capacity = 20
            logger.info("No velocity history - using default capacity of 20")
        return capacity

    def _select_from_backlog(
        self, capacity: int, backlog: Optional[List[dict]] = None
    ) -> tuple[List[dict], dict]:
        """Prioritize and select backlog items up to `capacity` points.

        No Jira writes. Shared by plan_next_sprint and top_up_future_sprints
        so both draw from the same live backlog using identical selection
        logic. Pass a pre-fetched `backlog` to avoid a redundant Jira call
        when the caller already needs to inspect it (e.g. to distinguish
        "nothing fits this capacity" from "nothing left anywhere").
        """
        if backlog is None:
            backlog = self._fetch_backlog()
        if not backlog:
            return [], {"item_count": 0, "total_points": 0, "items": []}

        prioritized = self._prioritize_backlog(backlog)
        selected = self.capacity_planner.select_items(prioritized, capacity)
        summary = self.capacity_planner.get_selection_summary(selected)
        return selected, summary

    def top_up_future_sprints(
        self,
        state: "SimulationState",
        pm_agent_id: str,
    ) -> dict:
        """Top up already-existing future sprints to capacity.

        Unlike plan_next_sprint, this never calls _create_jira_sprint - it
        only adds new backlog items to sprints that already exist on the
        board (scenario_id set), using each sprint's own recorded dates.
        Without this, once N future sprint placeholders exist (however they
        got created - populated or not), plan_to_horizon's count/runway gate
        would never revisit them again, leaving them empty forever.

        Capacity- and spillover-aware: accounts for whatever real Jira
        already has committed to a sprint (from a prior top-up pass, or
        Jira's own rollover carryover) before adding more, and discounts the
        soonest sprint's capacity by any predicted spillover from the
        active sprint (state.get_planning_horizon().predicted_spillover_points).
        """
        horizon = state.get_planning_horizon()
        velocity = state.get_velocity_tracker()
        target_capacity = self._calculate_target_capacity(velocity)
        spillover_discount = horizon.predicted_spillover_points

        candidates = sorted(
            (
                s for s in horizon.future_sprints
                if s.status == SprintPlanStatus.PLANNED and s.scenario_id
            ),
            key=lambda s: s.sprint_number,
        )
        soonest_sprint_number = candidates[0].sprint_number if candidates else None

        populated = []
        for sprint_plan in candidates:
            sprint_id = int(sprint_plan.scenario_id)
            try:
                existing_issues = self.jira.get_sprint_issues(sprint_id)
            except Exception as e:  # pylint: disable=broad-except
                logger.warning(
                    "Could not read issues for sprint %s: %s", sprint_id, e
                )
                continue

            existing_items = self.capacity_planner.issues_to_backlog_items(existing_issues)
            already_committed_points = self.capacity_planner.get_selection_summary(
                existing_items
            )["total_points"]

            discount = spillover_discount if sprint_plan.sprint_number == soonest_sprint_number else 0
            remaining_capacity = max(0, target_capacity - already_committed_points - discount)

            if remaining_capacity <= 0:
                continue  # already full/over capacity - try the next sprint

            backlog = self._fetch_backlog()
            if not backlog:
                break  # nothing left anywhere - no point trying later sprints either

            selected, _ = self._select_from_backlog(remaining_capacity, backlog=backlog)
            if not selected:
                # Backlog has items, but none fit THIS sprint's (possibly
                # small) remaining capacity - a later sprint may have more
                # room, so keep going rather than abandoning the whole pass.
                continue

            try:
                added_keys = self._populate_jira_sprint(
                    sprint_id, [item.get("key") for item in selected]
                )
            except Exception as e:  # pylint: disable=broad-except
                logger.error("Failed to populate Jira sprint %s: %s", sprint_id, e)
                continue

            if not added_keys:
                continue  # this sprint's Jira write failed - still try the next one

            confirmed_items = [i for i in selected if i.get("key") in added_keys]
            added_points = self.capacity_planner.get_selection_summary(
                confirmed_items
            )["total_points"]

            # Merge with what was already there - never overwrite carryover.
            existing_keys = [i["key"] for i in existing_items]
            sprint_plan.committed_items = existing_keys + added_keys
            sprint_plan.committed_points = already_committed_points + added_points
            sprint_plan.velocity_estimate = velocity.get_average_velocity()

            self._schedule_sprint_actions(sprint_plan, confirmed_items, pm_agent_id)

            populated.append({
                "sprint_number": sprint_plan.sprint_number,
                "items_added": len(added_keys),
                "points_added": added_points,
            })

        state.set_planning_horizon(horizon)
        return {
            "pm_agent_id": pm_agent_id,
            "sprints_populated": len(populated),
            "results": populated,
        }

    def _schedule_sprint_actions(
        self,
        sprint_plan: SprintPlan,
        selected_items: List[dict],
        pm_agent_id: str,
    ) -> List["ScheduledAction"]:
        """Generate and schedule actions for sprint items.

        Each item's lifecycle steps are assigned to real team members (round-robin
        across the team's developers) so scheduled actions are never ownerless.
        """
        from src.services.team_resolver import get_team_roster

        team = (
            self.personas.get("agents", {})
            .get(pm_agent_id, {})
            .get("team", "alpha")
        )
        roster = get_team_roster(self.personas, team)
        developers = roster.get("developer") or []

        all_actions = []

        for index, item in enumerate(selected_items):
            ticket_key = item.get("key")

            # Round-robin the primary developer so load spreads across the team.
            primary_dev = (
                developers[index % len(developers)] if developers else None
            )

            # Generate lifecycle script with owners + a wide execution window
            script = self._generate_item_script(item, roster, primary_dev, pm_agent_id)

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

    def _generate_item_script(
        self,
        item: dict,
        roster: dict,
        primary_dev: Optional[str],
        pm_agent_id: str,
    ) -> List[dict]:
        """Generate the lifecycle script for an item with real owners.

        Every step carries a non-empty ``agent_id`` (falling back through
        tech_lead -> first developer -> PM so it is never "") and a wide
        ``window_minutes`` so a normal tick can catch it. ``expected_status``
        stays the precondition guard; ``target_status`` records the destination.
        """
        tech_lead = roster.get("tech_lead")
        qa = roster.get("qa")
        developers = roster.get("developer") or []

        def _fallback(*candidates: Optional[str]) -> str:
            for cand in candidates:
                if cand:
                    return cand
            return pm_agent_id

        dev = _fallback(primary_dev, developers[0] if developers else None, tech_lead)
        reviewer = _fallback(tech_lead, primary_dev, developers[0] if developers else None)
        tester = _fallback(qa, tech_lead, dev)
        window = self.scenario_window_minutes

        return [
            {
                "day": 1, "type": "pick_up_task", "agent_id": dev,
                "expected_status": "To Do", "target_status": "In Progress",
                "window_minutes": window,
            },
            {
                "day": 3, "type": "progress_to_review", "agent_id": dev,
                "expected_status": "In Progress", "target_status": "Code Review",
                "window_minutes": window,
            },
            {
                "day": 4, "type": "complete_review", "agent_id": reviewer,
                "expected_status": "Code Review", "target_status": "Ready for QA",
                "window_minutes": window,
            },
            {
                "day": 5, "type": "qa_approve", "agent_id": tester,
                "expected_status": "Ready for QA", "target_status": "Done",
                "window_minutes": window,
            },
        ]

    def _create_jira_sprint(
        self, sprint_plan: SprintPlan, name_prefix: str = "Sprint"
    ) -> Optional[dict]:
        """Create sprint in Jira using the board's naming convention."""
        sprint_name = f"{name_prefix} {sprint_plan.sprint_number}"
        try:
            result = self.jira.create_sprint(
                name=sprint_name,
                start_date=sprint_plan.start_date.isoformat(),
                end_date=sprint_plan.end_date.isoformat(),
            )
            logger.info("Created Jira sprint: %s", sprint_name)
            return result
        except Exception as e:  # pylint: disable=broad-except
            logger.error("Failed to create Jira sprint: %s", e)
            return None

    def _populate_jira_sprint(
        self, sprint_id: Optional[int], committed_items: List[str]
    ) -> List[str]:
        """Add the committed backlog items to the newly created Jira sprint.

        Without this, a future sprint is created empty on the board. Epics are
        filtered out inside JiraClient.add_issue_to_sprint.

        Returns the keys that were actually confirmed added, so the caller can
        recompute committed_points/committed_items from only what Jira
        confirmed rather than the full aspirational list.
        """
        if not sprint_id or not committed_items:
            return []

        added_keys = []
        for ticket_key in committed_items:
            try:
                if self.jira.add_issue_to_sprint(sprint_id, [ticket_key]):
                    added_keys.append(ticket_key)
            except Exception as e:  # pylint: disable=broad-except
                logger.warning(
                    "Failed to add %s to sprint %s: %s", ticket_key, sprint_id, e
                )
        logger.info(
            "Added %d/%d items to sprint %s", len(added_keys), len(committed_items), sprint_id
        )
        return added_keys

    def _derive_sprint_length(self, state: "SimulationState") -> int:
        """Derive sprint length (days) from the live active sprint on the board."""
        sprint = state.sprint
        try:
            if sprint.jira_start_date and sprint.jira_end_date:
                start = pendulum.parse(sprint.jira_start_date)
                end = pendulum.parse(sprint.jira_end_date)
                days = (end.date() - start.date()).days + 1
                if days > 0:
                    return days
        except Exception:  # pylint: disable=broad-except
            pass
        return sprint.total_days or self.duration_days

    def _derive_sprint_prefix(self, state: "SimulationState") -> str:
        """Derive the sprint name prefix from the active sprint (e.g. 'ESCRUM Sprint 10' -> 'ESCRUM Sprint')."""
        name = state.sprint.jira_sprint_name
        if name:
            parts = name.rsplit(" ", 1)
            if len(parts) == 2 and parts[1].isdigit():
                return parts[0]
            return name
        return "Sprint"

    def _derive_next_sprint_start(
        self, state: "SimulationState", horizon: PlanningHorizon
    ) -> pendulum.DateTime:
        """Compute the next future sprint's start: the day after the latest known sprint end.

        Chains off the farthest already-planned future sprint so repeated planning
        produces back-to-back sprints; falls back to the active sprint's end date.
        """
        planned_ends = [
            s.end_date for s in horizon.future_sprints
            if s.status == SprintPlanStatus.PLANNED
        ]
        base_end: Optional[pendulum.DateTime] = max(planned_ends) if planned_ends else None

        if base_end is None and state.sprint.jira_end_date:
            try:
                base_end = pendulum.parse(state.sprint.jira_end_date)
            except Exception:  # pylint: disable=broad-except
                base_end = None

        if base_end is None:
            base_end = self.scheduler.get_simulation_time()

        return base_end.add(days=1).at(9, 0, 0)

    def plan_to_horizon(
        self,
        state: "SimulationState",
        pm_agent_id: str,
        target_sprints: Optional[int] = None,
        max_iterations: int = 3,
    ) -> dict:
        """Plan future sprints until the horizon holds `target_sprints` planned sprints.

        Unlike check_and_plan (which plans a single sprint when the gate trips),
        this loops so a tick or the manual endpoint can bring the board up to the
        full horizon in one pass. Bounded by max_iterations to cap Jira calls.
        """
        target = target_sprints or self.planning_horizon_sprints
        planned = []
        for _ in range(max_iterations):
            horizon = state.get_planning_horizon()
            # Honor the caller's target and let the runway gate participate:
            # needs_planning() trips when fewer than `target` sprints are planned
            # OR the farthest planned sprint ends within min_days_ahead (14d).
            # Previously only the count was checked, so the runway gate was dead.
            horizon.min_sprints = target
            if not horizon.needs_planning():
                break
            result = self.plan_next_sprint(state, pm_agent_id)
            planned.append(result)
            if not result.get("success"):
                break

        return {
            "pm_agent_id": pm_agent_id,
            "target_sprints": target,
            "sprints_planned": len(planned),
            "results": planned,
        }

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
