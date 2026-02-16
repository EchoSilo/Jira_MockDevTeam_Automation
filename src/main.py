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
from typing import Optional, Union
from contextlib import asynccontextmanager
from enum import Enum
import pendulum
import asyncio  # For async/sync bridge in TickExecutor callback

logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()  # Load .env file before other imports

from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yaml
import litellm

from .state import load_state, save_state, SimulationState, sync_state_with_jira, validate_state_agent_ids
from .services import JiraClient, LLMService
from .orchestrator import ScenarioOrchestrator
from .logging import AsyncLogWriter, LoggedLLMService, LoggedJiraClient, logs_router
from .time import Clock, RealClock, get_clock, validate_business_hours
from .scheduling import Scheduler
from .scheduling.persistence import ScheduledActionStore
from .scheduling.virtual_clock import VirtualClock
from .orchestrator.tick_executor import TickExecutor
from .planning import SprintPlanner
from .chaos import (
    RandomEventGenerator,
    ScenarioAdapter,
    ConfidenceTracker,
    ChaosConfig,
    EventCatalog,
    PathfindingAdapter,
    DynamicChaosTuner,
)
from .monitoring import HeartbeatMonitor
from .reconciliation import PerTicketCircuitBreaker


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
            except Exception as e:
                logger.warning(f"Jira connectivity check failed: {e}")
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

# Chaos injection components (Phase 4)
_event_generator: Optional[RandomEventGenerator] = None
_scenario_adapter: Optional[ScenarioAdapter] = None
_confidence_tracker: Optional[ConfidenceTracker] = None
_pathfinding_adapter: Optional[PathfindingAdapter] = None

# Performance optimization components (Phase 5)
_heartbeat_monitor: Optional[HeartbeatMonitor] = None
_dynamic_tuner: Optional[DynamicChaosTuner] = None
_per_ticket_breaker: Optional[PerTicketCircuitBreaker] = None


def _build_agent_registry() -> dict:
    """Build agent registry from personas config for chaos adapters."""
    registry = {}
    personas_path = Path("config/personas.yaml")
    if personas_path.exists():
        with open(personas_path) as f:
            personas = yaml.safe_load(f) or {}
        for agent_id, persona in personas.get("agents", {}).items():
            role = persona.get("role", "developer")
            if role not in registry:
                registry[role] = []
            registry[role].append(agent_id)
    return registry


def _initialize_chaos_components(settings: dict, scheduler: Scheduler):
    """Initialize chaos injection components if enabled in config."""
    global _event_generator, _scenario_adapter, _confidence_tracker, _pathfinding_adapter

    # Load chaos config from settings
    chaos_config = ChaosConfig.load_from_settings(settings)

    if not chaos_config.enabled:
        logger.info("Chaos injection disabled in settings")
        return

    # Build agent registry from personas
    agent_registry = _build_agent_registry()

    # Initialize components
    _event_generator = RandomEventGenerator(chaos_config)
    _scenario_adapter = ScenarioAdapter(scheduler)
    _confidence_tracker = ConfidenceTracker(
        threshold=chaos_config.confidence_threshold,
        override_limit=chaos_config.external_override_limit,
    )
    _pathfinding_adapter = PathfindingAdapter(scheduler, None, agent_registry)

    logger.info(f"Chaos injection enabled: base_chance={chaos_config.base_event_chance}")


def _initialize_performance_components(settings: dict):
    """Initialize performance optimization components."""
    global _heartbeat_monitor, _dynamic_tuner, _per_ticket_breaker

    perf_config = settings.get("performance", {})

    # Heartbeat monitor
    hb_config = perf_config.get("heartbeat", {})
    _heartbeat_monitor = HeartbeatMonitor(
        expected_interval_minutes=hb_config.get("expected_interval_minutes", 45),
        threshold_multiplier=hb_config.get("threshold_multiplier", 1.5),
        business_hours=(
            hb_config.get("business_hours_start", 9),
            hb_config.get("business_hours_end", 17),
        ),
    )

    # Dynamic chaos tuner
    ct_config = perf_config.get("chaos_tuning", {})
    if ct_config.get("enabled", True):
        _dynamic_tuner = DynamicChaosTuner(
            alpha=ct_config.get("alpha", 0.2),
            low_threshold=ct_config.get("low_threshold", 0.6),
            high_threshold=ct_config.get("high_threshold", 0.85),
            min_multiplier=ct_config.get("min_multiplier", 0.2),
            max_multiplier=ct_config.get("max_multiplier", 2.0),
        )

    # Per-ticket circuit breaker
    cb_config = perf_config.get("ticket_circuit_breaker", {})
    _per_ticket_breaker = PerTicketCircuitBreaker(
        failure_threshold=cb_config.get("failure_threshold", 3),
        reset_timeout_hours=cb_config.get("reset_timeout_hours", 24),
    )

    logger.info("Performance optimization components initialized")


def _rebuild_agent_workloads_from_jira(
    state: SimulationState,
    jira_client: JiraClient,
    personas: dict,
    sprint_id: Optional[int] = None
) -> None:
    """
    Rebuild agent assigned_tickets from actual Jira assignments.

    Reads issues from Jira and updates agent workloads to match
    the actual assignments, ensuring state reflects Jira reality.

    Args:
        state: SimulationState to update
        jira_client: Jira client for API calls
        personas: Persona configuration for agent lookups
        sprint_id: Optional sprint ID to filter by. If provided, only includes
                   issues in that sprint. If None, includes all active issues.
    """
    from src.state.simulation_state import _find_agent_by_jira_account

    if sprint_id:
        sprint_issues = jira_client.get_sprint_issues(sprint_id)
    else:
        sprint_issues = jira_client.get_all_active_issues()

    for issue in sprint_issues:
        assignee = issue.fields.assignee
        if not assignee:
            continue

        agent_id = _find_agent_by_jira_account(personas, assignee.accountId)
        if agent_id:
            state.get_agent_state(agent_id).assign_ticket(issue.key)


def _sync_planning_horizon_from_jira(
    state: SimulationState,
    jira_client: JiraClient
) -> None:
    """
    Rebuild planning horizon from actual Jira sprints.

    Fetches future sprints from Jira and populates the planning horizon
    to ensure sprint planning reflects Jira reality.

    Args:
        state: SimulationState to update
        jira_client: Jira client for API calls
    """
    from src.planning.models import PlanningHorizon, SprintPlan, SprintPlanStatus

    future_sprints = jira_client.get_future_sprints(max_results=4)

    if not future_sprints:
        return

    horizon = PlanningHorizon()

    for jira_sprint in future_sprints:
        start_date = pendulum.parse(jira_sprint["startDate"]) if jira_sprint.get("startDate") else None
        end_date = pendulum.parse(jira_sprint["endDate"]) if jira_sprint.get("endDate") else None

        sprint_number = 1
        if jira_sprint.get("name"):
            try:
                sprint_number = int(jira_sprint["name"].split()[-1])
            except (ValueError, IndexError):
                pass

        if start_date and end_date:
            plan = SprintPlan(
                sprint_number=sprint_number,
                start_date=start_date,
                end_date=end_date,
                status=SprintPlanStatus.PLANNED,
            )
            horizon.future_sprints.append(plan)

    state.set_planning_horizon(horizon)


