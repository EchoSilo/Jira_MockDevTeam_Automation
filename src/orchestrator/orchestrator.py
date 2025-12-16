"""
Scenario Orchestrator - main coordination for simulation ticks.

Combines the Analyzer, Planner, and Crews to execute simulation ticks.
"""

import random
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from ..services.jira_client import JiraClient
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
)
from .analyzer import ScenarioAnalyzer
from .planner import ScenarioPlanner

if TYPE_CHECKING:
    from ..logging import AsyncLogWriter


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

        # Create shared JiraTools
        self.jira_tools = JiraTools(jira_client)

        # Create LLM config for crews
        routine = settings.get("llm", {}).get("routine_model", "claude-3-haiku-20240307")
        complex_m = settings.get("llm", {}).get("complex_model", "claude-sonnet-4-20250514")
        self.llm_config = {
            "routine_model": routine,
            "complex_model": complex_m,
        }

        # Initialize components
        self.analyzer = ScenarioAnalyzer(jira_client, personas, settings)
        self.planner = ScenarioPlanner(llm_service, settings)

        # Initialize crews
        self.lifecycle_crew = TicketLifecycleCrew(personas, self.jira_tools, self.llm_config)
        self.blocker_crew = BlockerCrew(personas, self.jira_tools, self.llm_config)
        self.rework_crew = ReworkCrew(personas, self.jira_tools, self.llm_config)
        self.scope_creep_crew = ScopeCreepCrew(personas, self.jira_tools, self.llm_config)
        self.dependency_crew = DependencyCrew(personas, self.jira_tools, self.llm_config)

    def _log_event(
        self,
        phase: str,
        **kwargs,
    ) -> None:
        """Log an orchestrator event if log_writer is available."""
        if self.log_writer:
            self.log_writer.log_orchestrator_event(phase=phase, **kwargs)

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
            # Phase 1: Analyze
            analysis = self.analyzer.analyze(state)
            results["analysis"] = {
                "opportunities_found": len(analysis.get("opportunities", [])),
                "metrics": analysis.get("metrics", {}),
            }

            # Log analysis phase
            self._log_event(
                "analyze",
                intensity=intensity,
                analysis_summary=results["analysis"],
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
                    action_result = await self._execute_action(action, state)
                    results["actions"].append(action_result)

                    # Log action execution
                    self._log_event(
                        "action_result",
                        action_type=action.get("type"),
                        action_result=action_result,
                        ticket_key=action.get("ticket_key"),
                        scenario_id=action.get("scenario_id"),
                        agent_id=action.get("agent_id"),
                    )

                    # Phase 4: Update state
                    self._update_state_after_action(action, action_result, state)

                except Exception as e:
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

        return results

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
                result.update(
                    self.lifecycle_crew.pick_up_from_backlog(scenario, agent_id)
                )

        elif action_type == "progress_to_review":
            if scenario:
                result.update(self.lifecycle_crew.progress_to_review(scenario))

        elif action_type == "complete_review":
            if scenario:
                tech_lead_id = action.get("tech_lead_id")
                result.update(
                    self.lifecycle_crew.complete_code_review(scenario, tech_lead_id)
                )

        elif action_type == "qa_approve":
            if scenario:
                qa_id = action.get("qa_id")
                result.update(self.lifecycle_crew.qa_approve(scenario, qa_id))

        elif action_type == "add_progress_comment":
            if scenario:
                result.update(self.lifecycle_crew.add_progress_comment(scenario))

        # ========== Blocker Actions ==========
        elif action_type == "inject_blocker":
            if scenario:
                reason = details or self._generate_blocker_reason()
                result.update(self.blocker_crew.inject_blocker(scenario, reason))

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
    ) -> ActiveScenario:
        """Create a new scenario for a ticket being picked up."""
        # Try to get ticket info from Jira for complexity
        complexity = TicketComplexity.STORY  # Default

        try:
            issue = self.jira.get_issue(ticket_key)
            issue_type = issue.fields.issuetype.name
            complexity = ISSUE_TYPE_TO_COMPLEXITY.get(issue_type, TicketComplexity.STORY)
        except Exception:
            pass

        scenario = ActiveScenario.create_normal_flow(
            ticket_key=ticket_key,
            complexity=complexity,
            assigned_agent=agent_id,
        )

        state.add_scenario(scenario)

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
