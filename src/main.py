"""
FastAPI application for the Jira Team Simulator.
Exposes /trigger endpoint for n8n to call.

n8n is a dumb trigger only - all logic lives here.

This version uses the scenario-driven CrewAI orchestration system.
"""

import random
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import yaml

from .state import load_state, save_state, SimulationState, sync_state_with_jira
from .services import JiraClient, LLMService
from .orchestrator import ScenarioOrchestrator
from .logging import AsyncLogWriter, LoggedLLMService, LoggedJiraClient, logs_router


# Load configuration at startup
def load_config():
    with open("config/settings.yaml", "r") as f:
        settings = yaml.safe_load(f)
    with open("config/personas.yaml", "r") as f:
        personas = yaml.safe_load(f)
    with open("config/templates.yaml", "r") as f:
        templates = yaml.safe_load(f)
    return settings, personas, templates


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    # Startup
    settings, personas, templates = load_config()
    app.state.settings = settings
    app.state.personas = personas
    app.state.templates = templates

    # Initialize logging system
    log_config = settings.get("logging", {})
    db_path = log_config.get("db_path", "data/logs.db")
    app.state.log_writer = AsyncLogWriter(db_path=db_path)
    app.state.log_writer.start()

    # Clean up old logs on startup
    retention_days = log_config.get("retention_days", 30)
    try:
        from .logging import LogDatabase
        db = LogDatabase(db_path)
        deleted = db.cleanup_old_logs(retention_days)
        if deleted > 0:
            print(f"Cleaned up {deleted} old log entries")
    except Exception as e:
        print(f"Warning: Log cleanup failed: {e}")

    # Initialize base services (used for health checks etc)
    app.state.jira = JiraClient()
    app.state.llm = LLMService()

    print("Jira Team Simulator started (scenario-driven mode with logging)")
    yield

    # Shutdown
    print("Jira Team Simulator shutting down")
    app.state.log_writer.stop()


app = FastAPI(
    title="Jira Team Simulator",
    description="Simulates realistic development team activity in Jira",
    version="1.0.0",
    lifespan=lifespan,
)

# Include the logs API router
app.include_router(logs_router)


class TriggerResponse(BaseModel):
    """Response from trigger endpoint."""
    success: bool
    actions_taken: int
    actions_planned: int
    intensity: str
    analysis_summary: dict
    planning_reasoning: Optional[str]
    actions: list[dict]
    errors: list[dict]
    active_scenarios: int
    simulation_day: int
    sprint: str
    tick_start: str
    tick_end: str


