"""
FastAPI application for the Jira Team Simulator.
Exposes /trigger endpoint for n8n to call.

n8n is a dumb trigger only - all logic lives here.
"""

import random
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import yaml

from .state import load_state, save_state, SimulationState
from .services import JiraClient, LLMService
from .orchestrator import Orchestrator


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
    app.state.jira = JiraClient()
    app.state.llm = LLMService()
    app.state.orchestrator = Orchestrator(
        settings=settings,
        personas=personas,
        templates=templates,
        jira_client=app.state.jira,
        llm_service=app.state.llm,
    )
    print("Jira Team Simulator started")
    yield
    # Shutdown
    print("Jira Team Simulator shutting down")


app = FastAPI(
    title="Jira Team Simulator",
    description="Simulates realistic development team activity in Jira",
    version="1.0.0",
    lifespan=lifespan,
)


class TriggerResponse(BaseModel):
    """Response from trigger endpoint."""
    success: bool
    actions_taken: int
    intensity: str
    details: list[dict]
    simulation_day: int
    sprint: str
    timestamp: str


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
    are made internally by the simulator.
    """
    try:
        # Load current state
        state = load_state()

        # Check if new day - reset counters and advance sprint
        if state.is_new_day():
            state.reset_daily_counters()
            state.advance_sprint_day()

        # Determine intensity randomly
        intensity = determine_intensity()

        # Run the orchestrator
        results = await app.state.orchestrator.run_tick(
            state=state,
            intensity=intensity,
        )

        # Save updated state
        save_state(state)

        return TriggerResponse(
            success=True,
            actions_taken=len(results),
            intensity=intensity,
            details=results,
            simulation_day=state.simulation_day,
            sprint=state.current_sprint.name,
            timestamp=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/state")
async def get_state():
    """Get current simulation state (for debugging)."""
    state = load_state()
    return state.model_dump(mode="json")


@app.post("/reset")
async def reset_state():
    """Reset simulation state (for testing)."""
    state = SimulationState()
    save_state(state)
    return {"message": "State reset successfully"}


@app.get("/agents")
async def list_agents():
    """List configured agents."""
    agents = []
    for agent_id, config in app.state.personas.get("agents", {}).items():
        agents.append({
            "id": agent_id,
            "name": config.get("display_name"),
            "team": config.get("team"),
            "role": config.get("role"),
        })
    return {"agents": agents}