def check_and_handle_expired_sprint(
    jira_client: JiraClient,
    state: Optional[SimulationState] = None,
    personas: Optional[dict] = None,
    settings: Optional[dict] = None,
) -> Optional[dict]:
    """
    Check if the active sprint has expired and handle it.

    Delegates to SprintPlanningCrew.rollover_sprint() for the actual rollover,
    which handles: creating new sprint, closing old sprint with issue rollover,
    and starting the new sprint.

    Args:
        jira_client: Jira client for API calls
        state: Optional simulation state to update when sprint rolls over
        personas: Persona configuration from personas.yaml (required for crew)
        settings: Settings configuration from settings.yaml (required for LLM config)

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
        now = pendulum.now("UTC")

        if now > end_date:
            days_overdue = (now - end_date).days
            sprint_name = active_sprint.get("name", "Unknown")
            sprint_id = active_sprint.get("id")

            logger.warning(
                f"Sprint '{sprint_name}' (ID: {sprint_id}) expired {days_overdue} days ago. "
                f"End date: {end_date_str}"
            )

            # Load configs if not provided
            if personas is None or settings is None:
                _settings, _personas, _ = load_config()
                personas = personas or _personas
                settings = settings or _settings

            # Create JiraTools and LLM config for the crew
            from src.tools.jira_tools import JiraTools
            from src.crews.sprint_planning_crew import SprintPlanningCrew

            jira_tools = JiraTools(jira_client)
            llm_config = {
                "routine_model": settings.get("llm", {}).get("routine_model", "haiku"),
                "complex_model": settings.get("llm", {}).get("complex_model", "sonnet"),
            }

            crew = SprintPlanningCrew(personas, jira_tools, llm_config)
            new_sprint_name = f"ESCRUM Sprint {int(sprint_name.split()[-1]) + 1}"

            current_date = pendulum.now("UTC").date()

            result = crew.rollover_sprint(
                pm_id="alpha_pm",
                current_sprint_id=sprint_id,
                current_sprint_name=sprint_name,
                new_sprint_name=new_sprint_name,
                current_date=current_date,
            )

            if result["success"]:
                logger.info(result["result"])

                if state:
                    # Clear sprint scenario (simulation-specific data)
                    state.clear_sprint_scenario()

                    # Re-inject sprint data since Jira's active sprint changed
                    # This ensures derived values (sprint_number, sprint_day) are correct
                    # for the rest of this tick
                    new_active_sprint = jira_client.get_active_sprint()
                    state.sprint.inject_jira_sprint(new_active_sprint, current_time=pendulum.now("UTC"))
                    logger.info(
                        f"Re-injected sprint after rollover: "
                        f"sprint_number={state.sprint.sprint_number}, "
                        f"sprint_day={state.sprint.sprint_day}"
                    )

                return {
                    "action": "sprint_rollover",
                    "closed_sprint": sprint_name,
                    "new_sprint": new_sprint_name,
                    **result,
                }
            else:
                logger.error(result["result"])

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

    # Initialize Scheduler with VirtualClock and SQLite persistence (Phase 3)
    scheduler_config = settings.get("scheduler", {})
    tick_duration = scheduler_config.get("tick_duration_hours", 0.75)
    scheduler_db_path = scheduler_config.get("db_path", "data/scheduler.db")

    store = ScheduledActionStore(db_path=scheduler_db_path)
    virtual_clock = VirtualClock(pendulum.now("UTC"), tick_duration_hours=tick_duration)
    app.state.scheduler = Scheduler(store=store, virtual_clock=virtual_clock)

    # Initialize SprintPlanner (Phase 3)
    app.state.sprint_planner = SprintPlanner(
        jira_client=app.state.jira,
        llm_service=app.state.llm,
        scheduler=app.state.scheduler,
        settings=settings,
    )

    # Initialize chaos components (Phase 4)
    _initialize_chaos_components(settings, app.state.scheduler)

    # Initialize performance components (Phase 5)
    _initialize_performance_components(settings)

    print(f"Scheduler initialized (tick={tick_duration}h, db={scheduler_db_path})")
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


def _format_last_run(dt) -> str | None:
    """Safely format last_run as ISO string with Z suffix."""
    if dt is None:
        return None
    if isinstance(dt, str):
        # Already a string (shouldn't happen with validators, but be defensive)
        return dt if dt.endswith("Z") else f"{dt}Z"
    # Assume it's a datetime/pendulum object
    try:
        iso_str = dt.isoformat()
        return iso_str if iso_str.endswith("Z") else f"{iso_str}Z"
    except Exception as e:
        logger.warning(f"Failed to format last_run: {e}")
        return None

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check application health and Jira connectivity (cached for performance)."""
    state = _state_cache.get()
    jira_ok = _health_cache.check(app.state.jira)

    return HealthResponse(
        status="healthy" if jira_ok else "degraded",
        jira_connected=jira_ok,
        last_run=_format_last_run(state.last_run),
        simulation_day=state.simulation_day,
        jira_url=app.state.jira.url if app.state.jira else None,
    )


