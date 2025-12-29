"""
FastAPI application for the Jira Team Simulator.
Exposes /trigger endpoint for n8n to call.

n8n is a dumb trigger only - all logic lives here.

This version uses the scenario-driven CrewAI orchestration system.
"""

import logging
import random
import time
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()  # Load .env file before other imports

from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yaml

from .state import load_state, save_state, SimulationState, sync_state_with_jira, validate_state_agent_ids
from .services import JiraClient, LLMService
from .orchestrator import ScenarioOrchestrator
from .logging import AsyncLogWriter, LoggedLLMService, LoggedJiraClient, logs_router


# ============ Caching for Performance ============
# These caches prevent repeated expensive operations during dashboard polling

class CachedHealthCheck:
    """Cache Jira connection status to avoid repeated API calls."""

    def __init__(self, ttl_seconds: int = 60):
        self.ttl = ttl_seconds
        self._jira_connected: bool = False
        self._last_check: float = 0
        self._lock = threading.Lock()

    def check(self, jira_client: JiraClient) -> bool:
        """Check Jira connection, using cache if fresh."""
        now = time.time()
        with self._lock:
            if now - self._last_check < self.ttl:
                return self._jira_connected

            # Cache expired, do actual check
            try:
                jira_client.get_current_user()
                self._jira_connected = True
            except Exception:
                self._jira_connected = False

            self._last_check = now
            return self._jira_connected

    def invalidate(self):
        """Force next check to actually call Jira."""
        with self._lock:
            self._last_check = 0


class CachedState:
    """Cache simulation state to avoid repeated file reads."""

    def __init__(self, ttl_seconds: int = 5):
        self.ttl = ttl_seconds
        self._state: Optional[SimulationState] = None
        self._last_load: float = 0
        self._lock = threading.Lock()

    def get(self) -> SimulationState:
        """Get state, reloading from disk if cache expired."""
        now = time.time()
        with self._lock:
            if self._state is None or now - self._last_load >= self.ttl:
                self._state = load_state()
                self._last_load = now
            return self._state

    def invalidate(self):
        """Force next get() to reload from disk."""
        with self._lock:
            self._state = None
            self._last_load = 0

    def update(self, state: SimulationState):
        """Update cache with new state (call after save_state)."""
        with self._lock:
            self._state = state
            self._last_load = time.time()


# Global caches
_health_cache = CachedHealthCheck(ttl_seconds=60)  # Check Jira every 60s
_state_cache = CachedState(ttl_seconds=5)  # Reload state every 5s


def check_and_handle_expired_sprint(jira_client: JiraClient) -> Optional[dict]:
    """
    Check if the active sprint has expired and handle it.

    Returns:
        dict with sprint action taken, or None if no action needed
    """
    try:
        active_sprint = jira_client.get_active_sprint()
        if not active_sprint:
            logger.info("No active sprint found")
            return None

        end_date_str = active_sprint.get("end_date")
        if not end_date_str:
            return None

        # Parse end date and check if expired
        end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)

        if now > end_date:
            days_overdue = (now - end_date).days
            sprint_name = active_sprint.get("name", "Unknown")
            sprint_id = active_sprint.get("id")

            logger.warning(
                f"Sprint '{sprint_name}' (ID: {sprint_id}) expired {days_overdue} days ago. "
                f"End date: {end_date_str}"
            )

            # Close the expired sprint
            if jira_client.complete_sprint(sprint_id):
                logger.info(f"Successfully closed expired sprint '{sprint_name}'")

                # Create a new sprint
                new_sprint_name = f"ESCRUM Sprint {int(sprint_name.split()[-1]) + 1}"
                start_date = now.date()
                end_date_new = start_date + timedelta(days=7)

                new_sprint = jira_client.create_sprint(
                    name=new_sprint_name,
                    start_date=start_date,
                    end_date=end_date_new,
                )

                if new_sprint:
                    # Start the new sprint
                    jira_client.start_sprint(
                        new_sprint["id"],
                        start_date=start_date,
                        end_date=end_date_new,
                    )
                    logger.info(f"Created and started new sprint '{new_sprint_name}'")
                    return {
                        "action": "sprint_rollover",
                        "closed_sprint": sprint_name,
                        "new_sprint": new_sprint_name,
                    }
            else:
                logger.error(f"Failed to close expired sprint '{sprint_name}'")

        return None
    except Exception as e:
        logger.error(f"Error checking sprint expiration: {e}")
        return None


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

