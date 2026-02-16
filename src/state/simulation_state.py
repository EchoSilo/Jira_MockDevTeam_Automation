"""
Simulation state management.
Persists state between runs to maintain continuity and scenario progression.

This module provides backwards-compatible state management while supporting
the new scenario-driven simulation model.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import pendulum

logger = logging.getLogger(__name__)

from .models import (
    SimulationState,
    ActiveScenario,
    AgentState,
    ScenarioType,
    ScenarioPhase,
    TicketComplexity,
    ISSUE_TYPE_TO_COMPLEXITY,
)


def load_state(path: str = "data/state.json") -> SimulationState:
    """
    Load state from disk, or create new if doesn't exist.
    Handles migration from old state format if needed.
    """
    state_path = Path(path)

    if state_path.exists():
        with open(state_path, "r") as f:
            data = json.load(f)

        # Check if this is old format (has 'active_tickets' instead of 'active_scenarios')
        if "active_tickets" in data and "active_scenarios" not in data:
            state = _migrate_old_state(data)
        else:
            state = SimulationState.model_validate(data)

        # Migrate testing scenarios to assign QA agents if missing
        _assign_qa_to_testing_scenarios(state)

        # Note: We intentionally do NOT call sync_agent_workloads() here.
        # Agent workloads are set explicitly by sync-reset from sprint tickets,
        # while active_scenarios contains ALL active Jira tickets (for scenario tracking).
        # Calling sync_agent_workloads would overwrite sprint-filtered workloads.
        return state

    return SimulationState()


def _assign_qa_to_testing_scenarios(state: SimulationState) -> None:
    """Assign QA agents to testing scenarios that don't have one.

    This handles migration from before QA assignment tracking was added.
    """
    import yaml

    # Load personas to get QA agents per team
    personas_path = Path("config/personas.yaml")
    if not personas_path.exists():
        return

    with open(personas_path, "r") as f:
        personas = yaml.safe_load(f)

    # Build team -> qa_agent mapping
    team_qa = {}
    for agent_id, config in personas.get("agents", {}).items():
        if config.get("role") == "qa":
            team = config.get("team")
            if team:
                team_qa[team] = agent_id

    # Also build agent -> team mapping
    agent_team = {}
    for agent_id, config in personas.get("agents", {}).items():
        team = config.get("team")
        if team:
            agent_team[agent_id] = team

    # Assign QA to testing scenarios without one
    for scenario in state.active_scenarios.values():
        if scenario.current_phase in [ScenarioPhase.IN_TESTING, ScenarioPhase.RE_TESTING]:
            if not scenario.qa_agent and scenario.assigned_agent:
                team = agent_team.get(scenario.assigned_agent)
                if team and team in team_qa:
                    qa_agent_id = team_qa[team]
                    scenario.assign_qa(qa_agent_id)
                    logger.info(
                        f"Migrated: Assigned QA {qa_agent_id} to testing scenario {scenario.ticket_key}"
                    )


def save_state(state: SimulationState, path: str = "data/state.json") -> None:
    """Save state to disk."""
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    with open(state_path, "w") as f:
        json.dump(state.model_dump(mode="json"), f, indent=2, default=str)


def _migrate_old_state(old_data: dict) -> SimulationState:
    """
    Migrate from old state format to new scenario-based format.
    Preserves agent states and converts active_tickets to active_scenarios.
    """
    new_state = SimulationState()

    # Migrate basic fields
    new_state.last_run = (
        datetime.fromisoformat(old_data["last_run"])
        if old_data.get("last_run")
        else None
    )
    new_state.simulation_day = old_data.get("simulation_day", 1)

    # Migrate sprint state
    if "current_sprint" in old_data:
        old_sprint = old_data["current_sprint"]
        new_state.sprint.sprint_number = int(old_sprint.get("name", "Sprint 1").split()[-1])
        new_state.sprint.sprint_day = old_sprint.get("day", 1)
        new_state.sprint.total_days = old_sprint.get("total_days", 14)

    # Migrate agent states
    for agent_id, old_agent in old_data.get("agents", {}).items():
        agent_state = AgentState(agent_id=agent_id)
        agent_state.last_action = (
            datetime.fromisoformat(old_agent["last_action"])
            if old_agent.get("last_action")
            else None
        )
        agent_state.actions_today = old_agent.get("actions_today", 0)
        agent_state.assigned_tickets = old_agent.get("assigned_tickets", [])
        agent_state.current_workload = len(agent_state.assigned_tickets)
        agent_state.is_overloaded = agent_state.current_workload >= 5
        new_state.agents[agent_id] = agent_state

    # Convert active_tickets to active_scenarios
    for ticket_key, old_ticket in old_data.get("active_tickets", {}).items():
        # Skip completed tickets
        if old_ticket.get("status") in ["Done", "Closed"]:
            continue

        # Create scenario from old ticket state
        scenario = _convert_ticket_to_scenario(ticket_key, old_ticket)
        if scenario:
            new_state.active_scenarios[scenario.scenario_id] = scenario

    # Migrate recent actions (convert format)
    for old_action in old_data.get("recent_actions", [])[-20:]:
        new_state.record_action(
            agent_id=old_action.get("agent_id", "unknown"),
            agent_name=old_action.get("agent_id", "Unknown"),
            action_type=old_action.get("action", "unknown"),
            ticket_key=old_action.get("ticket"),
        )

    return new_state


def _convert_ticket_to_scenario(ticket_key: str, old_ticket: dict) -> Optional[ActiveScenario]:
    """Convert an old-format ticket to a new scenario."""
    status = old_ticket.get("status", "To Do").title()

    # Map old status to scenario phase (includes .title() variants for case normalization)
    status_to_phase = {
        "To Do": ScenarioPhase.BACKLOG,
        "Backlog": ScenarioPhase.BACKLOG,
        "In Progress": ScenarioPhase.IN_PROGRESS,
        "Code Review": ScenarioPhase.IN_REVIEW,
        "In Review": ScenarioPhase.IN_REVIEW,
        "Ready For Qa": ScenarioPhase.IN_TESTING,  # .title() variant of "READY FOR QA"
        "Testing": ScenarioPhase.IN_TESTING,
        "QA": ScenarioPhase.IN_TESTING,
        "Qa": ScenarioPhase.IN_TESTING,  # .title() variant of "QA"
        "Blocked": ScenarioPhase.BLOCKED,
        "Done": ScenarioPhase.COMPLETED,
        "Closed": ScenarioPhase.COMPLETED,
    }

    phase = status_to_phase.get(status)
    if not phase:
        return None

    # Determine scenario type from old state
    scenario_type = ScenarioType.NORMAL_FLOW
    if old_ticket.get("blocked"):
        scenario_type = ScenarioType.BLOCKER

    # Default to STORY complexity
    complexity = TicketComplexity.STORY

    # Calculate timeline based on when ticket started
    started = (
        datetime.fromisoformat(old_ticket["started"])
        if old_ticket.get("started")
        else pendulum.now("UTC") - timedelta(days=2)
    )

    # Estimate target completion
    target_completion = started + timedelta(days=5)  # Default 5 days for story

    now = pendulum.now("UTC")

    return ActiveScenario(
        ticket_key=ticket_key,
        scenario_type=scenario_type,
        complexity=complexity,
        started=started,
        target_completion=target_completion,
        current_phase=phase,
        phase_started=now - timedelta(hours=12),  # Assume been in phase for a bit
        phase_target_end=now + timedelta(hours=12),  # Ready to advance soon
        assigned_agent=old_ticket.get("assigned_to"),
        involved_agents=[old_ticket["assigned_to"]] if old_ticket.get("assigned_to") else [],
    )


# ============ Utility Functions ============

def sync_state_with_jira(state: SimulationState, jira_client, personas: dict) -> SimulationState:
    """
    Sync simulation state with actual Jira board state.
    Creates scenarios for tickets not yet tracked.
    Updates phases for tickets that have changed status.

    Note: Sprint state (sprint_number, sprint_day) is handled via inject_jira_sprint()
    at the start of each tick, not in this function. This function only syncs scenarios.
    """
    # Get all active tickets from Jira
    try:
        jira_tickets = jira_client.get_all_active_issues()
    except Exception as e:
        logger.error(f"Failed to sync state with Jira: {e}")
        return state

    tracked_tickets = {s.ticket_key for s in state.active_scenarios.values()}

    for ticket in jira_tickets:
        ticket_key = ticket.key
        status = ticket.fields.status.name.title()
        issue_type = ticket.fields.issuetype.name
        assignee = ticket.fields.assignee

        # Skip if already completed
        if status in ["Done", "Closed", "Resolved"]:
            # If we were tracking it, mark complete
            scenario = state.get_scenario_by_ticket(ticket_key)
            if scenario:
                state.complete_scenario(scenario.scenario_id)
            continue

        # If not tracked, create a new scenario
        if ticket_key not in tracked_tickets:
            complexity = ISSUE_TYPE_TO_COMPLEXITY.get(issue_type, TicketComplexity.STORY)
            assigned_agent = _find_agent_by_jira_account(
                personas,
                assignee.accountId if assignee else None
            )

            scenario = ActiveScenario.create_normal_flow(
                ticket_key=ticket_key,
                complexity=complexity,
                assigned_agent=assigned_agent,
            )

            # Set phase based on current Jira status (includes .title() variants for case normalization)
            jira_status_to_phase = {
                "To Do": ScenarioPhase.BACKLOG,
                "Backlog": ScenarioPhase.BACKLOG,
                "Selected For Development": ScenarioPhase.ASSIGNED,  # .title() variant
                "In Progress": ScenarioPhase.IN_PROGRESS,
                "Code Review": ScenarioPhase.IN_REVIEW,
                "In Review": ScenarioPhase.IN_REVIEW,
                "Ready For Qa": ScenarioPhase.IN_TESTING,  # .title() variant of "READY FOR QA"
                "Testing": ScenarioPhase.IN_TESTING,
                "QA": ScenarioPhase.IN_TESTING,
                "Qa": ScenarioPhase.IN_TESTING,  # .title() variant of "QA"
                "Done": ScenarioPhase.COMPLETED,
                "Closed": ScenarioPhase.COMPLETED,
            }
            if status in jira_status_to_phase:
                scenario.current_phase = jira_status_to_phase[status]

            state.add_scenario(scenario)

            # Update agent assignment
            if assigned_agent:
                state.get_agent_state(assigned_agent).assign_ticket(ticket_key)

    return state


def _find_agent_by_jira_account(personas: dict, account_id: Optional[str]) -> Optional[str]:
    """
    Find agent_id by Jira account ID.
    """
    if not account_id:
        return None
    for agent_id, agent_config in personas.get("agents", {}).items():
        if agent_config.get("jira_account_id") == account_id:
            return agent_id
    return None


def validate_state_agent_ids(state: SimulationState, personas: dict) -> SimulationState:
    """
    Validate and clean up agent_ids in state against personas config.

    This prevents runtime errors from invalid agent_ids that may have been
    persisted from previous runs or LLM hallucinations.

    Args:
        state: The simulation state to validate
        personas: The personas config containing valid agent IDs

    Returns:
        The cleaned state with invalid agent_ids removed or replaced
    """
    valid_agent_ids = set(personas.get("agents", {}).keys())

    # Clean up active scenarios
    scenarios_to_clean = []
    for scenario_id, scenario in state.active_scenarios.items():
        needs_cleaning = False

        # Check assigned_agent
        if scenario.assigned_agent and scenario.assigned_agent not in valid_agent_ids:
            # Try to find a valid agent from actions_taken
            valid_agent = None
            for action in scenario.actions_taken:
                if action.get("agent_id") in valid_agent_ids:
                    valid_agent = action.get("agent_id")
                    break

            if valid_agent:
                scenario.assigned_agent = valid_agent
            else:
                scenario.assigned_agent = None
            needs_cleaning = True

        # Clean involved_agents list
        original_involved = scenario.involved_agents.copy()
        scenario.involved_agents = [
            a for a in scenario.involved_agents if a in valid_agent_ids
        ]
        if scenario.involved_agents != original_involved:
            needs_cleaning = True

        if needs_cleaning:
            scenarios_to_clean.append(scenario_id)

    # Clean up agent states - remove any with invalid IDs
    invalid_agents = [
        agent_id for agent_id in state.agents.keys()
        if agent_id not in valid_agent_ids
    ]
    for agent_id in invalid_agents:
        del state.agents[agent_id]

    return state


def get_scenario_opportunities(state: SimulationState) -> list[dict]:
    """
    Analyze state and return opportunities for scenario actions.
    Used by the rules-based analyzer.
    """
    opportunities = []

    # Check for scenarios ready to advance
    ready_scenarios = state.get_scenarios_ready_to_advance()
    for scenario in ready_scenarios:
        opportunities.append({
            "type": "phase_advancement",
            "scenario_id": scenario.scenario_id,
            "ticket_key": scenario.ticket_key,
            "current_phase": scenario.current_phase.value,
            "description": f"{scenario.ticket_key} ready to advance from {scenario.current_phase.value}",
        })

    # Check for overdue scenarios
    for scenario in state.active_scenarios.values():
        if scenario.is_overdue():
            opportunities.append({
                "type": "overdue_scenario",
                "scenario_id": scenario.scenario_id,
                "ticket_key": scenario.ticket_key,
                "description": f"{scenario.ticket_key} is overdue (started {scenario.get_total_cycle_days():.1f} days ago)",
            })

    # Check for overloaded agents
    for agent_id, agent in state.agents.items():
        if agent.is_overloaded:
            opportunities.append({
                "type": "agent_overloaded",
                "agent_id": agent_id,
                "workload": agent.current_workload,
                "description": f"Agent {agent_id} is overloaded with {agent.current_workload} tickets",
            })

    # Check scenario distribution for balance
    percentages = state.scenario_distribution.get_percentages()
    if percentages.get(ScenarioType.BLOCKER.value, 0) < 0.10:
        opportunities.append({
            "type": "low_blocker_rate",
            "description": "Blocker scenarios underrepresented - consider injecting one",
        })
    if percentages.get(ScenarioType.REWORK.value, 0) < 0.10:
        opportunities.append({
            "type": "low_rework_rate",
            "description": "Rework scenarios underrepresented - consider a QA rejection",
        })

    # Check for scope creep opportunity mid-sprint
    if state.sprint.is_mid_sprint():
        scope_creep_count = state.scenario_distribution.scope_creep
        if scope_creep_count < 2:  # Max 2 per sprint
            opportunities.append({
                "type": "scope_creep_opportunity",
                "description": "Mid-sprint - opportunity for scope creep story",
            })

    return opportunities