@app.post("/trigger", response_model=TriggerResponse, dependencies=[Depends(validate_business_hours)])
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

        # Record tick for heartbeat monitoring (PERF-05)
        results = {}
        if _heartbeat_monitor:
            heartbeat_alert = _heartbeat_monitor.record_tick(pendulum.now("UTC"))
            if heartbeat_alert:
                results["heartbeat_alert"] = {
                    "gap_minutes": heartbeat_alert.gap_minutes,
                    "threshold_minutes": heartbeat_alert.threshold_minutes,
                }

        # Create logged services for this tick (needed early for Jira calls)
        logged_jira = LoggedJiraClient(log_writer=app.state.log_writer)
        logged_llm = LoggedLLMService(log_writer=app.state.log_writer)

        # EARLY: Inject Jira sprint data (source of truth for sprint_number/day)
        # This must happen before any sprint-dependent logic
        previous_sprint_number = state.sprint.sprint_number  # From cached Jira data
        jira_sprint = logged_jira.get_active_sprint()
        state.sprint.inject_jira_sprint(jira_sprint, current_time=pendulum.now("UTC"))

        # Detect sprint transition (e.g., Sprint 7 -> Sprint 8)
        if state.handle_sprint_transition(previous_sprint_number):
            logger.info(
                f"Sprint transition detected: {previous_sprint_number} -> "
                f"{state.sprint.sprint_number}"
            )

        # Check if new day - advance simulation day (resets daily counters only)
        if state.is_new_day():
            state.advance_day()

        # Determine intensity randomly
        intensity = determine_intensity()

        # Start logging session for this tick (sprint values now derived from Jira)
        session = app.state.log_writer.start_session(
            intensity=intensity,
            simulation_day=state.simulation_day,
            sprint_day=state.sprint.sprint_day,
            sprint_number=state.sprint.sprint_number,
        )

        # Sync scenarios with actual Jira board (sprint already injected above)
        try:
            sync_state_with_jira(state, logged_jira, app.state.personas)
        except Exception as sync_error:
            print(f"Warning: State sync failed: {sync_error}")

        # Check for and handle expired sprint (pass state so it can be updated)
        sprint_action = check_and_handle_expired_sprint(
            logged_jira,
            state,
            personas=app.state.personas,
            settings=app.state.settings,
        )
        if sprint_action:
            logger.info(f"Sprint action taken: {sprint_action}")

        # Validate and clean up any invalid agent_ids in state
        state = validate_state_agent_ids(state, app.state.personas)

        # Check if sprint planning needed (PLAN-08)
        # This maintains 2-3 sprint planning horizon
        planning_result = None
        if hasattr(app.state, 'sprint_planner') and app.state.sprint_planner:
            try:
                # Use alpha_pm as default PM for planning
                planning_result = app.state.sprint_planner.check_and_plan(state, "alpha_pm")
                if planning_result:
                    logger.info(f"Sprint planning completed: {planning_result}")
            except Exception as e:
                logger.error(f"Sprint planning failed: {e}")

        # Create orchestrator with logged services for this tick
        clock = RealClock()
        orchestrator = ScenarioOrchestrator(
            jira_client=logged_jira,
            llm_service=logged_llm,
            personas=app.state.personas,
            templates=app.state.templates,
            settings=app.state.settings,
            clock=clock,
        )

        # Set up comprehensive logging (CrewAI LLM calls, Jira API calls, events)
        orchestrator.set_log_writer(app.state.log_writer)

        # Create TickExecutor to run scheduled actions (EXEC-01, EXEC-02)
        tick_executor = TickExecutor(
            scheduler=app.state.scheduler,
            jira_client=logged_jira,
            max_actions_per_tick=4,
            per_ticket_breaker=_per_ticket_breaker,
            pathfinding_adapter=_pathfinding_adapter,
        )

        # Define action executor that bridges sync TickExecutor to async _execute_action
        # Use asyncio.get_event_loop() to run async code from sync context within async endpoint
        def action_executor(action_dict: dict, exec_state) -> dict:
            """Sync wrapper for async orchestrator._execute_action."""
            import concurrent.futures
            import threading

            # Create a new event loop in a separate thread for the async execution
            result = None
            exception = None

            def run_async():
                nonlocal result, exception
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(orchestrator._execute_action(action_dict, exec_state))
                except Exception as e:
                    exception = e
                finally:
                    loop.close()

            thread = threading.Thread(target=run_async)
            thread.start()
            thread.join(timeout=60)  # 60 second timeout

            if exception:
                raise exception
            return result or {}

        # Execute tick via TickExecutor (handles scheduled action execution)
        # Flow: mark overdue -> get due actions -> reconcile -> execute -> advance time
        tick_results = tick_executor.execute_tick(state, action_executor)

        # --- Chaos injection phase (Phase 4) ---
        chaos_metrics = {}
        if _event_generator:
            # Get current context for chaos event generation
            current_tickets = [t.ticket_key for t in state.active_tickets] if hasattr(state, 'active_tickets') else []
            agent_registry = _build_agent_registry()
            flat_agents = [agent for agents in agent_registry.values() for agent in agents]

            # Roll for chaos event
            chaos_event = _event_generator.roll_for_event(current_tickets, flat_agents)

            if chaos_event:
                logger.info(f"Chaos event triggered: {chaos_event.event_type.value} ({chaos_event.event_id})")
                chaos_metrics["event_triggered"] = True
                chaos_metrics["event_type"] = chaos_event.event_type.value
                chaos_metrics["event_id"] = chaos_event.event_id

                # Adapt scenario to event
                if _scenario_adapter:
                    adaptation_result = _scenario_adapter.adapt_to_event(chaos_event)
                    chaos_metrics["adapted_actions"] = len(adaptation_result.actions_adapted)
                    chaos_metrics["inserted_actions"] = len(adaptation_result.actions_inserted)
                    logger.info(
                        f"Scenario adapted: {len(adaptation_result.actions_adapted)} adapted, "
                        f"{len(adaptation_result.actions_inserted)} inserted"
                    )
            else:
                chaos_metrics["event_triggered"] = False

        # --- Confidence tracking ---
        active_scenario = state.get_sprint_scenario() if hasattr(state, 'get_sprint_scenario') else None
        if _confidence_tracker and active_scenario:
            confidence = _confidence_tracker.calculate_confidence(active_scenario)
            chaos_metrics["script_fidelity"] = confidence.script_fidelity
            chaos_metrics["accept_reality"] = confidence.accept_reality
            chaos_metrics["external_overrides"] = confidence.external_overrides
            chaos_metrics["executed_as_planned"] = confidence.executed_as_planned
            chaos_metrics["total_executed"] = confidence.total_events

            if confidence.accept_reality:
                logger.warning(
                    f"Scenario confidence low: fidelity={confidence.script_fidelity:.2f}, "
                    f"overrides={confidence.external_overrides} - accepting reality"
                )

        # --- Dynamic chaos tuning at sprint end (PERF-04) ---
        if _dynamic_tuner and previous_sprint_number != state.sprint.sprint_number:
            # Sprint just ended - adjust chaos based on completion rate
            completion_rate = state.velocity_tracker.get_completion_rate() if hasattr(state, 'velocity_tracker') else 0.7
            tuning_result = _dynamic_tuner.adjust(completion_rate)
            chaos_metrics["tuning"] = {
                "previous_multiplier": tuning_result.previous_multiplier,
                "new_multiplier": tuning_result.new_multiplier,
                "completion_rate": completion_rate,
                "direction": tuning_result.adjustment_direction,
            }
            logger.info(
                f"Chaos tuning: {tuning_result.adjustment_direction} "
                f"({tuning_result.previous_multiplier:.3f} -> {tuning_result.new_multiplier:.3f})"
            )

        # Apply tuned probabilities to event generator
        if _dynamic_tuner and _event_generator:
            # The event generator would need to support adjusted probabilities
            # For now, log the current multiplier
            chaos_metrics["chaos_multiplier"] = _dynamic_tuner.current_multiplier

        # Run the scenario orchestrator (Analyze + Plan ONLY)
        # Execution is handled by TickExecutor above (EXEC-01: single execution path)
        orchestrator_results = await orchestrator.run_tick(
            state=state,
            intensity=intensity,
            skip_execution=True,  # TickExecutor is the SOLE executor
        )

        # Merge results (TickExecutor actions + orchestrator planning + chaos metrics)
        # Note: results already initialized with heartbeat_alert if applicable
        if not results:
            results = {}
        results.update(tick_results)  # Merge tick executor results
        results["analysis"] = orchestrator_results.get("analysis", {})
        results["planning_reasoning"] = orchestrator_results.get("planning_reasoning")
        results["llm_call_count"] = orchestrator_results.get("llm_call_count", 0)
        results["jira_call_count"] = orchestrator_results.get("jira_call_count", 0)
        results["total_input_tokens"] = orchestrator_results.get("total_input_tokens", 0)
        results["total_output_tokens"] = orchestrator_results.get("total_output_tokens", 0)
        results["planned_actions"] = orchestrator_results.get("planned_actions", 0)
        results["chaos"] = chaos_metrics  # Phase 4: Include chaos injection metrics
        results["actions_completed"] = results.get("metrics", {}).get("executed", 0)

        # Schedule planned actions for next tick execution (if any)
        planned_action_dicts = orchestrator_results.get("planned_action_dicts", [])
        if planned_action_dicts and hasattr(app.state, 'scheduler') and app.state.scheduler:
            from .scheduling import ScheduledAction
            current_time = app.state.scheduler.clock.now()
            scheduled_count = 0
            for action_dict in planned_action_dicts:
                ticket_key = action_dict.get("ticket_key") or ""
                # Skip actions without required fields
                if not action_dict.get("type"):
                    logger.warning(f"Skipping action with missing type: {action_dict}")
                    continue
                # Schedule for immediate execution (current tick window)
                try:
                    scheduled_action = ScheduledAction(
                        scheduled_time=current_time,
                        action_type=action_dict.get("type"),
                        agent_id=action_dict.get("agent_id") or "",
                        ticket_key=ticket_key,
                        scenario_id=action_dict.get("scenario_id"),
                        params={"details": action_dict.get("details", "")},
                    )
                    app.state.scheduler.schedule_action(scheduled_action)
                    logger.info(f"Scheduled planned action: {scheduled_action.action_type} for {ticket_key or 'no ticket'}")
                    scheduled_count += 1
                except Exception as e:
                    logger.error(f"Failed to schedule action: {e}")
            results["actions_scheduled"] = scheduled_count

        # Performance metrics (Phase 5)
        results["performance"] = {
            "heartbeat": _heartbeat_monitor.get_status() if _heartbeat_monitor else None,
            "chaos_multiplier": _dynamic_tuner.current_multiplier if _dynamic_tuner else 1.0,
            "unhealthy_tickets": _per_ticket_breaker.get_unhealthy_tickets() if _per_ticket_breaker else [],
        }

        # Note: actions_completed comes from tick_results, not orchestrator
        # since TickExecutor handles execution

        # Add planning result if available
        if planning_result:
            results["sprint_planning"] = planning_result

        # Advance simulation time by tick_duration_hours (SCHED-05)
        if hasattr(app.state, 'scheduler') and app.state.scheduler:
            next_time = app.state.scheduler.advance_tick()
            results["simulation_time_advanced_to"] = next_time.isoformat()
            logger.info(f"Simulation time advanced to {next_time}")

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
    except Exception as e:
        # Fallback to local sprint data if Jira unavailable
        logger.warning(f"Failed to fetch Jira sprint data: {e}")

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

        start_date = datetime.fromisoformat(active_sprint["start_date"].replace("Z", "+00:00")) if active_sprint["start_date"] else pendulum.now("UTC")
        end_date = datetime.fromisoformat(active_sprint["end_date"].replace("Z", "+00:00")) if active_sprint["end_date"] else start_date + timedelta(days=14)
        total_days = max(1, (end_date - start_date).days)
        total_items = len(sprint_issues)
        done_items = status_counts["done"]
        remaining = total_items - done_items

        burndown_data = []
        for day in range(total_days + 1):
            day_label = f"Day {day + 1}" if day < total_days else "End"
            ideal = max(0, total_items - (total_items * day / total_days))
            # For past days, show actual; for future, show 0 (unknown)
            current_day = (pendulum.now("UTC") - start_date.replace(tzinfo=None)).days
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
                except Exception as e:
                    logger.warning(f"Failed to get sprint issues for {sprint.name}: {e}")
                velocity_data.append({
                    "sprintNumber": sprint_num,
                    "sprintName": sprint.name,
                    "completedItems": done_count,
                })
        except Exception as e:
            logger.warning(f"Failed to fetch velocity data: {e}")

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