# Configure CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:5176",
        "http://localhost:5177",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
        "http://127.0.0.1:5176",
        "http://127.0.0.1:5177",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    jira_url: Optional[str] = None


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check application health and Jira connectivity (cached for performance)."""
    state = _state_cache.get()
    jira_ok = _health_cache.check(app.state.jira)

    return HealthResponse(
        status="healthy" if jira_ok else "degraded",
        jira_connected=jira_ok,
        last_run=state.last_run.isoformat() if state.last_run else None,
        simulation_day=state.simulation_day,
        jira_url=app.state.jira.url if app.state.jira else None,
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

        # Check if new day - advance day (resets counters and advances sprint)
        if state.is_new_day():
            state.advance_day()

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

        # Check for and handle expired sprint
        sprint_action = check_and_handle_expired_sprint(logged_jira)
        if sprint_action:
            logger.info(f"Sprint action taken: {sprint_action}")

        # Validate and clean up any invalid agent_ids in state
        state = validate_state_agent_ids(state, app.state.personas)

        # Create orchestrator with logged services for this tick
        orchestrator = ScenarioOrchestrator(
            jira_client=logged_jira,
            llm_service=logged_llm,
            personas=app.state.personas,
            templates=app.state.templates,
            settings=app.state.settings,
        )

        # Set up comprehensive logging (CrewAI LLM calls, Jira API calls, events)
        orchestrator.set_log_writer(app.state.log_writer)

        # Run the scenario orchestrator
        results = await orchestrator.run_tick(
            state=state,
            intensity=intensity,
        )

        # Save updated state and refresh cache
        save_state(state)
        _state_cache.update(state)
        _health_cache.invalidate()  # Re-check Jira after trigger

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
    """Get current simulation state (cached for dashboard performance)."""
    state = _state_cache.get()
    state_dict = state.model_dump(mode="json")

    # Add real Jira sprint data
    try:
        jira_sprint = app.state.jira.get_active_sprint()
        if jira_sprint:
            # Get sprint issues count
            sprint_issues = app.state.jira.get_sprint_issues(jira_sprint["id"])
            done_count = sum(1 for issue in sprint_issues if issue.fields.status.name.lower() == "done")

            state_dict["jira_sprint"] = {
                "id": jira_sprint["id"],
                "name": jira_sprint["name"],
                "state": jira_sprint["state"],
                "start_date": jira_sprint["start_date"],
                "end_date": jira_sprint["end_date"],
                "total_issues": len(sprint_issues),
                "done_issues": done_count,
            }
    except Exception:
        # Fallback to local sprint data if Jira unavailable
        pass

    return state_dict


@app.get("/api/sprint-data")
async def get_sprint_data():
    """Get comprehensive sprint data from Jira for dashboard charts."""
    try:
        jira = app.state.jira

        # Get active sprint
        active_sprint = jira.get_active_sprint()
        if not active_sprint:
            return {"error": "No active sprint found"}

        sprint_id = active_sprint["id"]
        sprint_issues = jira.get_sprint_issues(sprint_id)

        # Calculate status breakdown from real Jira statuses
        status_counts = {
            "backlog": 0,
            "inProgress": 0,
            "codeReview": 0,
            "testing": 0,
            "done": 0,
        }

        for issue in sprint_issues:
            status = issue.fields.status.name.lower()
            if status in ["to do", "backlog", "open"]:
                status_counts["backlog"] += 1
            elif status in ["in progress", "in development", "blocked"]:
                status_counts["inProgress"] += 1
            elif status in ["code review", "in review", "review"]:
                status_counts["codeReview"] += 1
            elif status in ["ready for qa", "testing", "qa", "in testing"]:
                status_counts["testing"] += 1
            elif status in ["done", "closed", "resolved"]:
                status_counts["done"] += 1
            else:
                # Log unknown status for debugging
                logger.warning(f"Unknown status '{status}' for {issue.key}, defaulting to inProgress")
                status_counts["inProgress"] += 1

        # Calculate burndown data
        from datetime import datetime, timedelta

        start_date = datetime.fromisoformat(active_sprint["start_date"].replace("Z", "+00:00")) if active_sprint["start_date"] else datetime.utcnow()
        end_date = datetime.fromisoformat(active_sprint["end_date"].replace("Z", "+00:00")) if active_sprint["end_date"] else start_date + timedelta(days=7)
        total_days = max(1, (end_date - start_date).days)
        total_items = len(sprint_issues)
        done_items = status_counts["done"]
        remaining = total_items - done_items

        burndown_data = []
        for day in range(total_days + 1):
            day_label = f"Day {day + 1}" if day < total_days else "End"
            ideal = max(0, total_items - (total_items * day / total_days))
            # For past days, show actual; for future, show 0 (unknown)
            current_day = (datetime.utcnow() - start_date.replace(tzinfo=None)).days
            actual = remaining if day <= current_day else 0
            burndown_data.append({
                "day": day_label,
                "ideal": round(ideal),
                "actual": actual if day <= current_day else None,
            })

        # Get velocity from closed sprints
        velocity_data = []
        try:
            closed_sprints = jira._client.sprints(4, state="closed")  # Board ID 4
            for sprint in closed_sprints[-5:]:  # Last 5 sprints
                sprint_num = int(''.join(filter(str.isdigit, sprint.name)) or '0')
                # Count done issues in this sprint
                done_count = 0
                try:
                    sprint_issues_closed = jira.get_sprint_issues(sprint.id)
                    done_count = sum(1 for i in sprint_issues_closed if i.fields.status.name.lower() in ["done", "closed", "resolved"])
                except Exception:
                    pass
                velocity_data.append({
                    "sprintNumber": sprint_num,
                    "sprintName": sprint.name,
                    "completedItems": done_count,
                })
        except Exception:
            pass

        # Add current sprint to velocity if has completed items
        if done_items > 0 or not velocity_data:
            sprint_num = int(''.join(filter(str.isdigit, active_sprint["name"])) or '0')
            velocity_data.append({
                "sprintNumber": sprint_num,
                "sprintName": active_sprint["name"],
                "completedItems": done_items,
            })

        return {
            "statusBreakdown": status_counts,
            "burndownData": burndown_data,
            "velocityData": velocity_data,
            "sprint": active_sprint,
        }

    except Exception as e:
        return {"error": str(e)}


@app.get("/scenarios")
async def get_scenarios():
    """Get active scenarios and their status (cached for dashboard performance)."""
    state = _state_cache.get()
    scenarios = []

    # Compute distribution from active scenarios (not stored totals)
    active_distribution = {
        "normal_flow": 0,
        "blocker": 0,
        "rework": 0,
        "scope_creep": 0,
        "dependency": 0,
    }

    for scenario_id, scenario in state.active_scenarios.items():
        # Compute is_blocked from phase
        is_blocked = scenario.current_phase.value in ["blocked", "blocker_discussed", "waiting_on_dependency"]
        # Compute is_rejected from phase
        is_rejected = scenario.current_phase.value in ["rejected", "fixing", "re_review", "re_testing"]

        scenarios.append({
            "id": scenario_id,
            "ticket_key": scenario.ticket_key,
            "scenario_type": scenario.scenario_type.value,
            "current_phase": scenario.current_phase.value,
            "assigned_agent": scenario.assigned_agent,
            "complexity": scenario.complexity.value,
            "is_blocked": is_blocked,
            "blocker_reason": scenario.blocker_reason,
            "is_rejected": is_rejected,
            "rejection_reason": scenario.rejection_reason,
            "rework_count": scenario.times_rejected,
            "started_at": scenario.started.isoformat() if scenario.started else None,
            "target_end": scenario.target_completion.isoformat() if scenario.target_completion else None,
        })

        # Count by scenario type for active distribution
        scenario_type = scenario.scenario_type.value
        if scenario_type in active_distribution:
            active_distribution[scenario_type] += 1

    return {
        "active_count": len(scenarios),
        "scenarios": scenarios,
        "distribution": active_distribution,
    }


@app.post("/reset")
async def reset_state():
    """Reset simulation state (for testing)."""
    state = SimulationState()
    save_state(state)
    _state_cache.update(state)  # Update cache with new state
    return {"message": "State reset successfully"}


@app.post("/plan-sprint")
async def force_sprint_planning():
    """
    Force sprint planning to run immediately.
    This will have a PM add backlog items to the active sprint.
    """
    try:
        state = load_state()

        # Validate and clean up any invalid agent_ids in state
        state = validate_state_agent_ids(state, app.state.personas)

        # Start a logging session for this action
        session = app.state.log_writer.start_session(
            intensity="normal",
            simulation_day=state.simulation_day,
            sprint_day=state.sprint.sprint_day,
            sprint_number=state.sprint.sprint_number,
        )

        # Create logged services
        logged_jira = LoggedJiraClient(log_writer=app.state.log_writer)
        logged_llm = LoggedLLMService(log_writer=app.state.log_writer)

        # Create orchestrator
        orchestrator = ScenarioOrchestrator(
            jira_client=logged_jira,
            llm_service=logged_llm,
            personas=app.state.personas,
            templates=app.state.templates,
            settings=app.state.settings,
        )
        orchestrator.set_log_writer(app.state.log_writer)

        # Get active sprint
        active_sprint = logged_jira.get_active_sprint()
        if not active_sprint:
            app.state.log_writer.end_session(success=False, error_summary="No active sprint")
            return {"success": False, "error": "No active sprint found"}

        # Get unassigned backlog items (not in any sprint)
        all_issues = logged_jira.get_project_issues(max_results=100)
        unassigned_items = []
        for issue in all_issues:
            sprint_info = logged_jira.get_issue_sprint_info(issue.key)
            # Check if issue is not in any sprint (sprint_info might be None or empty)
            if not sprint_info or not sprint_info.get("current_sprint"):
                # Not in any sprint - available for planning
                unassigned_items.append({
                    "key": issue.key,
                    "summary": issue.fields.summary,
                    "type": issue.fields.issuetype.name,
                    "priority": getattr(issue.fields.priority, 'name', 'Medium') if issue.fields.priority else 'Medium',
                    "status": issue.fields.status.name,
                })

        if not unassigned_items:
            app.state.log_writer.end_session(success=True)
            return {"success": True, "message": "No unassigned items to plan", "items_added": 0}

        # Use alpha PM for planning
        pm_id = "alpha_pm"
        team = "alpha"

        # Execute sprint planning
        result = orchestrator.sprint_planning_crew.plan_current_sprint(
            pm_id=pm_id,
            team=team,
            active_sprint=active_sprint,
            unassigned_items=unassigned_items[:15],  # Limit to 15 items
        )

        # End session
        app.state.log_writer.end_session(
            success=True,
            actions_completed=1,
        )

        return {
            "success": True,
            "sprint": active_sprint.get("name"),
            "unassigned_items_available": len(unassigned_items),
            "result": result,
        }

    except Exception as e:
        if hasattr(app.state, 'log_writer') and app.state.log_writer.get_current_session():
            app.state.log_writer.end_session(success=False, error_summary=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/agents")
async def list_agents():
    """List configured agents and their current state (cached for dashboard performance)."""
    state = _state_cache.get()
    agents = []
    for agent_id, config in app.state.personas.get("agents", {}).items():
        agent_state = state.agents.get(agent_id)
        agents.append({
            "id": agent_id,
            "name": config.get("display_name"),
            "team": config.get("team"),
            "role": config.get("role"),
            "assigned_tickets": agent_state.assigned_tickets if agent_state else [],
            "current_workload": agent_state.current_workload if agent_state else 0,
            "daily_actions": agent_state.actions_today if agent_state else 0,
        })

    # Get schedule config for dashboard context
    schedule_config = app.state.settings.get("schedule", {})

    return {
        "agents": agents,
        "last_run": state.last_run.isoformat() if state.last_run else None,
        "schedule": {
            "days": schedule_config.get("days", [1, 2, 3, 4, 5]),
            "start_hour": schedule_config.get("start_hour", 9),
            "end_hour": schedule_config.get("end_hour", 17),
        }
    }


class ChatRequest(BaseModel):
    """Request model for PM chat."""
    pm_id: str
    message: str


class ChatResponse(BaseModel):
    """Response model for PM chat."""
    pm_id: str
    pm_name: str
    response: str
    tickets_mentioned: list[str] = []


@app.post("/chat", response_model=ChatResponse)
async def chat_with_pm(request: ChatRequest):
    """
    Chat with a PM agent about sprint status, workload, blockers, etc.
    The PM will respond based on current simulation state and their persona.
    """
    pm_id = request.pm_id
    user_message = request.message

    # Get PM config
    pm_config = app.state.personas.get("agents", {}).get(pm_id)
    if not pm_config or pm_config.get("role") != "pm":
        raise HTTPException(status_code=400, detail=f"Invalid PM ID: {pm_id}")

    # Get current state for context (cached for performance)
    state = _state_cache.get()

    # Build context about the current sprint/team
    team = pm_config.get("team") or "unknown"  # Handle null team values
    team_agents = [
        (aid, cfg) for aid, cfg in app.state.personas.get("agents", {}).items()
        if cfg.get("team") == team
    ]

    # Get team workload info
    team_workload = []
    for aid, cfg in team_agents:
        agent_state = state.agents.get(aid)
        if agent_state:
            team_workload.append(f"- {cfg.get('display_name')} ({cfg.get('role')}): {agent_state.current_workload} tickets assigned")

    # Get active scenarios for this team
    team_scenarios = []
    blocked_items = []
    for scenario in state.active_scenarios.values():
        if scenario.assigned_agent and any(scenario.assigned_agent == aid for aid, _ in team_agents):
            phase = scenario.current_phase.value
            team_scenarios.append(f"- {scenario.ticket_key}: {phase}")
            if phase in ["blocked", "blocker_discussed", "waiting_on_dependency"]:
                blocked_items.append(f"{scenario.ticket_key} ({scenario.blocker_reason or 'unknown reason'})")

    # Get recent actions
    recent = [
        f"- {a.agent_name}: {a.action_type} on {a.ticket_key}"
        for a in state.recent_actions[-5:]
        if any(a.agent_id == aid for aid, _ in team_agents)
    ]

    # Build the prompt
    context = f"""Current Sprint: Sprint {state.sprint.sprint_number}, Day {state.sprint.sprint_day} of {state.sprint.total_days}