def determine_intensity() -> str:
    """
    Randomly determine activity intensity for this tick.
    Weighted towards normal activity with occasional light/busy periods.
    """
    # 20% light, 60% normal, 20% busy
    r = random.random()
    if r < 0.20:
        return "light"
    elif r < 0.80:
        return "normal"
    else:
        return "busy"


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    jira_connected: bool
    last_run: Optional[str]
    simulation_day: int


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check application health and Jira connectivity."""
    state = load_state()

    # Test Jira connection
    jira_ok = False
    try:
        app.state.jira.get_current_user()
        jira_ok = True
    except Exception:
        pass

    return HealthResponse(
        status="healthy" if jira_ok else "degraded",
        jira_connected=jira_ok,
        last_run=state.last_run.isoformat() if state.last_run else None,
        simulation_day=state.simulation_day,
    )


@app.post("/trigger", response_model=TriggerResponse)
async def trigger_simulation():
    """
    Main endpoint called by n8n to run one simulation tick.
    Each call simulates a period of team activity.

    n8n just triggers this - all decisions (intensity, who acts, what they do)
    are made internally by the simulator using the scenario-driven approach:
    1. Analyze - detect opportunities from current board state
    2. Plan - LLM decides which scenarios to inject/progress
    3. Execute - CrewAI crews perform the planned actions
    4. Update - state is updated based on results
    """
    # Track session stats for logging
    llm_call_count = 0
    jira_call_count = 0
    total_input_tokens = 0
    total_output_tokens = 0

    try:
        # Load current state
        state = load_state()

        # Check if new day - reset counters and advance sprint
        if state.is_new_day():
            state.reset_daily_counters()
            state.advance_sprint_day()

        # Determine intensity randomly
        intensity = determine_intensity()

        # Start logging session for this tick
        session = app.state.log_writer.start_session(
            intensity=intensity,
            simulation_day=state.simulation_day,
            sprint_day=state.sprint.sprint_day,
            sprint_number=state.sprint.sprint_number,
        )

        # Create logged services for this tick
        logged_jira = LoggedJiraClient(log_writer=app.state.log_writer)
        logged_llm = LoggedLLMService(log_writer=app.state.log_writer)

        # Sync state with actual Jira board using logged client
        try:
            sync_state_with_jira(state, logged_jira)
        except Exception as sync_error:
            print(f"Warning: State sync failed: {sync_error}")

        # Create orchestrator with logged services for this tick
        orchestrator = ScenarioOrchestrator(
            jira_client=logged_jira,
            llm_service=logged_llm,
            personas=app.state.personas,
            templates=app.state.templates,
            settings=app.state.settings,
        )

        # Inject log writer into orchestrator for event logging
        orchestrator.log_writer = app.state.log_writer

        # Run the scenario orchestrator
        results = await orchestrator.run_tick(
            state=state,
            intensity=intensity,
        )

        # Save updated state
        save_state(state)

        # End logging session with stats
        app.state.log_writer.end_session(
            success=len(results.get("errors", [])) == 0,
            llm_calls=results.get("llm_call_count", 0),
            jira_calls=results.get("jira_call_count", 0),
            actions_planned=results.get("planned_actions", 0),
            actions_completed=results.get("actions_completed", 0),
            errors=len(results.get("errors", [])),
            total_input_tokens=results.get("total_input_tokens", 0),
            total_output_tokens=results.get("total_output_tokens", 0),
        )

        return TriggerResponse(
            success=len(results.get("errors", [])) == 0,
            actions_taken=results.get("actions_completed", 0),
            actions_planned=results.get("planned_actions", 0),
            intensity=intensity,
            analysis_summary=results.get("analysis", {}),
            planning_reasoning=results.get("planning_reasoning"),
            actions=results.get("actions", []),
            errors=results.get("errors", []),
            active_scenarios=len(state.active_scenarios),
            simulation_day=state.simulation_day,
            sprint=f"Sprint {state.sprint.sprint_number}",
            tick_start=results.get("tick_start", ""),
            tick_end=results.get("tick_end", ""),
        )

    except Exception as e:
        # End session with error if we have one active
        if hasattr(app.state, 'log_writer') and app.state.log_writer.get_current_session():
            app.state.log_writer.end_session(
                success=False,
                error_summary=str(e),
            )
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/state")
async def get_state():
    """Get current simulation state (for debugging)."""
    state = load_state()
    return state.model_dump(mode="json")


@app.get("/scenarios")
async def get_scenarios():
    """Get active scenarios and their status."""
    state = load_state()
    scenarios = []
    for scenario_id, scenario in state.active_scenarios.items():
        scenarios.append({
            "id": scenario_id,
            "ticket_key": scenario.ticket_key,
            "scenario_type": scenario.scenario_type.value,
            "current_phase": scenario.current_phase.value,
            "assigned_agent": scenario.assigned_agent,
            "complexity": scenario.complexity.value,
            "is_blocked": scenario.is_blocked,
            "blocker_reason": scenario.blocker_reason,
            "is_rejected": scenario.is_rejected,
            "rejection_reason": scenario.rejection_reason,
            "rework_count": scenario.rework_count,
            "started_at": scenario.started_at.isoformat() if scenario.started_at else None,
            "target_end": scenario.target_end.isoformat() if scenario.target_end else None,
        })

    return {
        "active_count": len(scenarios),
        "scenarios": scenarios,
        "distribution": state.scenario_distribution.model_dump() if state.scenario_distribution else {},
    }


@app.post("/reset")
async def reset_state():
    """Reset simulation state (for testing)."""
    state = SimulationState()
    save_state(state)
    return {"message": "State reset successfully"}


@app.get("/agents")
async def list_agents():
    """List configured agents and their current state."""
    state = load_state()
    agents = []
    for agent_id, config in app.state.personas.get("agents", {}).items():
        agent_state = state.agent_states.get(agent_id)
        agents.append({
            "id": agent_id,
            "name": config.get("display_name"),
            "team": config.get("team"),
            "role": config.get("role"),
            "assigned_tickets": agent_state.assigned_tickets if agent_state else [],
            "current_workload": agent_state.current_workload if agent_state else 0,
            "daily_actions": agent_state.daily_action_count if agent_state else 0,
        })
    return {"agents": agents}
