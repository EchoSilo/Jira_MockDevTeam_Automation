"""
Scenario Orchestrator - main coordination for simulation ticks.

Combines the Analyzer, Planner, and Crews to execute simulation ticks.
"""

import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Optional, TYPE_CHECKING

from ..services.jira_client import JiraClient

logger = logging.getLogger(__name__)
from ..services.llm_service import LLMService
from ..tools.jira_tools import JiraTools
from ..state import (
    SimulationState,
    ActiveScenario,
    ScenarioType,
    ScenarioPhase,
    TicketComplexity,
    ISSUE_TYPE_TO_COMPLEXITY,
)
from ..crews import (
    TicketLifecycleCrew,
    BlockerCrew,
    ReworkCrew,
    ScopeCreepCrew,
    DependencyCrew,
    SprintPlanningCrew,
)
from .analyzer import ScenarioAnalyzer
from .planner import ScenarioPlanner
from .pathfinder import WorkflowPathfinder

if TYPE_CHECKING:
    from ..logging import AsyncLogWriter, CrewAILoggingCallback


class ScenarioOrchestrator:
    """
    Main orchestrator for scenario-driven simulation.

    Coordinates the full tick cycle:
    1. Analyze - detect opportunities
    2. Plan - decide what to do (LLM)
    3. Execute - run crews for planned actions
    4. Update - modify state based on results
    """

    def __init__(
        self,
        jira_client: JiraClient,
        llm_service: LLMService,
        personas: dict,
        templates: dict,
        settings: dict,
    ):
        self.jira = jira_client
        self.llm = llm_service
        self.personas = personas
        self.templates = templates
        self.settings = settings

        # Optional log writer - injected by main.py
        self.log_writer: "AsyncLogWriter | None" = None

        # Optional CrewAI logging callback - set up when log_writer is injected
        self.crewai_callback: "CrewAILoggingCallback | None" = None

        # Create shared JiraTools (log_writer will be set later via set_log_writer)
        self.jira_tools = JiraTools(jira_client)

        # Create LLM config for crews
        routine = settings.get("llm", {}).get("routine_model", "claude-haiku-4-5")
        complex_m = settings.get("llm", {}).get("complex_model", "claude-sonnet-4-5")
        self.llm_config = {
            "routine_model": routine,
            "complex_model": complex_m,
        }

        # Initialize components
        self.analyzer = ScenarioAnalyzer(jira_client, personas, settings)
        self.planner = ScenarioPlanner(llm_service, settings, personas)
        self.pathfinder = WorkflowPathfinder()

        # Initialize crews
        self.lifecycle_crew = TicketLifecycleCrew(personas, self.jira_tools, self.llm_config)
        self.blocker_crew = BlockerCrew(personas, self.jira_tools, self.llm_config)
        self.rework_crew = ReworkCrew(personas, self.jira_tools, self.llm_config)
        self.scope_creep_crew = ScopeCreepCrew(personas, self.jira_tools, self.llm_config)
        self.dependency_crew = DependencyCrew(personas, self.jira_tools, self.llm_config)
        self.sprint_planning_crew = SprintPlanningCrew(
            personas, self.jira_tools, self.llm_config
        )

        # Actions that require sprint membership to execute
        self.sprint_required_actions = {
            "pick_up_task",
            "progress_to_review",
            "complete_review",
            "qa_approve",
            "qa_reject",
            "add_progress_comment",
            "inject_blocker",
            "discuss_blocker",
            "resolve_blocker",
            "acknowledge_rejection",
            "complete_fix",
            "verify_fix",
        }

    def set_log_writer(self, log_writer: "AsyncLogWriter") -> None:
        """
        Set up comprehensive logging for the orchestrator and all crews.

        This method:
        1. Sets the log_writer on the orchestrator
        2. Sets up CrewAI LLM logging callback
        3. Passes the log_writer to JiraTools for Jira API logging
        4. Passes the log_writer to the planner
        5. Passes the callback to all crews for usage tracking
        """
        from ..logging import setup_crewai_logging

        self.log_writer = log_writer

        # Set up CrewAI LLM logging callback
        self.crewai_callback = setup_crewai_logging(log_writer)

        # Pass log_writer to JiraTools for Jira API call logging
        self.jira_tools.log_writer = log_writer

        # Pass log_writer to planner
        self.planner.log_writer = log_writer

        # Pass crewai_callback to all crews for usage metric logging
        self.lifecycle_crew.crewai_callback = self.crewai_callback
        self.blocker_crew.crewai_callback = self.crewai_callback
        self.rework_crew.crewai_callback = self.crewai_callback
        self.scope_creep_crew.crewai_callback = self.crewai_callback
        self.dependency_crew.crewai_callback = self.crewai_callback
        self.sprint_planning_crew.crewai_callback = self.crewai_callback

    def _log_event(
        self,
        phase: str,
        **kwargs,
    ) -> None:
        """Log an orchestrator event if log_writer is available."""
        if self.log_writer:
            self.log_writer.log_orchestrator_event(phase=phase, **kwargs)

            # Also inject log_writer into planner if not already done
            if self.planner.log_writer is None:
                self.planner.log_writer = self.log_writer

    async def run_tick(
        self,
        state: SimulationState,
        intensity: str = "normal",
    ) -> dict:
        """
        Run one simulation tick.

        Args:
            state: Current simulation state
            intensity: Tick intensity ("light", "normal", "busy")

        Returns:
            Dict with tick results including actions taken and updated state
        """
        tick_start = datetime.utcnow()
        results = {
            "tick_start": tick_start.isoformat(),
            "intensity": intensity,
            "actions": [],
            "errors": [],
        }

        # Log tick start
        self._log_event("tick_start", intensity=intensity)

        try:
            # Validate sprint scenario matches active sprint in Jira
            # Note: scenario.sprint_id is the sprint number (e.g., 6) extracted from name,
            # while Jira's active_sprint.id is internal ID (e.g., 74). Use name for comparison.
            active_sprint = self.jira.get_active_sprint()
            sprint_scenario = state.get_sprint_scenario()
            if sprint_scenario and active_sprint:
                scenario_sprint_name = sprint_scenario.sprint_name
                active_sprint_name = active_sprint.get("name")
                if scenario_sprint_name != active_sprint_name:
                    logger.warning(
                        f"Sprint scenario mismatch: scenario is for '{scenario_sprint_name}' "
                        f"but active sprint is '{active_sprint_name}'. Clearing stale scenario."
                    )
                    state.clear_sprint_scenario()

            # Phase 1: Analyze
            analysis = self.analyzer.analyze(state)
            results["analysis"] = {
                "opportunities_found": len(analysis.get("opportunities", [])),
                "metrics": analysis.get("metrics", {}),
            }

            # Build workflow graph from board snapshot (for pathfinding)
            board_snapshot = analysis.get("board_snapshot", {})
            self.pathfinder.build_graph_from_snapshot(board_snapshot)

            # Log analysis phase
            self._log_event(
                "analyze",
                intensity=intensity,
                analysis_summary=results["analysis"],
            )

            # Phase 1.5: Coordinate (Release Management)
            if self.settings.get("release_management", {}).get("enabled", False):
                coordination_result = await self._run_coordination_phase(state, board_snapshot)
                analysis["release_directives"] = coordination_result.get("directives", [])
                analysis["release_analysis"] = coordination_result.get("analysis", {})
                results["release_coordination"] = {
                    "directives_generated": len(coordination_result.get("directives", [])),
                    "version_coverage": coordination_result.get("analysis", {}).get("version_coverage", 0),
                }

                # Log coordination phase
                self._log_event(
                    "coordinate",
                    intensity=intensity,
                    coordination_summary=results["release_coordination"],
                )

            # Phase 2: Plan
            planned_actions = self.planner.plan_tick(analysis, state, intensity)
            results["planned_actions"] = len(planned_actions)
            results["planning_reasoning"] = self.planner.last_reasoning

            # Log planning phase
            self._log_event(
                "plan",
                intensity=intensity,
                planned_actions=planned_actions,
                planning_reasoning=self.planner.last_reasoning,
            )

            # Phase 3: Execute
            for action in planned_actions:
                try:
                    # Set logging context for this action
                    agent_id = action.get("agent_id")
                    ticket_key = action.get("ticket_key")
                    scenario_id = action.get("scenario_id")
                    agent_name = None
                    if agent_id:
                        persona = self.personas.get("agents", {}).get(agent_id, {})
                        agent_name = persona.get("display_name")

                    # Set context on CrewAI callback and JiraTools
                    action_type = action.get("type")
                    if self.crewai_callback:
                        self.crewai_callback.set_context(
                            agent_id=agent_id,
                            agent_name=agent_name,
                            ticket_key=ticket_key,
                            scenario_id=scenario_id,
                            action_type=action_type,
                        )
                    self.jira_tools.set_context(
                        agent_id=agent_id,
                        ticket_key=ticket_key,
                    )

                    action_result = await self._execute_action(action, state)
                    results["actions"].append(action_result)

                    # Clear logging context after action
                    if self.crewai_callback:
                        self.crewai_callback.clear_context()
                    self.jira_tools.clear_context()

                    # Log action execution
                    self._log_event(
                        "action_result",
                        action_type=action.get("type"),
                        action_result=action_result,
                        ticket_key=ticket_key,
                        scenario_id=scenario_id,
                        agent_id=agent_id,
                    )

                    # Phase 4: Update state
                    self._update_state_after_action(action, action_result, state)

                except Exception as e:
                    # Clear logging context on error
                    if self.crewai_callback:
                        self.crewai_callback.clear_context()
                    self.jira_tools.clear_context()

                    error_info = {
                        "action": action,
                        "error": str(e),
                    }
                    results["errors"].append(error_info)

                    # Log error
                    self._log_event(
                        "action_error",
                        action_type=action.get("type"),
                        ticket_key=action.get("ticket_key"),
                        error=str(e),
                    )

        except Exception as e:
            results["errors"].append({
                "phase": "orchestration",
                "error": str(e),
            })

            # Log orchestration error
            self._log_event("orchestration_error", error=str(e))

        results["tick_end"] = datetime.utcnow().isoformat()
        results["actions_completed"] = len(results["actions"])

        # Log tick completion
        self._log_event(
            "tick_complete",
            intensity=intensity,
            analysis_summary={
                "actions_completed": results["actions_completed"],
                "errors": len(results["errors"]),
            },
        )

        # Advance simulation time
        if state.simulation_time:
            state.simulation_time += timedelta(hours=state.tick_duration_hours)
            logger.info(f"Advanced simulation time to {state.simulation_time}")
        else:
            # Initialize if missing (fallback)
            state.simulation_time = datetime.now(timezone.utc)
            logger.info(f"Initialized simulation time to {state.simulation_time}")

        return results

    def _validate_sprint_requirement(self, ticket_key: str) -> bool:
        """Check if ticket is in active sprint and can be worked on."""
        if not ticket_key:
            return True  # No ticket to validate
        return self.jira.is_issue_in_active_sprint(ticket_key)

    async def _run_coordination_phase(
        self,
        state: SimulationState,
        board_snapshot: dict,
    ) -> dict:
        """
        Run the Release Management coordination phase.

        This phase runs the Release Manager agent to:
        1. Analyze version coverage and compliance
        2. Generate directives for PMs to create/assign versions

        Args:
            state: Current simulation state
            board_snapshot: Current Jira board state

        Returns:
            Dict with analysis and generated directives
        """
        result = {
            "analysis": {},
            "directives": [],
        }

        # Clean up duplicate directives from previous ticks
        removed = state.release_state.cleanup_duplicate_directives()
        if removed > 0:
            logger.info(f"Cleaned up {removed} duplicate release directives")

        # Lazy initialization of Release Manager agent
        if not hasattr(self, 'release_manager'):
            rm_config = self.personas.get("agents", {}).get("release_manager", {})
            if rm_config:
                from ..agents import ReleaseManagerAgent
                self.release_manager = ReleaseManagerAgent(
                    agent_id="release_manager",
                    config=rm_config,
                    llm_service=self.llm,
                    settings=self.settings,
                )
            else:
                logger.warning("Release Manager persona not found in config")
                return result

        try:
            # Run coordination cycle
            coordination = await self.release_manager.coordinate(state, board_snapshot)

            result["analysis"] = coordination.get("analysis", {})
            result["directives"] = coordination.get("directives", [])

            # Store directives in state for tracking
            for directive in result["directives"]:
                state.release_state.active_directives.append(directive)

            # Log coordination activity
            logger.info(
                f"Release Manager generated {len(result['directives'])} directives, "
                f"version coverage: {result['analysis'].get('version_coverage', 0)}%"
            )

        except Exception as e:
            logger.error(f"Release coordination failed: {str(e)}")
            result["error"] = str(e)

        return result

    def _find_agent_by_jira_id(self, jira_account_id: str) -> Optional[str]:
        """Find agent_id by their Jira account ID."""
        if not jira_account_id:
            return None
        for agent_id, config in self.personas.get("agents", {}).items():
            if config.get("jira_account_id") == jira_account_id:
                return agent_id
        return None

    def _get_qa_for_team(self, team: str) -> Optional[str]:
        """Get the QA agent for a specific team."""
        for agent_id, config in self.personas.get("agents", {}).items():
            if config.get("team") == team and config.get("role") == "qa":
                return agent_id
        return None

    def _get_team_for_agent(self, agent_id: str) -> Optional[str]:
        """Get the team for an agent."""
        config = self.personas.get("agents", {}).get(agent_id, {})
        return config.get("team")

    def _get_next_available_developer(self) -> dict | None:
        """Get the next available developer for assignment (round-robin)."""
        developers = []
        for agent_id, config in self.personas.get("agents", {}).items():
            if config.get("role") == "developer":
                developers.append({
                    "agent_id": agent_id,
                    "account_id": config.get("jira_account_id"),
                    "name": config.get("display_name"),
                })
        if not developers:
            return None
        # Simple round-robin using a class counter
        if not hasattr(self, "_dev_assignment_index"):
            self._dev_assignment_index = 0
        dev = developers[self._dev_assignment_index % len(developers)]
        self._dev_assignment_index += 1
        return dev

    def _get_unassigned_backlog_items(self) -> list[dict]:
        """Get backlog items not in any sprint, filtered for valid types (no Epics)."""
        try:
            items = self.jira.get_issues_not_in_sprint(
                issue_types=["Story", "Bug", "Task"]
            )
            return [
                {
                    "key": item.key,
                    "type": item.fields.issuetype.name,
                    "priority": (
                        item.fields.priority.name
                        if item.fields.priority
                        else "Medium"
                    ),
                    "summary": item.fields.summary,
                }
                for item in items
            ]
        except Exception as e:
            logger.warning(f"Failed to get unassigned backlog items: {e}")
            return []

    def _auto_fix_sprint_membership(self, ticket_key: str) -> bool:
        """
        Attempt to add a ticket to the active sprint.

        Used when a work action is planned for a ticket that's not in the active sprint.
        Instead of failing, we auto-add the ticket and proceed.

        Returns:
            True if ticket was successfully added to active sprint
        """
        try:
            active_sprint = self.jira.get_active_sprint()
            if not active_sprint:
                logger.warning(f"No active sprint to add {ticket_key} to")
                return False

            sprint_id = active_sprint.get("id")
            success = self.jira.add_issue_to_sprint(sprint_id, [ticket_key])

            if success:
                self.jira.add_comment(
                    ticket_key,
                    "Automatically added to active sprint to complete pending work."
                )
                logger.info(f"Auto-added {ticket_key} to sprint {sprint_id}")
            return success
        except Exception as e:
            logger.warning(f"Failed to auto-add {ticket_key} to sprint: {e}")
            return False

    def _get_or_assign_developer_for_ticket(
        self,
        ticket_key: str,
        fallback_agent_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Get the developer for a ticket, or auto-assign one if none exists.

        Priority:
        1. Jira assignee (if already assigned)
        2. Fallback agent_id (if provided and is a developer)
        3. Any available developer from the team

        If assigning a new developer, also updates Jira.

        Returns:
            agent_id of the developer, or None if no developer available
        """
        # Priority 1: Check Jira assignee
        try:
            issue = self.jira.get_issue(ticket_key)
            if issue.fields.assignee:
                jira_id = issue.fields.assignee.accountId
                agent_id = self._find_agent_by_jira_id(jira_id)
                if agent_id:
                    return agent_id
        except Exception as e:
            logger.warning(f"Failed to get Jira assignee for {ticket_key}: {e}")

        # Priority 2: Use fallback agent if it's a developer
        if fallback_agent_id:
            persona = self.personas.get("agents", {}).get(fallback_agent_id, {})
            if persona.get("role") == "developer":
                self._assign_ticket_to_agent(ticket_key, fallback_agent_id)
                return fallback_agent_id

        # Priority 3: Find any available developer
        dev = self._get_next_available_developer()
        if dev:
            dev_agent_id = dev.get("agent_id")
            self._assign_ticket_to_agent(ticket_key, dev_agent_id)
            logger.info(f"Auto-assigned {dev_agent_id} to {ticket_key}")
            return dev_agent_id

        return None

    def _assign_ticket_to_agent(self, ticket_key: str, agent_id: str) -> bool:
        """Assign a ticket to an agent in Jira."""
        try:
            persona = self.personas.get("agents", {}).get(agent_id, {})
            jira_account_id = persona.get("jira_account_id")
            if jira_account_id:
                success = self.jira.assign_issue(ticket_key, jira_account_id)
                if success:
                    logger.info(f"Assigned {ticket_key} to {agent_id}")
                return success
        except Exception as e:
            logger.warning(f"Failed to assign {ticket_key} to {agent_id}: {e}")
        return False

    async def _execute_action(
        self,
        action: dict,
        state: SimulationState,
    ) -> dict:
        """Execute a single planned action."""
        action_type = action.get("type", "unknown")
        ticket_key = action.get("ticket_key")
        scenario_id = action.get("scenario_id")
        agent_id = action.get("agent_id")
        details = action.get("details", "")

        # Validate sprint requirement for work actions
        if action_type in self.sprint_required_actions and ticket_key:
            if not self._validate_sprint_requirement(ticket_key):
                # Try to auto-fix by adding to active sprint
                if self._auto_fix_sprint_membership(ticket_key):
                    logger.info(
                        f"Auto-added {ticket_key} to active sprint before {action_type}"
                    )
                else:
                    return {
                        "action_type": action_type,
                        "ticket_key": ticket_key,
                        "error": "Ticket not in active sprint and could not be added",
                        "skipped": True,
                        "reason": "sprint_violation",
                    }

        # Get scenario if exists
        scenario = None
        if scenario_id and scenario_id in state.active_scenarios:
            scenario = state.active_scenarios[scenario_id]
        elif ticket_key:
            scenario = state.get_scenario_by_ticket(ticket_key)

        # Route to appropriate crew method
        result = {"action_type": action_type, "ticket_key": ticket_key}

        # ========== Lifecycle Actions ==========
        if action_type == "pick_up_task":
            if not agent_id:
                result["error"] = "No agent specified"
            elif ticket_key:
                # Create scenario if doesn't exist
                if not scenario:
                    scenario = self._create_scenario_for_ticket(ticket_key, agent_id, state)
                # Update assigned_agent if not set (scenario may exist from sync)
                if scenario and not scenario.assigned_agent:
                    scenario.assigned_agent = agent_id
                    if agent_id not in scenario.involved_agents:
                        scenario.involved_agents.append(agent_id)
                result.update(
                    self.lifecycle_crew.pick_up_from_backlog(scenario, agent_id)
                )

        elif action_type == "progress_to_review":
            # Create scenario if it doesn't exist (handles state reset recovery)
            if not scenario and ticket_key:
                dev_agent_id = self._get_or_assign_developer_for_ticket(
                    ticket_key, fallback_agent_id=agent_id
                )
                if dev_agent_id:
                    scenario = self._create_scenario_for_ticket(ticket_key, dev_agent_id, state)
                    # Set phase to IN_PROGRESS since we're moving to review
                    scenario.advance_to_phase(ScenarioPhase.IN_PROGRESS)
            # Update assigned_agent if scenario exists but agent is missing
            if scenario and not scenario.assigned_agent and ticket_key:
                dev_agent_id = self._get_or_assign_developer_for_ticket(
                    ticket_key, fallback_agent_id=agent_id
                )
                if dev_agent_id:
                    scenario.assigned_agent = dev_agent_id
                    if dev_agent_id not in scenario.involved_agents:
                        scenario.involved_agents.append(dev_agent_id)
            if scenario and scenario.assigned_agent:
                result.update(self.lifecycle_crew.progress_to_review(scenario))
            else:
                result["error"] = "No developer available for progress_to_review"

        elif action_type == "complete_review":
            tech_lead_id = action.get("tech_lead_id") or agent_id
            # Create scenario if it doesn't exist (handles state reset recovery)
            if not scenario and ticket_key:
                # Try to find the assigned developer from Jira
                try:
                    issue = self.jira.get_issue(ticket_key)
                    dev_agent_id = None
                    if issue.fields.assignee:
                        assignee_id = issue.fields.assignee.accountId
                        dev_agent_id = self._find_agent_by_jira_id(assignee_id)

                    # If no assignee in Jira, find a developer from the tech lead's team
                    if not dev_agent_id and tech_lead_id:
                        lead_persona = self.personas.get("agents", {}).get(tech_lead_id, {})
                        team = lead_persona.get("team", "alpha")
                        # Get first available developer from team
                        for aid, config in self.personas.get("agents", {}).items():
                            if config.get("team") == team and config.get("role") == "developer":
                                dev_agent_id = aid
                                break

                    if dev_agent_id:
                        scenario = self._create_scenario_for_ticket(ticket_key, dev_agent_id, state)
                        scenario.advance_to_phase(ScenarioPhase.IN_REVIEW)
                except Exception as e:
                    logger.error(f"Failed to create/advance scenario for {ticket_key}: {e}")
            if scenario:
                result.update(
                    self.lifecycle_crew.complete_code_review(scenario, tech_lead_id)
                )
            else:
                result["error"] = "Could not create scenario - no assignee found"

        elif action_type == "qa_approve":
            qa_id = action.get("qa_id") or agent_id
            # Create scenario if it doesn't exist (handles state reset recovery)
            if not scenario and ticket_key:
                try:
                    issue = self.jira.get_issue(ticket_key)
                    dev_agent_id = None
                    if issue.fields.assignee:
                        assignee_id = issue.fields.assignee.accountId
                        dev_agent_id = self._find_agent_by_jira_id(assignee_id)

                    # If no assignee in Jira, find a developer from the QA's team
                    if not dev_agent_id and qa_id:
                        qa_persona = self.personas.get("agents", {}).get(qa_id, {})
                        team = qa_persona.get("team", "alpha")
                        for aid, config in self.personas.get("agents", {}).items():
                            if config.get("team") == team and config.get("role") == "developer":
                                dev_agent_id = aid
                                break

                    if dev_agent_id:
                        scenario = self._create_scenario_for_ticket(ticket_key, dev_agent_id, state)
                        scenario.advance_to_phase(ScenarioPhase.IN_TESTING)
                except Exception as e:
                    logger.error(f"Failed to create/advance scenario for {ticket_key}: {e}")
            if scenario:
                result.update(self.lifecycle_crew.qa_approve(scenario, qa_id))
            else:
                result["error"] = "Could not create scenario - no assignee found"

        elif action_type == "add_progress_comment":
            if scenario:
                result.update(self.lifecycle_crew.add_progress_comment(scenario))

        # ========== Blocker Actions ==========
        elif action_type == "inject_blocker":
            # Create scenario if it doesn't exist (handles state reset recovery)
            if not scenario and ticket_key:
                try:
                    # Use helper that finds/assigns developer with fallback chain
                    dev_agent_id = self._get_or_assign_developer_for_ticket(
                        ticket_key, fallback_agent_id=agent_id
                    )
                    if dev_agent_id:
                        scenario = self._create_scenario_for_ticket(
                            ticket_key, dev_agent_id, state
                        )
                        scenario.advance_to_phase(ScenarioPhase.IN_PROGRESS)
                except Exception as e:
                    logger.error(f"Failed to create/advance scenario for {ticket_key}: {e}")
            # Update assigned_agent if scenario exists but agent is missing
            if scenario and not scenario.assigned_agent and ticket_key:
                dev_agent_id = self._get_or_assign_developer_for_ticket(
                    ticket_key, fallback_agent_id=agent_id
                )
                if dev_agent_id:
                    scenario.assigned_agent = dev_agent_id
                    if dev_agent_id not in scenario.involved_agents:
                        scenario.involved_agents.append(dev_agent_id)
            if scenario and scenario.assigned_agent:
                reason = details or self._generate_blocker_reason()
                result.update(self.blocker_crew.inject_blocker(scenario, reason))
            else:
                result["error"] = "No developer available for blocker injection"

        elif action_type == "discuss_blocker":
            if scenario:
                result.update(self.blocker_crew.discuss_blocker(scenario, agent_id))

        elif action_type == "resolve_blocker":
            if scenario:
                result.update(self.blocker_crew.resolve_blocker(scenario, details))

        # ========== Rework Actions ==========
        elif action_type == "qa_reject":
            if scenario:
                reason = details or self._generate_rejection_reason()
                qa_id = action.get("qa_id")
                result.update(self.rework_crew.qa_reject(scenario, reason, qa_id))

        elif action_type == "acknowledge_rejection":
            if scenario:
                result.update(
                    self.rework_crew.developer_acknowledge_rejection(scenario)
                )

        elif action_type == "complete_fix":
            if scenario:
                result.update(self.rework_crew.developer_fix_issue(scenario))

        elif action_type == "verify_fix":
            if scenario:
                qa_id = action.get("qa_id")
                result.update(self.rework_crew.qa_verify_fix(scenario, qa_id))

        # ========== Scope Creep Actions ==========
        elif action_type == "create_scope_creep":
            pm_id = agent_id
            team = action.get("team", "alpha")
            urgency = details or self._generate_urgency_context()
            result.update(
                self.scope_creep_crew.create_mid_sprint_story(pm_id, team, urgency)
            )

        # ========== Dependency Actions ==========
        elif action_type == "identify_dependency":
            if scenario:
                dep_ticket = action.get("dependency_ticket")
                dep_team = action.get("dependency_team", "beta")
                if dep_ticket:
                    result.update(
                        self.dependency_crew.identify_dependency(
                            scenario, dep_ticket, dep_team
                        )
                    )

        elif action_type == "check_dependency":
            if scenario:
                result.update(
                    self.dependency_crew.pm_coordinate_dependency(
                        scenario,
                        scenario.dependency_ticket or "",
                        scenario.dependency_team or "beta",
                    )
                )

        elif action_type == "resolve_dependency":
            if scenario:
                result.update(
                    self.dependency_crew.resolve_dependency(
                        scenario, details or "Dependency resolved"
                    )
                )

        # ========== Epic Lifecycle Actions ==========
        elif action_type == "update_epic_status":
            epic_key = action.get("epic_key")
            new_status = action.get("suggested_status")
            reason = action.get("reason", "Child issues have progressed")
            pm_id = action.get("pm_id")

            if epic_key and new_status:
                try:
                    # Transition the Epic
                    success = self.jira.transition_issue(epic_key, new_status)
                    if success:
                        # Add comment explaining the status change
                        persona = self.personas.get("agents", {}).get(pm_id, {})
                        pm_name = persona.get("display_name", "Product Manager")
                        comment = (
                            f"Updated Epic status to '{new_status}'. "
                            f"Reason: {reason}. - {pm_name}"
                        )
                        self.jira.add_comment(epic_key, comment)
                        result.update({
                            "success": True,
                            "epic_key": epic_key,
                            "new_status": new_status,
                            "agent": pm_id,
                        })
                    else:
                        result["error"] = f"Could not transition Epic to {new_status}"
                except Exception as e:
                    result["error"] = f"Failed to update Epic status: {str(e)}"

        elif action_type == "assign_epic_to_pm":
            epic_key = action.get("epic_key")
            pm_id = action.get("pm_id")

            if epic_key and pm_id:
                try:
                    persona = self.personas.get("agents", {}).get(pm_id, {})
                    pm_account_id = persona.get("jira_account_id")
                    pm_name = persona.get("display_name", "Product Manager")

                    if pm_account_id:
                        # Assign the Epic to the PM
                        self.jira.assign_issue(epic_key, pm_account_id)
                        # Add comment explaining the assignment
                        comment = (
                            f"Assigned to {pm_name} for Epic ownership. "
                            f"Epics should be managed by Product Management."
                        )
                        self.jira.add_comment(epic_key, comment)
                        result.update({
                            "success": True,
                            "epic_key": epic_key,
                            "assigned_to": pm_name,
                            "agent": pm_id,
                        })
                    else:
                        result["error"] = "PM account ID not found"
                except Exception as e:
                    result["error"] = f"Failed to assign Epic: {str(e)}"

        # ========== Sprint Planning Actions ==========
        elif action_type == "sprint_planning":
            pm_id = action.get("pm_id")
            team = action.get("team", "alpha")

            # Check if scenario generation is needed
            scenario_reason = action.get("scenario_reason")
            needs_scenario = scenario_reason or state.get_sprint_scenario() is None

            if needs_scenario:
                # Get sprint info from action or fetch from Jira
                active_sprint = action.get("active_sprint")
                if not active_sprint:
                    sprint_id = action.get("sprint_id")
                    sprint_name = action.get("sprint_name")
                    if sprint_id:
                        active_sprint = {"id": sprint_id, "name": sprint_name}
                    else:
                        active_sprint = self.jira.get_active_sprint()

                # Get unassigned items from action or fetch from Jira
                unassigned_items = action.get("unassigned_items", [])
                if not unassigned_items:
                    unassigned_items = self._get_unassigned_backlog_items()

                if pm_id and active_sprint:
                    try:
                        crew_result = self.sprint_planning_crew.plan_sprint_with_scenario(
                            pm_id=pm_id,
                            team=team,
                            active_sprint=active_sprint,
                            unassigned_items=unassigned_items,
                            state=state,
                        )
                        result.update(crew_result)

                        # Save generated scenario to state
                        if crew_result.get("scenario"):
                            state.set_sprint_scenario(crew_result["scenario"])
                            logger.info(
                                f"Sprint scenario generated for {active_sprint.get('name')}"
                            )
                    except Exception as e:
                        result["error"] = f"Sprint planning with scenario failed: {str(e)}"
            else:
                # Original flow - just plan items without scenario
                active_sprint = action.get("active_sprint", {})
                unassigned_items = action.get("unassigned_items", [])
                if pm_id:
                    try:
                        crew_result = self.sprint_planning_crew.plan_current_sprint(
                            pm_id=pm_id,
                            team=team,
                            active_sprint=active_sprint,
                            unassigned_items=unassigned_items,
                        )
                        result.update(crew_result)
                    except Exception as e:
                        result["error"] = f"Sprint planning failed: {str(e)}"

        elif action_type == "create_future_sprint":
            pm_id = action.get("pm_id")
            team = action.get("team", "alpha")
            sprint_number = action.get("sprint_number", 1)
            start_date = action.get("start_date")

            if pm_id and start_date:
                try:
                    # Use virtual time if available
                    current_date = state.simulation_time.date() if state.simulation_time else datetime.now(timezone.utc).date()
                    
                    crew_result = self.sprint_planning_crew.create_future_sprint(
                        pm_id=pm_id,
                        team=team,
                        sprint_number=sprint_number,
                        start_date=start_date,
                        current_date=current_date,
                    )
                    result.update(crew_result)
                except Exception as e:
                    result["error"] = f"Create future sprint failed: {str(e)}"

        elif action_type == "allocate_to_future_sprint":
            pm_id = action.get("pm_id")
            team = action.get("team", "alpha")
            sprint_info = action.get("sprint_info", {})
            backlog_items = action.get("backlog_items", [])

            if pm_id and sprint_info:
                try:
                    crew_result = self.sprint_planning_crew.allocate_items_to_future_sprint(
                        pm_id=pm_id,
                        team=team,
                        sprint_info=sprint_info,
                        backlog_items=backlog_items,
                    )
                    result.update(crew_result)
                except Exception as e:
                    result["error"] = f"Allocate to future sprint failed: {str(e)}"

        elif action_type == "start_sprint":
            pm_id = action.get("pm_id")
            sprint_id = action.get("sprint_id")
            sprint_name = action.get("sprint_name", f"Sprint {sprint_id}")

            if pm_id and sprint_id:
                try:
                    # Use virtual time if available
                    current_date = state.simulation_time.date() if state.simulation_time else datetime.now(timezone.utc).date()
                    
                    crew_result = self.sprint_planning_crew.start_sprint(
                        pm_id=pm_id,
                        sprint_id=sprint_id,
                        sprint_name=sprint_name,
                        current_date=current_date,
                    )
                    result.update(crew_result)
                except Exception as e:
                    result["error"] = f"Start sprint failed: {str(e)}"

        elif action_type == "complete_sprint":
            pm_id = action.get("pm_id")
            sprint_id = action.get("sprint_id")
            sprint_name = action.get("sprint_name", f"Sprint {sprint_id}")
            next_sprint_id = action.get("next_sprint_id")

            if pm_id and sprint_id:
                try:
                    crew_result = self.sprint_planning_crew.complete_sprint(
                        pm_id=pm_id,
                        sprint_id=sprint_id,
                        sprint_name=sprint_name,
                        next_sprint_id=next_sprint_id,
                    )
                    result.update(crew_result)
                except Exception as e:
                    result["error"] = f"Complete sprint failed: {str(e)}"

        elif action_type == "rollover_sprint":
            pm_id = action.get("pm_id")
            sprint_id = action.get("sprint_id")
            sprint_name = action.get("sprint_name", f"Sprint {sprint_id}")
            new_sprint_name = action.get("new_sprint_name")

            if pm_id and sprint_id:
                try:
                    crew_result = self.sprint_planning_crew.rollover_sprint(
                        pm_id=pm_id,
                        current_sprint_id=sprint_id,
                        current_sprint_name=sprint_name,
                        new_sprint_name=new_sprint_name,
                    )
                    result.update(crew_result)
                except Exception as e:
                    result["error"] = f"Rollover sprint failed: {str(e)}"

        # ========== Violation Fix Actions ==========
        elif action_type == "fix_sprint_violation":
            ticket_key = action.get("ticket_key")
            pm_id = action.get("pm_id")
            fix_comment = action.get("fix_comment", "Added to active sprint.")

            if ticket_key:
                try:
                    # Get active sprint
                    active_sprint = self.jira.get_active_sprint()
                    if active_sprint:
                        sprint_id = active_sprint.get("id")
                        success = self.jira.add_issue_to_sprint(sprint_id, [ticket_key])
                        if success:
                            # Add explanatory comment
                            persona = self.personas.get("agents", {}).get(pm_id, {})
                            pm_name = persona.get("display_name", "Product Manager")
                            comment = f"{fix_comment} - {pm_name}"
                            self.jira.add_comment(ticket_key, comment)
                            result.update({
                                "success": True,
                                "ticket_key": ticket_key,
                                "sprint_id": sprint_id,
                                "agent": pm_id,
                                "fix_type": "added_to_sprint",
                            })
                        else:
                            result["error"] = "Could not add issue to sprint"
                    else:
                        result["error"] = "No active sprint found"
                except Exception as e:
                    result["error"] = f"Fix sprint violation failed: {str(e)}"

        elif action_type == "fix_issue_type_violation":
            epic_key = action.get("epic_key")
            pm_id = action.get("pm_id")
            fix_comment = action.get("fix_comment", "Reassigned to PM.")

            if epic_key and pm_id:
                try:
                    persona = self.personas.get("agents", {}).get(pm_id, {})
                    pm_account_id = persona.get("jira_account_id")
                    pm_name = persona.get("display_name", "Product Manager")

                    if pm_account_id:
                        # Reassign Epic to PM
                        self.jira.assign_issue(epic_key, pm_account_id)
                        # Add explanatory comment
                        comment = f"{fix_comment} - {pm_name}"
                        self.jira.add_comment(epic_key, comment)
                        result.update({
                            "success": True,
                            "epic_key": epic_key,
                            "assigned_to": pm_name,
                            "agent": pm_id,
                            "fix_type": "reassigned_to_pm",
                        })
                    else:
                        result["error"] = "PM account ID not found"
                except Exception as e:
                    result["error"] = f"Fix issue type violation failed: {str(e)}"

        elif action_type == "fix_unassigned_sprint_item":
            ticket_key = action.get("ticket_key")
            if ticket_key:
                try:
                    # Find an available developer to assign
                    developer = self._get_next_available_developer()
                    if developer:
                        self.jira.assign_issue(ticket_key, developer["account_id"])
                        result.update({
                            "success": True,
                            "ticket_key": ticket_key,
                            "assigned_to": developer["name"],
                            "fix_type": "assigned_to_developer",
                        })
                    else:
                        result["error"] = "No available developers found"
                except Exception as e:
                    result["error"] = f"Fix unassigned sprint item failed: {str(e)}"

        elif action_type == "fix_epic_sprint_violation":
            ticket_key = action.get("ticket_key")
            pm_id = action.get("pm_id")
            fix_comment = action.get(
                "fix_comment",
                "Removed from sprint - Epics should not be assigned to sprints."
            )

            if ticket_key:
                try:
                    # Remove Epic from sprint
                    success = self.jira.remove_issue_from_sprint(ticket_key)
                    if success:
                        # Add explanatory comment
                        persona = self.personas.get("agents", {}).get(pm_id, {})
                        pm_name = persona.get("display_name", "Product Manager")
                        comment = f"{fix_comment} - {pm_name}"
                        self.jira.add_comment(ticket_key, comment)
                        result.update({
                            "success": True,
                            "ticket_key": ticket_key,
                            "agent": pm_id,
                            "fix_type": "removed_epic_from_sprint",
                        })
                    else:
                        result["error"] = "Could not remove Epic from sprint"
                except Exception as e:
                    result["error"] = f"Fix epic sprint violation failed: {str(e)}"

        # ========== Release Management Actions ==========
        elif action_type == "create_fix_version":
            pm_id = action.get("agent_id")
            version_name = action.get("version_name")
            target_date_str = action.get("target_date")
            reason = action.get("reason", "")

            if version_name:
                try:
                    from datetime import date

                    # Parse target date if provided
                    release_date = None
                    if target_date_str:
                        try:
                            release_date = date.fromisoformat(target_date_str[:10])
                        except (ValueError, TypeError):
                            pass

                    # Create version in Jira
                    version = self.jira.create_fix_version(
                        name=version_name,
                        release_date=release_date,
                    )

                    if version:
                        # Get PM name for comment
                        persona = self.personas.get("agents", {}).get(pm_id, {})
                        pm_name = persona.get("display_name", "Product Manager")

                        # Update release state
                        for release in state.release_state.planned_releases:
                            if release.name == version_name:
                                release.created_in_jira = True
                                break

                        # Mark directive as executed if from directive
                        if action.get("from_directive") and action.get("directive_id"):
                            state.release_state.mark_directive_executed(
                                action.get("directive_id"),
                                f"Created version {version_name}",
                            )

                        result.update({
                            "success": True,
                            "jira_success": True,
                            "version_name": version_name,
                            "version_id": version.get("id"),
                            "agent": pm_id,
                            "reason": reason,
                        })

                        logger.info(f"Created fix version {version_name} by {pm_name}")
                    else:
                        result["error"] = f"Failed to create version {version_name} in Jira"
                except Exception as e:
                    result["error"] = f"Create fix version failed: {str(e)}"

        elif action_type == "assign_fix_version":
            pm_id = action.get("agent_id")
            ticket_key = action.get("ticket_key")
            version_name = action.get("version_name")
            reason = action.get("reason", "Ensuring release tracking coverage")

            if ticket_key and version_name:
                try:
                    # Assign version in Jira
                    success = self.jira.set_fix_version(ticket_key, version_name)

                    if success:
                        # Get PM name for comment
                        persona = self.personas.get("agents", {}).get(pm_id, {})
                        pm_name = persona.get("display_name", "Product Manager")

                        # Add explanatory comment
                        comment = f"Assigned to release {version_name}. {reason} - {pm_name}"
                        self.jira.add_comment(ticket_key, comment)

                        # Update scenario if exists
                        scenario = state.get_scenario_by_ticket(ticket_key)
                        if scenario:
                            scenario.fix_version = version_name

                        # Mark directive as executed if from directive
                        if action.get("from_directive") and action.get("directive_id"):
                            state.release_state.mark_directive_executed(
                                action.get("directive_id"),
                                f"Assigned {ticket_key} to {version_name}",
                            )

                        result.update({
                            "success": True,
                            "jira_success": True,
                            "ticket_key": ticket_key,
                            "version_name": version_name,
                            "agent": pm_id,
                            "reason": reason,
                        })

                        logger.info(f"Assigned {ticket_key} to version {version_name} by {pm_name}")
                    else:
                        result["error"] = f"Failed to set fix version on {ticket_key}"
                except Exception as e:
                    result["error"] = f"Assign fix version failed: {str(e)}"

        elif action_type == "release_reminder":
            # Release reminder is informational - just log it
            pm_id = action.get("agent_id")
            release_name = action.get("release_name", "")
            message = action.get("message", "")

            result.update({
                "success": True,
                "release_name": release_name,
                "agent": pm_id,
                "message": message,
            })

            logger.info(f"Release reminder sent for {release_name}")

        elif action_type == "release_version":
            pm_id = action.get("agent_id")
            version_name = action.get("version_name")
            transition_done = action.get("transition_done_to_closed", True)
            reason = action.get("reason", "")

            if version_name:
                try:
                    closed_count = 0

                    # Transition Done items to Closed if requested
                    if transition_done:
                        done_issues = self.jira.get_issues_by_fix_version(
                            version_name,
                            statuses=["Done"]
                        )
                        for issue in done_issues:
                            try:
                                success = self.jira.transition_issue(
                                    issue.key, "Closed"
                                )
                                if success:
                                    closed_count += 1
                                else:
                                    # Try alternate terminal status names
                                    for alt_status in ["Close", "Close Issue", "Resolve"]:
                                        success = self.jira.transition_issue(
                                            issue.key, alt_status
                                        )
                                        if success:
                                            closed_count += 1
                                            break
                            except Exception as e:
                                logger.warning(f"Failed to close {issue.key}: {e}")

                    # Mark version as released in Jira
                    release_success = self.jira.release_version(version_name)

                    if release_success:
                        # Update state
                        for release in state.release_state.planned_releases:
                            if release.name == version_name:
                                release.status = "released"
                                break

                        # Mark directive as executed if from directive
                        if action.get("from_directive") and action.get("directive_id"):
                            state.release_state.mark_directive_executed(
                                action.get("directive_id"),
                                f"Released {version_name}, closed {closed_count} items",
                            )

                        # Get PM name for logging
                        persona = self.personas.get("agents", {}).get(pm_id, {})
                        pm_name = persona.get("display_name", "Product Manager")

                        result.update({
                            "success": True,
                            "jira_success": True,
                            "version_name": version_name,
                            "items_closed": closed_count,
                            "agent": pm_id,
                            "reason": reason,
                        })

                        logger.info(
                            f"Released {version_name} by {pm_name}, "
                            f"transitioned {closed_count} items to Closed"
                        )
                    else:
                        result["error"] = f"Failed to release version {version_name} in Jira"
                except Exception as e:
                    result["error"] = f"Release version failed: {str(e)}"

        elif action_type == "rollover_items":
            pm_id = action.get("agent_id")
            from_version = action.get("from_version")
            to_version = action.get("to_version")
            reason = action.get("reason", "")

            if from_version and to_version:
                try:
                    # Get non-Done items from source version
                    all_issues = self.jira.get_issues_by_fix_version(from_version)
                    rollover_issues = [
                        i for i in all_issues
                        if i.fields.status.name.lower() not in ["done", "closed"]
                    ]

                    rolled_count = 0
                    for issue in rollover_issues:
                        try:
                            # Change fix version
                            self.jira.set_fix_version(issue.key, to_version)
                            rolled_count += 1

                            # Add explanatory comment
                            persona = self.personas.get("agents", {}).get(pm_id, {})
                            pm_name = persona.get("display_name", "Product Manager")
                            comment = (
                                f"Rolled over from {from_version} to {to_version}. "
                                f"Item was not completed before release. - {pm_name}"
                            )
                            self.jira.add_comment(issue.key, comment)
                        except Exception as e:
                            logger.warning(f"Failed to rollover {issue.key}: {e}")

                    # Mark directive as executed if from directive
                    if action.get("from_directive") and action.get("directive_id"):
                        state.release_state.mark_directive_executed(
                            action.get("directive_id"),
                            f"Rolled {rolled_count} items from {from_version} to {to_version}",
                        )

                    result.update({
                        "success": True,
                        "jira_success": True,
                        "from_version": from_version,
                        "to_version": to_version,
                        "rolled_count": rolled_count,
                        "agent": pm_id,
                        "reason": reason,
                    })

                    logger.info(
                        f"Rolled over {rolled_count} items from {from_version} to {to_version}"
                    )
                except Exception as e:
                    result["error"] = f"Rollover failed: {str(e)}"

        else:
            result["error"] = f"Unknown action type: {action_type}"

        return result

    def _update_state_after_action(
        self,
        action: dict,
        result: dict,
        state: SimulationState,
    ) -> None:
        """Update simulation state after action execution."""
        action_type = action.get("type", "unknown")
        ticket_key = action.get("ticket_key")
        scenario_id = action.get("scenario_id")
        agent_id = action.get("agent_id") or result.get("agent")

        # Skip if action failed
        if result.get("error") or result.get("skipped"):
            return

        # Skip if Jira operation failed (prevents state drift)
        # Default to True for backwards compatibility with actions that don't set this flag
        if not result.get("jira_success", True):
            logger.warning(
                f"State update SKIPPED for {action_type} on {ticket_key}: "
                f"Jira operation failed. State remains unchanged to prevent drift."
            )
            return

        # Get scenario
        scenario = None
        if scenario_id and scenario_id in state.active_scenarios:
            scenario = state.active_scenarios[scenario_id]
        elif ticket_key:
            scenario = state.get_scenario_by_ticket(ticket_key)

        # Record the action in history
        if agent_id:
            agent_persona = self.personas.get("agents", {}).get(agent_id, {})
            state.record_action(
                agent_id=agent_id,
                agent_name=agent_persona.get("display_name", agent_id),
                action_type=action_type,
                ticket_key=ticket_key,
                scenario_id=scenario.scenario_id if scenario else None,
                details=action.get("details"),
            )

        # Update scenario phase based on action
        if scenario:
            phase_updates = {
                "pick_up_task": ScenarioPhase.IN_PROGRESS,
                "progress_to_review": ScenarioPhase.IN_REVIEW,
                "complete_review": ScenarioPhase.IN_TESTING,
                "qa_approve": ScenarioPhase.COMPLETED,
                "inject_blocker": ScenarioPhase.BLOCKED,
                "discuss_blocker": ScenarioPhase.BLOCKER_DISCUSSED,
                "resolve_blocker": ScenarioPhase.IN_PROGRESS,
                "qa_reject": ScenarioPhase.REJECTED,
                "acknowledge_rejection": ScenarioPhase.FIXING,
                "complete_fix": ScenarioPhase.RE_REVIEW,
                "verify_fix": ScenarioPhase.COMPLETED,
                "identify_dependency": ScenarioPhase.WAITING_ON_DEPENDENCY,
                "resolve_dependency": ScenarioPhase.IN_PROGRESS,
            }

            new_phase = phase_updates.get(action_type)
            if new_phase:
                scenario.advance_to_phase(new_phase)

                # Assign QA when entering testing phase
                if new_phase in [ScenarioPhase.IN_TESTING, ScenarioPhase.RE_TESTING]:
                    dev_team = self._get_team_for_agent(scenario.assigned_agent)
                    if dev_team:
                        qa_agent_id = self._get_qa_for_team(dev_team)
                        if qa_agent_id:
                            scenario.assign_qa(qa_agent_id)
                            qa_state = state.get_agent_state(qa_agent_id)
                            qa_state.assign_ticket(ticket_key)
                            logger.info(f"Assigned QA {qa_agent_id} to test {ticket_key}")

                # Unassign QA when testing is complete
                elif new_phase == ScenarioPhase.COMPLETED and scenario.qa_agent:
                    qa_state = state.get_agent_state(scenario.qa_agent)
                    qa_state.unassign_ticket(ticket_key)
                    scenario.unassign_qa()

            # Advance script if action was from a script
            if action.get("from_script") or scenario.action_script:
                next_action = scenario.get_next_script_action()
                if next_action and next_action.type == action_type:
                    scenario.advance_script()
                    progress = scenario.get_script_progress()
                    logger.debug(
                        f"Script advanced for {ticket_key}: {progress[0]}/{progress[1]} actions complete"
                    )

            # Special handling
            if action_type == "inject_blocker":
                scenario.inject_blocker(
                    action.get("details", "Unknown blocker"),
                    agent_id or "unknown",
                )
            elif action_type == "qa_reject":
                scenario.inject_rejection(
                    action.get("details", "QA issue found"),
                    agent_id or "unknown",
                )
                # Unassign QA when rejecting (ticket goes back to developer)
                if scenario.qa_agent and ticket_key:
                    qa_state = state.get_agent_state(scenario.qa_agent)
                    qa_state.unassign_ticket(ticket_key)
                    scenario.unassign_qa()
            elif action_type == "identify_dependency":
                scenario.inject_dependency(
                    action.get("dependency_ticket", ""),
                    action.get("dependency_team", "beta"),
                    agent_id or "unknown",
                )

            # Complete scenario if done
            if new_phase == ScenarioPhase.COMPLETED:
                state.complete_scenario(scenario.scenario_id)

        # Update agent state
        if agent_id:
            agent_state = state.get_agent_state(agent_id)
            if action_type == "pick_up_task" and ticket_key:
                agent_state.assign_ticket(ticket_key)
            elif action_type in ["qa_approve", "verify_fix"] and ticket_key:
                # Unassign completed tickets
                if scenario and scenario.assigned_agent:
                    dev_state = state.get_agent_state(scenario.assigned_agent)
                    dev_state.unassign_ticket(ticket_key)

    def _create_scenario_for_ticket(
        self,
        ticket_key: str,
        agent_id: str,
        state: SimulationState,
        scenario_type: str = "normal_flow",
    ) -> ActiveScenario:
        """
        Create a new scenario for a ticket being picked up.

        Generates an action script using the pathfinder based on current
        ticket status and scenario type.
        """
        # Try to get ticket info from Jira for complexity and status
        complexity = TicketComplexity.STORY  # Default
        current_status = "To Do"  # Default

        try:
            issue = self.jira.get_issue(ticket_key)
            issue_type = issue.fields.issuetype.name
            complexity = ISSUE_TYPE_TO_COMPLEXITY.get(issue_type, TicketComplexity.STORY)
            current_status = issue.fields.status.name if issue.fields.status else "To Do"
        except Exception as e:
            logger.warning(f"Failed to get issue details for {ticket_key}: {e}")

        scenario = ActiveScenario.create_normal_flow(
            ticket_key=ticket_key,
            complexity=complexity,
            assigned_agent=agent_id,
        )

        # Generate action script using pathfinder
        script_actions = self.pathfinder.generate_scenario_script(
            scenario_type=scenario_type,
            current_status=current_status,
            complexity=complexity.value,
        )

        # Set the script on the scenario
        if script_actions:
            scenario.set_script(script_actions)
            logger.info(
                f"Generated {len(script_actions)}-action script for {ticket_key}: "
                f"{[a.get('type') for a in script_actions]}"
            )

        state.add_scenario(scenario)

        # Assign ticket to agent's workload
        state.get_agent_state(agent_id).assign_ticket(ticket_key)

        return scenario

    def _generate_blocker_reason(self) -> str:
        """Generate a realistic blocker reason."""
        reasons = [
            "Waiting on API clarification from backend team",
            "Environment issue - can't reproduce locally",
            "Missing test data for edge cases",
            "Unclear acceptance criteria - need PM input",
            "Dependency on infrastructure change not yet deployed",
            "Need security review before proceeding",
            "Conflicting requirements with another ticket",
            "Database migration needed first",
        ]
        return random.choice(reasons)

    def _generate_rejection_reason(self) -> str:
        """Generate a realistic QA rejection reason."""
        reasons = [
            "Edge case not handled - see repro steps",
            "Regression in existing functionality",
            "Missing error handling for invalid input",
            "UI doesn't match design specs",
            "Performance issue under load",
            "Accessibility requirement not met",
            "Data validation missing",
            "Inconsistent behavior across browsers",
        ]
        return random.choice(reasons)

    def _generate_urgency_context(self) -> str:
        """Generate a realistic urgency context for scope creep."""
        contexts = [
            "Customer escalation - production issue affecting key client",
            "Security vulnerability discovered - needs immediate patch",
            "Regulatory compliance deadline approaching",
            "Critical bug found during demo to stakeholders",
            "Competitive pressure - need to match competitor feature",
            "Data integrity issue reported by support",
            "Integration partner API change requires update",
        ]
        return random.choice(contexts)