Team {team.title()} Workload:
{chr(10).join(team_workload) if team_workload else "No workload data"}

Active Items ({len(team_scenarios)} total):
{chr(10).join(team_scenarios[:10]) if team_scenarios else "No active items"}

Blocked Items:
{chr(10).join(blocked_items) if blocked_items else "None"}

Recent Activity:
{chr(10).join(recent) if recent else "No recent activity"}
"""

    prompt = f"""You are {pm_config.get('display_name')}, a Product Manager for Team {team.title()}.

Your persona:
{pm_config.get('persona', 'Professional and collaborative PM.')}

Current project context:
{context}

The user is asking you a question or making a request. Respond naturally as this PM would.
- Be helpful and informative
- Reference specific tickets, team members, or sprint data when relevant
- Keep responses concise (2-4 sentences usually)
- Don't be overly formal or use corporate jargon
- If asked to do something (create story, etc), explain that you can't directly take actions in chat but can discuss

User message: {user_message}

Respond as {pm_config.get('display_name')}:"""

    # Generate response using LLM
    try:
        response = app.state.llm.client.messages.create(
            model=app.state.llm.complex_model,  # Use Sonnet for chat
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        pm_response = response.content[0].text.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM error: {str(e)}")

    # Extract any ticket keys mentioned in the response
    import re
    tickets_mentioned = list(set(re.findall(r'[A-Z]+-\d+', pm_response)))

    return ChatResponse(
        pm_id=pm_id,
        pm_name=pm_config.get('display_name'),
        response=pm_response,
        tickets_mentioned=tickets_mentioned,
    )


# ============ Frontend Static Files ============
# Serve the built React frontend (must be after all API routes)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "dist"

if FRONTEND_DIR.exists():
    # Mount static assets (js, css, images, etc.)
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

    # Serve index.html for root and all non-API routes (SPA routing)
    @app.get("/")
    async def serve_root():
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        """Catch-all route for SPA - serve index.html for client-side routing."""
        # If the path points to an actual file, serve it
        file_path = FRONTEND_DIR / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        # Otherwise serve index.html for client-side routing
        return FileResponse(FRONTEND_DIR / "index.html")