# =============================================================================
# Assignment Trends API Endpoint
# =============================================================================


class AssignmentTrendDataPoint(BaseModel):
    """Single data point for assignment trends."""
    date: str
    period_start: str
    period_end: str
    assignments_by_agent: dict[str, int]


class AssignmentTrendsResponse(BaseModel):
    """Response for assignment trends endpoint."""
    granularity: str
    sprint_name: Optional[str]
    date_range: dict
    data_points: list[AssignmentTrendDataPoint]
    agents: list[str]
    insights: dict


def aggregate_assignments_to_buckets(
    history: list[dict],
    current_assignments: dict[str, list[str]],
    granularity: str,
    start_date: datetime,
    end_date: datetime,
    all_agents: list[str],
) -> list[AssignmentTrendDataPoint]:
    """
    Aggregate assignment history into time buckets.

    Uses a snapshot approach: for each bucket, calculate how many tickets
    each person had assigned at the end of that period.
    """
    from collections import defaultdict

    # Generate time buckets
    buckets = []
    current = start_date

    if granularity == "daily":
        delta = timedelta(days=1)
        date_format = "%Y-%m-%d"
    elif granularity == "weekly":
        delta = timedelta(weeks=1)
        date_format = "%Y-%m-%d"
    else:  # monthly
        delta = timedelta(days=30)
        date_format = "%Y-%m"

    while current <= end_date:
        bucket_end = min(current + delta, end_date + timedelta(days=1))
        buckets.append((current, bucket_end))
        current = bucket_end

    # Build assignment state timeline from history
    # Start from current state and work backwards
    assignment_counts: dict[str, int] = {}
    for agent in all_agents:
        assignment_counts[agent] = len(current_assignments.get(agent, []))

    # Process history in reverse to build state at each point
    # (history is sorted chronologically, we want reverse)
    history_reversed = list(reversed(history))

    data_points = []
    now = pendulum.now("UTC")

    for bucket_start, bucket_end in reversed(buckets):
        # Adjust assignment counts based on changes that happened after this bucket
        for change in history_reversed:
            try:
                change_time = datetime.fromisoformat(
                    change["timestamp"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                continue

            # If change happened after this bucket, reverse it
            if change_time > bucket_end:
                to_agent = change.get("to_assignee")
                from_agent = change.get("from_assignee")

                # Reverse: undo the assignment change
                if to_agent and to_agent in assignment_counts:
                    assignment_counts[to_agent] = max(0, assignment_counts[to_agent] - 1)
                if from_agent and from_agent in assignment_counts:
                    assignment_counts[from_agent] = assignment_counts.get(from_agent, 0) + 1

        # Record this bucket's state
        if granularity == "daily":
            date_label = bucket_start.strftime("%b %d")
        elif granularity == "weekly":
            date_label = f"Week of {bucket_start.strftime('%b %d')}"
        else:
            date_label = bucket_start.strftime("%B %Y")

        data_points.append(AssignmentTrendDataPoint(
            date=date_label,
            period_start=bucket_start.isoformat(),
            period_end=bucket_end.isoformat(),
            assignments_by_agent={
                agent: assignment_counts.get(agent, 0) for agent in all_agents
            },
        ))

    # Reverse to get chronological order
    return list(reversed(data_points))


@app.get("/api/assignment-trends", response_model=AssignmentTrendsResponse)
async def get_assignment_trends(
    granularity: str = "daily",
    sprint_id: Optional[int] = None,
    days_back: int = 30,
    team: Optional[str] = None,
):
    """
    Get assignment trends data for visualization.

    Args:
        granularity: Time bucket size - "daily", "weekly", or "monthly"
        sprint_id: Optional sprint ID to filter issues by
        days_back: How far back to look (default 30 days)
        team: Optional team filter ("alpha" or "beta")

    Returns:
        AssignmentTrendsResponse with time-bucketed assignment counts per agent
    """
    try:
        jira = app.state.jira
        personas = app.state.personas

        # Validate granularity
        if granularity not in ["daily", "weekly", "monthly"]:
            granularity = "daily"

        # Calculate date range
        end_date = pendulum.now("UTC")
        start_date = end_date - timedelta(days=days_back)

        # Get sprint name if sprint_id provided
        sprint_name = None
        if sprint_id:
            try:
                active_sprint = jira.get_active_sprint()
                if active_sprint and active_sprint.get("id") == sprint_id:
                    sprint_name = active_sprint.get("name")
            except Exception:
                pass

        # Build agent list filtered by team
        all_agents = []
        agent_names_by_team = {}
        for agent_id, config in personas.get("agents", {}).items():
            agent_team = config.get("team")
            display_name = config.get("display_name")
            role = config.get("role")

            # Skip PMs - they don't get ticket assignments
            if role == "pm":
                continue

            # Apply team filter
            if team and agent_team != team:
                continue

            if display_name:
                all_agents.append(display_name)
                agent_names_by_team[display_name] = agent_team

        # Get assignment history from Jira
        history = jira.get_assignment_history(
            sprint_id=sprint_id,
            start_date=start_date,
            end_date=end_date,
            max_issues=200,
        )

        # Get current assignment snapshot
        current_assignments = jira.get_current_assignments_snapshot(
            sprint_id=sprint_id,
        )

        # Filter current assignments to only include our agents
        filtered_assignments = {
            agent: tickets
            for agent, tickets in current_assignments.items()
            if agent in all_agents
        }

        # Aggregate into buckets
        data_points = aggregate_assignments_to_buckets(
            history=history,
            current_assignments=filtered_assignments,
            granularity=granularity,
            start_date=start_date,
            end_date=end_date,
            all_agents=all_agents,
        )

        # Calculate insights
        unassigned_agents = []
        consistently_overloaded = []

        for agent in all_agents:
            # Check if agent has had zero assignments throughout the period
            total_assignments = sum(
                dp.assignments_by_agent.get(agent, 0) for dp in data_points
            )
            if total_assignments == 0:
                unassigned_agents.append(agent)

            # Check if agent is consistently overloaded (5+ tickets average)
            if data_points:
                avg_assignments = total_assignments / len(data_points)
                if avg_assignments >= 5:
                    consistently_overloaded.append(agent)

        return AssignmentTrendsResponse(
            granularity=granularity,
            sprint_name=sprint_name,
            date_range={
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            data_points=data_points,
            agents=sorted(all_agents),
            insights={
                "unassigned_agents": unassigned_agents,
                "consistently_overloaded": consistently_overloaded,
            },
        )

    except Exception as e:
        logger.error(f"Failed to get assignment trends: {e}")
        return AssignmentTrendsResponse(
            granularity=granularity,
            sprint_name=None,
            date_range={"start": "", "end": ""},
            data_points=[],
            agents=[],
            insights={"unassigned_agents": [], "consistently_overloaded": [], "error": str(e)},
        )


# =============================================================================
# Release/Version API Endpoints
# =============================================================================

class VersionInfo(BaseModel):
    """Version information from Jira."""
    id: str
    name: str
    released: bool
    release_date: Optional[str]
    description: Optional[str]
    archived: bool


class VersionsResponse(BaseModel):
    """Response for versions list."""
    versions: list[VersionInfo]
    total: int


class VersionProgress(BaseModel):
    """Progress metrics for a version."""
    version_name: str
    total: int
    done: int
    in_progress: int
    todo: int
    done_percent: float
    in_progress_percent: float


class VersionIssue(BaseModel):
    """Issue assigned to a version."""
    key: str
    summary: str
    issue_type: str
    status: str
    assignee: Optional[str]
    priority: Optional[str]
    parent_key: Optional[str] = None
    parent_summary: Optional[str] = None


class VersionIssuesResponse(BaseModel):
    """Response for version issues."""
    version_name: str
    total: int
    issues_by_type: dict[str, list[VersionIssue]]
    issues: list[VersionIssue]


@app.get("/api/releases/versions", response_model=VersionsResponse)
async def get_versions(
    released: Optional[bool] = None,
    include_archived: bool = False,
):
    """Get all fix versions from Jira."""
    try:
        versions = app.state.jira.get_fix_versions(released=released)

        # Filter archived if not requested
        if not include_archived:
            versions = [v for v in versions if not v.get("archived", False)]

        version_infos = [
            VersionInfo(
                id=str(v.get("id", "")),
                name=v.get("name", ""),
                released=v.get("released", False),
                release_date=v.get("release_date"),
                description=v.get("description"),
                archived=v.get("archived", False),
            )
            for v in versions
        ]

        return VersionsResponse(
            versions=version_infos,
            total=len(version_infos),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/releases/versions/{version_name}/progress", response_model=VersionProgress)
async def get_version_progress_endpoint(version_name: str):
    """Get progress metrics for a specific version."""
    try:
        progress = app.state.jira.get_version_progress(version_name)
        if not progress:
            raise HTTPException(status_code=404, detail=f"Version '{version_name}' not found or has no issues")

        return VersionProgress(
            version_name=version_name,
            total=progress.get("total", 0),
            done=progress.get("done", 0),
            in_progress=progress.get("in_progress", 0),
            todo=progress.get("todo", 0),
            done_percent=progress.get("done_percent", 0.0),
            in_progress_percent=progress.get("in_progress_percent", 0.0),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/releases/versions/{version_name}/issues", response_model=VersionIssuesResponse)
async def get_version_issues(version_name: str):
    """Get all issues for a specific version, grouped by type."""
    try:
        issues = app.state.jira.get_issues_by_fix_version(version_name)

        result_issues = []
        issues_by_type: dict[str, list[VersionIssue]] = {}

        for issue in issues:
            issue_type = issue.fields.issuetype.name
            assignee = issue.fields.assignee.displayName if issue.fields.assignee else None
            priority = issue.fields.priority.name if issue.fields.priority else None

            # Get parent info if available (for hierarchy display)
            parent_key = None
            parent_summary = None
            if hasattr(issue.fields, 'parent') and issue.fields.parent:
                parent_key = issue.fields.parent.key
                parent_summary = getattr(issue.fields.parent.fields, 'summary', None) if hasattr(issue.fields.parent, 'fields') else None

            issue_data = VersionIssue(
                key=issue.key,
                summary=issue.fields.summary,
                issue_type=issue_type,
                status=issue.fields.status.name,
                assignee=assignee,
                priority=priority,
                parent_key=parent_key,
                parent_summary=parent_summary,
            )

            result_issues.append(issue_data)

            if issue_type not in issues_by_type:
                issues_by_type[issue_type] = []
            issues_by_type[issue_type].append(issue_data)

        return VersionIssuesResponse(
            version_name=version_name,
            total=len(issues),
            issues_by_type=issues_by_type,
            issues=result_issues,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scenarios")
async def get_scenarios():
    """Get active scenarios and their status (cached for dashboard performance).

    Returns sprint-level scenario if available, with legacy per-ticket scenarios
    as fallback for backwards compatibility.
    """
    state = _state_cache.get()

    # NEW: Check for sprint-level scenario
    sprint_scenario = state.get_sprint_scenario()
    if sprint_scenario:
        # Return sprint scenario summary
        progress = sprint_scenario.get_progress_summary()

        # Get upcoming events for today
        today_events = []
        for event in sprint_scenario.get_pending_events_for_today():
            today_events.append({
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "ticket_key": event.ticket_key,
                "executed": event.executed,
            })

        return {
            "type": "sprint_scenario",
            "sprint_scenario": {
                "scenario_id": progress["scenario_id"],
                "sprint_id": progress["sprint_id"],
                "sprint_name": progress["sprint_name"],
                "archetype": progress["archetype"],
                "archetype_name": progress["archetype_name"],
                "current_day": progress["current_day"],
                "total_days": progress["total_days"],
                "current_mood": progress["current_mood"],
                "target_completion_rate": progress["target_completion_rate"],
                "actual_completion_rate": progress["actual_completion_rate"],
                "is_on_track": progress["is_on_track"],
                "total_items": progress["total_items"],
                "items_completed": progress["items_completed"],
                "items_carried_over": progress["items_carried_over"],
                "total_events": progress["total_events"],
                "events_executed": progress["events_executed"],
                "events_remaining": progress["events_remaining"],
                "release_context": progress["release_context"],
                "started_at": progress["started_at"],
                "today_events": today_events,
            },
            # Legacy format for backwards compatibility
            "active_count": len(sprint_scenario.sprint_items),
            "scenarios": [],  # Empty for sprint scenario format
            "distribution": {
                "normal_flow": progress["total_items"],
                "blocker": 0,
                "rework": 0,
                "scope_creep": 0,
                "dependency": 0,
            },
        }

    # LEGACY: Fall back to per-ticket scenarios
    scenarios = []
    active_distribution = {
        "normal_flow": 0,
        "blocker": 0,
        "rework": 0,
        "scope_creep": 0,
        "dependency": 0,
    }

    for scenario_id, scenario in state.active_scenarios.items():
        is_blocked = scenario.current_phase.value in ["blocked", "blocker_discussed", "waiting_on_dependency"]
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

        scenario_type = scenario.scenario_type.value
        if scenario_type in active_distribution:
            active_distribution[scenario_type] += 1

    return {
        "type": "legacy_scenarios",
        "active_count": len(scenarios),
        "scenarios": scenarios,
        "distribution": active_distribution,
    }


@app.get("/scenario/current")
async def get_current_scenario():
    """Get the current sprint scenario details."""
    state = _state_cache.get()
    sprint_scenario = state.get_sprint_scenario()

    if not sprint_scenario:
        return {"has_scenario": False, "message": "No active sprint scenario"}

    progress = sprint_scenario.get_progress_summary()

    # Build script overview
    script_overview = []
    for day in sprint_scenario.script:
        day_info = {
            "day": day.day,
            "mood": day.mood.value if day.mood else None,
            "total_events": len(day.events),
            "executed_events": len(day.get_executed_events()),
            "pending_events": len(day.get_pending_events()),
        }
        script_overview.append(day_info)

    return {
        "has_scenario": True,
        "scenario": progress,
        "script_overview": script_overview,
        "sprint_items": sprint_scenario.sprint_items,
        "items_completed": sprint_scenario.items_completed,
        "items_carried_over": sprint_scenario.items_carried_over,
    }


@app.post("/reset")
async def reset_state():
    """Reset simulation state (for testing)."""
    state = SimulationState()
    save_state(state)
    _state_cache.update(state)  # Update cache with new state
    return {"message": "State reset successfully"}


@app.post("/sync-reset")
async def sync_reset_state():
    """
    Soft reset: Rebuild simulation state from current Jira conditions.

    Unlike /reset (hard reset), this reads Jira and rebuilds state to match:
    - Sets sprint from Jira's active sprint
    - Creates scenarios from active Jira tickets
    - Resets agent workloads from actual Jira assignments
    - Clears scheduler infrastructure (SQLite, queue, clock)
    - Resets performance components (circuit breakers, tuner, heartbeat)

    Does NOT modify Jira (read-only operation).
    """
    global _per_ticket_breaker, _dynamic_tuner, _heartbeat_monitor

    try:
        # Create fresh state with preserved structure
        new_state = SimulationState()

        # 1. Fetch and inject current sprint from Jira
        jira_client = app.state.jira  # Use existing authenticated client

        # Validate Jira connectivity before proceeding
        try:
            jira_client.get_current_user()
        except Exception as auth_error:
            logger.error(f"Jira authentication failed: {auth_error}")
            raise HTTPException(
                status_code=503,
                detail=f"Jira authentication failed - check API token: {str(auth_error)}"
            )

        jira_sprint = jira_client.get_active_sprint()
        if jira_sprint:
            new_state.sprint.inject_jira_sprint(jira_sprint, current_time=pendulum.now("UTC"))

        # 2. Sync all active tickets from Jira (creates scenarios)
        sync_state_with_jira(new_state, jira_client, app.state.personas)

        # 3. Rebuild agent workloads from actual Jira assignments
        # First, clear all agent workloads (sync_state_with_jira assigns all active tickets)
        for agent_state in new_state.agents.values():
            agent_state.assigned_tickets.clear()

        # Then rebuild from active sprint only
        sprint_id = jira_sprint.get("id") if jira_sprint else None
        _rebuild_agent_workloads_from_jira(new_state, jira_client, app.state.personas, sprint_id=sprint_id)

        # 4. Sync planning horizon from Jira future sprints
        _sync_planning_horizon_from_jira(new_state, jira_client)

        # === Phase 3: Scheduler Infrastructure Reset ===
        scheduler = app.state.scheduler

        # Clear SQLite action store
        conn = scheduler.store._get_connection()
        conn.execute("DELETE FROM scheduled_actions")
        conn.commit()
        # Close connection if file-based (not in-memory)
        if not scheduler.store._conn:
            conn.close()

        # Clear in-memory queue
        scheduler.queue._heap.clear()

        # Reset VirtualClock to real time
        scheduler.clock.set_time(pendulum.now("UTC"))

        # === Phase 5: Performance Components Reset ===
        if _per_ticket_breaker:
            _per_ticket_breaker.reset_all()

        if _dynamic_tuner:
            _dynamic_tuner.reset()

        if _heartbeat_monitor:
            _heartbeat_monitor.reset()

        # 5. Set timestamp
        new_state.last_run = pendulum.now("UTC")

        # Save and update cache
        save_state(new_state)
        _state_cache.update(new_state)

        logger.info(
            f"Sync reset complete: sprint={new_state.sprint.jira_sprint_name}, "
            f"scenarios={len(new_state.active_scenarios)}"
        )

        return {
            "success": True,
            "message": "State synced with Jira",
            "sprint": {
                "name": new_state.sprint.jira_sprint_name,
                "number": new_state.sprint.sprint_number,
                "day": new_state.sprint.sprint_day,
            },
            "active_scenarios": len(new_state.active_scenarios),
            "agents_synced": len(new_state.agents),
            "scheduler_cleared": True,
            "performance_reset": True,
        }
    except HTTPException:
        # Re-raise HTTPExceptions (like auth errors) without wrapping
        raise
    except Exception as e:
        logger.error(f"Sync reset failed: {e}")
        raise HTTPException(status_code=500, detail=f"Sync reset failed: {str(e)}")


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
        clock = RealClock()
        orchestrator = ScenarioOrchestrator(
            jira_client=logged_jira,
            llm_service=logged_llm,
            personas=app.state.personas,
            templates=app.state.templates,
            settings=app.state.settings,
            clock=clock,
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
            # Skip Epics - they should never be in sprints
            if issue.fields.issuetype.name == "Epic":
                continue

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

        # Execute sprint planning with scenario generation
        result = orchestrator.sprint_planning_crew.plan_sprint_with_scenario(
            pm_id=pm_id,
            team=team,
            active_sprint=active_sprint,
            unassigned_items=unassigned_items[:15],  # Limit to 15 items
            state=state,
            release_context=None,  # Could be enhanced to detect release context
        )

        # Save state with new scenario
        save_state(state)
        _state_cache.update(state)

        # End session
        app.state.log_writer.end_session(
            success=True,
            actions_completed=1,
        )

        # Check if scenario was generated
        scenario_info = None
        if state.sprint_scenario:
            scenario_info = {
                "scenario_id": state.sprint_scenario.get("scenario_id"),
                "archetype": state.sprint_scenario.get("archetype"),
                "archetype_name": state.sprint_scenario.get("archetype_name"),
                "total_events": state.sprint_scenario.get("total_events", 0),
            }

        return {
            "success": True,
            "sprint": active_sprint.get("name"),
            "unassigned_items_available": len(unassigned_items),
            "result": result,
            "sprint_scenario": scenario_info,
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
            "review_tickets": agent_state.review_tickets if agent_state else [],
            "current_workload": agent_state.current_workload if agent_state else 0,
            "daily_actions": agent_state.actions_today if agent_state else 0,
        })

    # Get schedule config for dashboard context
    schedule_config = app.state.settings.get("schedule", {})

    return {
        "agents": agents,
        "last_run": _format_last_run(state.last_run),
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


class ReleaseNotesResponse(BaseModel):
    """Response model for release notes generation."""
    version: str
    executive_notes: str
    technical_notes: str
    saved_path: str
    generated_at: str
    issue_count: int
    teams: list[str]
    from_cache: bool = False
    tags: list[str] = []  # AI-generated tags like "Performance", "Features", "Security"


class ReleaseNotesHistoryItem(BaseModel):
    """Metadata for a previously generated release notes file."""
    version: str
    generated_at: str
    file_formats: list[str]  # ['md', 'pdf', 'docx'] - available formats
    issue_count: int
    tags: list[str]


class OutputFormat(str, Enum):
    """Supported output formats for release notes."""
    MARKDOWN = "md"
    TEXT = "txt"
    DOCX = "docx"
    PPTX = "pptx"
    PDF = "pdf"


class ReleaseNotesRequest(BaseModel):
    """Request model for release notes generation."""
    output_format: OutputFormat = OutputFormat.MARKDOWN
    regenerate: bool = False


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
        response = litellm.completion(
            model=app.state.llm.complex_model,  # Use Sonnet for chat
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        pm_response = response.choices[0].message.content.strip()
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


# ============ Release Notes Generation ============

def build_account_team_lookup(personas: dict) -> dict[str, dict]:
    """Build lookup from Jira account ID to team/display_name."""
    lookup = {}
    for agent_id, config in personas.get("agents", {}).items():
        jira_account_id = config.get("jira_account_id")
        if jira_account_id:
            lookup[jira_account_id] = {
                "team": config.get("team"),
                "display_name": config.get("display_name"),
                "role": config.get("role"),
                "agent_id": agent_id,
            }
    return lookup


def categorize_issues_for_release_notes(
    issues: list,
    team_lookup: dict,
) -> tuple[dict, dict, dict]:
    """
    Categorize issues by type and team for release notes.

    Returns:
        (issues_by_category, issues_by_team, metrics)
    """
    # Issue type to category mapping
    type_to_category = {
        "Story": "Features",
        "Epic": "Features",
        "Bug": "Fixes",
        "Task": "Improvements",
        "Sub-task": "Improvements",
        "Subtask": "Improvements",
    }

    issues_by_category = {
        "Features": [],
        "Fixes": [],
        "Improvements": [],
    }

    issues_by_team = {}
    teams_seen = set()

    for issue in issues:
        # Get issue details
        key = issue.key
        summary = issue.fields.summary
        issue_type = issue.fields.issuetype.name
        category = type_to_category.get(issue_type, "Improvements")

        # Determine team from assignee
        assignee = issue.fields.assignee
        team = "unassigned"
        if assignee:
            account_id = assignee.accountId
            agent_info = team_lookup.get(account_id, {})
            team = agent_info.get("team") or "unassigned"

        if team and team != "unassigned":
            teams_seen.add(team)

        # Create issue record
        issue_record = {
            "key": key,
            "summary": summary,
            "type": issue_type,
            "team": team,
            "status": issue.fields.status.name,
        }

        # Add to category
        issues_by_category[category].append(issue_record)

        # Add to team
        if team not in issues_by_team:
            issues_by_team[team] = {
                "Features": 0,
                "Fixes": 0,
                "Improvements": 0,
                "issues": [],
            }
        issues_by_team[team][category] += 1
        issues_by_team[team]["issues"].append(issue_record)

    metrics = {
        "total_issues": len(issues),
        "done_count": sum(1 for i in issues if i.fields.status.name.lower() in ["done", "closed", "resolved"]),
        "teams": sorted(list(teams_seen)),
        "category_counts": {
            cat: len(items) for cat, items in issues_by_category.items()
        },
    }

    return issues_by_category, issues_by_team, metrics


def load_cached_release_notes(version: str) -> Optional[dict]:
    """Load cached release notes from disk if available."""
    releases_dir = Path("data/releases")
    file_path = releases_dir / f"{version}.md"

    if not file_path.exists():
        return None

    try:
        content = file_path.read_text(encoding="utf-8")

        # Parse the markdown to extract sections
        sections = {}
        current_section = None
        current_content = []

        for line in content.split("\n"):
            if line.startswith("## Executive Summary"):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = "executive"
                current_content = []
            elif line.startswith("## Technical Details"):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = "technical"
                current_content = []
            elif line.startswith("## Statistics"):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = "stats"
                current_content = []
            elif line.startswith("---"):
                continue  # Skip horizontal rules
            elif current_section:
                current_content.append(line)

        if current_section:
            sections[current_section] = "\n".join(current_content).strip()

        if "executive" in sections and "technical" in sections:
            return {
                "executive_notes": sections["executive"],
                "technical_notes": sections["technical"],
            }

    except Exception as e:
        logger.error(f"Failed to generate release notes: {e}")

    return None


def save_release_notes(
    version: str,
    executive_notes: str,
    technical_notes: str,
    metrics: dict,
    tags: list[str] = None,
) -> str:
    """Save release notes to disk and return the file path.

    Also saves a companion JSON metadata file with tags and other metadata.
    """
    import json

    releases_dir = Path("data/releases")
    releases_dir.mkdir(parents=True, exist_ok=True)

    file_path = releases_dir / f"{version}.md"
    timestamp = pendulum.now("UTC").isoformat()

    content = f"""# Release Notes: {version}
Generated: {timestamp}

---

## Executive Summary

{executive_notes}

---

## Technical Details

{technical_notes}

---

## Statistics
- Total Issues: {metrics.get('total_issues', 0)}
- Teams Contributing: {', '.join(metrics.get('teams', [])) or 'None'}
- Features: {metrics.get('category_counts', {}).get('Features', 0)}
- Fixes: {metrics.get('category_counts', {}).get('Fixes', 0)}
- Improvements: {metrics.get('category_counts', {}).get('Improvements', 0)}
"""

    file_path.write_text(content, encoding="utf-8")

    # Save companion JSON metadata file
    json_path = releases_dir / f"{version}.json"
    metadata = {
        "version": version,
        "generated_at": timestamp,
        "issue_count": metrics.get('total_issues', 0),
        "teams": metrics.get('teams', []),
        "tags": tags or [],
        "category_counts": metrics.get('category_counts', {}),
    }
    json_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return str(file_path)


def get_media_type(output_format: OutputFormat) -> str:
    """Get the MIME type for a given output format."""
    media_types = {
        OutputFormat.MARKDOWN: "text/markdown",
        OutputFormat.TEXT: "text/plain",
        OutputFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        OutputFormat.PPTX: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        OutputFormat.PDF: "application/pdf",
    }
    return media_types.get(output_format, "application/octet-stream")


def markdown_to_plain_text(markdown: str) -> str:
    """Convert markdown to plain text by stripping formatting."""
    import re
    lines = markdown.split('\n')
    result = []

    for line in lines:
        # Remove header markers but keep text
        if line.startswith('#'):
            line = re.sub(r'^#+\s*', '', line)
            if result and result[-1] != '':
                result.append('')
            result.append(line.upper())
            result.append('')
            continue

        # Remove bold markers
        line = re.sub(r'\*\*([^*]+)\*\*', r'\1', line)

        # Remove inline code markers
        line = re.sub(r'`([^`]+)`', r'\1', line)

        result.append(line)

    return '\n'.join(result)


def load_release_metadata(version: str) -> Optional[dict]:
    """Load metadata from companion JSON file for a release version."""
    import json
    json_path = Path("data/releases") / f"{version}.json"
    if json_path.exists():
        try:
            return json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def scan_releases_directory() -> list[ReleaseNotesHistoryItem]:
    """Scan the releases directory and return metadata for all generated releases."""
    import json
    import re

    releases_dir = Path("data/releases")
    if not releases_dir.exists():
        return []

    # Find all unique versions by looking at .md files
    history_items = []
    md_files = list(releases_dir.glob("*.md"))

    for md_file in md_files:
        version = md_file.stem  # filename without extension

        # Determine which formats exist for this version
        file_formats = []
        for ext in ['md', 'txt', 'pdf', 'docx', 'pptx']:
            if (releases_dir / f"{version}.{ext}").exists():
                file_formats.append(ext)

        # Try to load metadata from companion JSON
        metadata = load_release_metadata(version)

        if metadata:
            # Use JSON metadata if available
            history_items.append(ReleaseNotesHistoryItem(
                version=version,
                generated_at=metadata.get("generated_at", ""),
                file_formats=file_formats,
                issue_count=metadata.get("issue_count", 0),
                tags=metadata.get("tags", []),
            ))
        else:
            # Parse the markdown file header for generated_at timestamp
            try:
                content = md_file.read_text(encoding="utf-8")
                generated_at = ""
                issue_count = 0

                # Look for "Generated: <timestamp>" line
                match = re.search(r"Generated:\s*(.+)", content)
                if match:
                    generated_at = match.group(1).strip()

                # Look for "Total Issues: <count>" line
                match = re.search(r"Total Issues:\s*(\d+)", content)
                if match:
                    issue_count = int(match.group(1))

                history_items.append(ReleaseNotesHistoryItem(
                    version=version,
                    generated_at=generated_at,
                    file_formats=file_formats,
                    issue_count=issue_count,
                    tags=[],  # No tags without JSON metadata
                ))
            except Exception as e:
                logger.warning(f"Failed to parse release notes for {version}: {e}")
                continue

    # Sort by generated_at descending (newest first)
    history_items.sort(key=lambda x: x.generated_at, reverse=True)

    return history_items


@app.get("/api/releases/history", response_model=list[ReleaseNotesHistoryItem])
async def get_release_notes_history():
    """
    Get a list of all previously generated release notes with metadata.

    Returns:
        List of ReleaseNotesHistoryItem with version, formats, timestamps, and tags
    """
    try:
        return scan_releases_directory()
    except Exception as e:
        logger.error(f"Failed to scan releases directory: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load release history: {str(e)}")


@app.get("/api/releases/{version}/download/{format}")
async def download_release_notes(version: str, format: str):
    """
    Download existing release notes without regenerating.

    Args:
        version: The version name
        format: The output format (md, txt, pdf, docx, pptx)

    Returns:
        FileResponse for the requested format

    Raises:
        404: If the file doesn't exist for that version/format
    """
    # Validate format
    valid_formats = ['md', 'txt', 'pdf', 'docx', 'pptx']
    if format not in valid_formats:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid format: {format}. Must be one of: {', '.join(valid_formats)}"
        )

    releases_dir = Path("data/releases")
    file_path = releases_dir / f"{version}.{format}"

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Release notes for '{version}' in '{format}' format not found. Generate them first."
        )

    # Determine media type
    media_types = {
        'md': 'text/markdown',
        'txt': 'text/plain',
        'pdf': 'application/pdf',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    }

    return FileResponse(
        path=str(file_path),
        filename=f"{version}_release_notes.{format}",
        media_type=media_types.get(format, 'application/octet-stream'),
    )


@app.post("/api/releases/{version}/generate-notes", response_model=None)
async def generate_release_notes(
    version: str,
    request: Optional[ReleaseNotesRequest] = None
):
    """
    Generate release notes for a specific version.

    Args:
        version: The fix version name (e.g., "v1.2.0")
        request: Optional request body with output_format and regenerate flags

    Returns:
        For md/txt: ReleaseNotesResponse JSON with content inline
        For docx/pptx/pdf: FileResponse for direct file download

    Raises:
        404: Version not found
        400: No issues in version
        500: Generation or save failed
    """
    # Default request if none provided (backwards compatibility)
    if request is None:
        request = ReleaseNotesRequest()

    output_format = request.output_format
    regenerate = request.regenerate

    try:
        jira = app.state.jira
        llm = app.state.llm
        releases_dir = Path("data/releases")
        releases_dir.mkdir(parents=True, exist_ok=True)

        # Check if version exists
        versions = jira.get_fix_versions()
        version_exists = any(v["name"] == version for v in versions)
        if not version_exists:
            raise HTTPException(
                status_code=404,
                detail=f"Version '{version}' not found in Jira"
            )

        # Try to use cached markdown notes if available
        cached = None
        if not regenerate:
            cached = load_cached_release_notes(version)

        # Get or generate the base notes (always needed)
        tags = []  # Will be populated from cache or generated fresh
        if cached:
            executive_notes = cached["executive_notes"]
            technical_notes = cached["technical_notes"]
            # Get metrics from Jira for statistics
            progress = jira.get_version_progress(version) or {}
            metrics = {
                "total_issues": progress.get("total", 0),
                "teams": [],
                "category_counts": {"Features": 0, "Fixes": 0, "Improvements": 0}
            }
            # Try to load tags from metadata JSON
            metadata = load_release_metadata(version)
            if metadata:
                tags = metadata.get("tags", [])
            from_cache = True
        else:
            # Fetch issues for this version
            issues = jira.get_issues_by_fix_version(version)
            if not issues:
                raise HTTPException(
                    status_code=400,
                    detail=f"No issues found for version '{version}'"
                )

            # Build team lookup and categorize
            team_lookup = build_account_team_lookup(app.state.personas)
            issues_by_category, issues_by_team, metrics = categorize_issues_for_release_notes(
                issues, team_lookup
            )

            # Generate release notes via LLM
            notes = llm.generate_release_notes(
                version_name=version,
                issues_by_category=issues_by_category,
                issues_by_team=issues_by_team,
                version_metrics=metrics,
            )
            executive_notes = notes["executive_notes"]
            technical_notes = notes["technical_notes"]
            from_cache = False

            # Generate tags for this release
            tags = llm.generate_release_tags(
                version_name=version,
                issues_by_category=issues_by_category,
                executive_notes=executive_notes,
            )

            # Always save markdown version as cache (now includes tags)
            save_release_notes(
                version=version,
                executive_notes=executive_notes,
                technical_notes=technical_notes,
                metrics=metrics,
                tags=tags,
            )

        generated_at = pendulum.now("UTC").isoformat()

        # Route based on output format
        if output_format == OutputFormat.MARKDOWN:
            return ReleaseNotesResponse(
                version=version,
                executive_notes=executive_notes,
                technical_notes=technical_notes,
                saved_path=str(releases_dir / f"{version}.md"),
                generated_at=generated_at,
                issue_count=metrics.get("total_issues", 0),
                teams=metrics.get("teams", []),
                from_cache=from_cache,
                tags=tags,
            )

        elif output_format == OutputFormat.TEXT:
            # Convert to plain text
            plain_executive = markdown_to_plain_text(executive_notes)
            plain_technical = markdown_to_plain_text(technical_notes)

            # Save text file
            txt_path = releases_dir / f"{version}.txt"
            txt_content = f"""RELEASE NOTES: {version}
Generated: {generated_at}

{'='*60}

EXECUTIVE SUMMARY

{plain_executive}

{'='*60}

TECHNICAL DETAILS

{plain_technical}

{'='*60}

STATISTICS
- Total Issues: {metrics.get('total_issues', 0)}
- Teams Contributing: {', '.join(metrics.get('teams', [])) or 'None'}
- Features: {metrics.get('category_counts', {}).get('Features', 0)}
- Fixes: {metrics.get('category_counts', {}).get('Fixes', 0)}
- Improvements: {metrics.get('category_counts', {}).get('Improvements', 0)}
"""
            txt_path.write_text(txt_content, encoding="utf-8")

            return ReleaseNotesResponse(
                version=version,
                executive_notes=plain_executive,
                technical_notes=plain_technical,
                saved_path=str(txt_path),
                generated_at=generated_at,
                issue_count=metrics.get("total_issues", 0),
                teams=metrics.get("teams", []),
                from_cache=from_cache,
                tags=tags,
            )

        elif output_format in [OutputFormat.DOCX, OutputFormat.PPTX, OutputFormat.PDF]:
            # Use Anthropic Skills API to generate document
            skill_id = output_format.value  # "docx", "pptx", or "pdf"

            file_bytes = llm.generate_document_with_skill(
                skill_id=skill_id,
                version_name=version,
                executive_notes=executive_notes,
                technical_notes=technical_notes,
                metrics=metrics,
            )

            # Save the file
            file_path = releases_dir / f"{version}.{output_format.value}"
            file_path.write_bytes(file_bytes)

            return FileResponse(
                path=str(file_path),
                filename=f"{version}_release_notes.{output_format.value}",
                media_type=get_media_type(output_format),
            )

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported output format: {output_format}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate release notes for {version}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate release notes: {str(e)}"
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
