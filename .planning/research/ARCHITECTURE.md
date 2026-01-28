# Architecture Research

**Domain:** Real-time Event Scheduling with External System Reconciliation
**Researched:** 2026-01-27
**Confidence:** HIGH

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        APPLICATION LAYER                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   FastAPI    │  │  Dashboard   │  │  Chat/Admin  │              │
│  │   (REST)     │  │   (React)    │  │     UI       │              │
│  └──────┬───────┘  └──────────────┘  └──────────────┘              │
│         │                                                            │
├─────────┴────────────────────────────────────────────────────────────┤
│                    ORCHESTRATION LAYER                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   Scenario   │  │   Analyzer   │  │   Planner    │              │
│  │ Orchestrator │  │(Opportunity)  │  │ (Decision)   │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         │                  │                  │                      │
├─────────┴──────────────────┴──────────────────┴──────────────────────┤
│                    SCHEDULING LAYER (NEW)                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   Event      │  │  Execution   │  │   Reconciler │              │
│  │  Scheduler   │  │   Window     │  │   (Jira)     │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         │                  │                  │                      │
├─────────┴──────────────────┴──────────────────┴──────────────────────┤
│                    EXECUTION LAYER                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  CrewAI      │  │    Agent     │  │   Workflow   │              │
│  │   Crews      │  │  Factories   │  │  Pathfinder  │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         │                  │                  │                      │
├─────────┴──────────────────┴──────────────────┴──────────────────────┤
│                    SERVICE LAYER                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ JiraClient   │  │  LLMService  │  │ StateManager │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         │                  │                  │                      │
├─────────┴──────────────────┴──────────────────┴──────────────────────┤
│                    PERSISTENCE LAYER                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ state.json   │  │  Jira API    │  │  SQLite      │              │
│  │  (Local)     │  │ (External)   │  │   (Logs)     │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| **Event Scheduler** | Maintain timeline of scheduled actions; provide "what's due now?" query | Priority queue or sorted list with time-based indexing |
| **Execution Window** | Determine if preconditions met; check Jira state before executing | State validator with real-time Jira API queries |
| **Reconciler** | Compare simulation plan with Jira reality; adapt on mismatch | Diff engine + decision tree for conflict resolution |
| **Chaos Injector** | Randomly inject unplanned events (bugs, blockers, scope creep) | Weighted random selection from event catalog |
| **Planning Horizon** | Maintain rolling window of scheduled future work (3-7 days ahead) | Sliding window over event queue |
| **Virtual Clock** | Track simulation time independently of wall-clock time | DateTime state field with configurable tick duration |

## Recommended Project Structure

```
src/
├── scheduling/              # NEW: Real-time scheduling system
│   ├── __init__.py
│   ├── event_scheduler.py   # Core scheduler with priority queue
│   ├── execution_window.py  # "What's ready to execute NOW?"
│   ├── reconciler.py        # Compare plan vs Jira reality
│   ├── chaos_engine.py      # Random event injection
│   └── models.py            # ScheduledEvent, ExecutionWindow, etc.
│
├── orchestrator/            # EXISTING: High-level orchestration
│   ├── orchestrator.py      # Modified to query scheduler
│   ├── analyzer.py          # Detect opportunities from Jira
│   ├── planner.py           # LLM decides actions
│   └── pathfinder.py        # Workflow progression logic
│
├── scenarios/               # EXISTING: Sprint scenario definitions
│   ├── sprint_scenario.py   # Modified to output scheduled events
│   ├── scenario_planner.py  # Generates event schedules
│   └── script_executor.py   # DEPRECATED - replaced by scheduler
│
├── state/                   # EXISTING: State management
│   ├── models.py            # Add simulation_time, scheduled_events
│   └── simulation_state.py  # Load/save state with scheduler data
│
├── services/                # EXISTING: External services
│   ├── jira_client.py       # Add reconciliation queries
│   └── llm_service.py       # Scenario planning and adaptation
│
├── crews/                   # EXISTING: CrewAI execution units
│   └── ...                  # No changes - same execution units
│
└── main.py                  # MODIFIED: /trigger uses scheduler
```

### Structure Rationale

- **scheduling/:** New layer sits between orchestration and execution. Provides temporal dimension to existing scenario system without disrupting proven orchestration patterns.
- **orchestrator/:** Modified to query scheduler instead of directly executing. Orchestrator remains decision-maker, scheduler becomes timeline-keeper.
- **scenarios/:** Enhanced to produce timestamped event schedules rather than immediate execution scripts.
- **state/:** Extended with virtual clock and scheduled event queue for persistence.

## Architectural Patterns

### Pattern 1: Time-Triggered + Event-Triggered Hybrid

**What:** Combines scheduled time-based events with reactive event-triggered responses. System executes scripted timeline while reacting to external changes (Jira state mismatches).

**When to use:** When you need predictable scripted behaviors (time-triggered) but must adapt to external reality (event-triggered).

**Trade-offs:**
- **Pro:** Realistic simulation follows script while handling unexpected changes
- **Pro:** Deterministic replay (same seed = same timeline) with adaptive recovery
- **Con:** More complex than pure time-triggered (requires reconciliation logic)
- **Con:** Needs careful handling of timeline disruptions

**Example:**
```python
# Time-triggered: Execute pre-scheduled events
scheduled_events = scheduler.get_events_due(current_time=state.simulation_time)
for event in scheduled_events:
    # Event-triggered: Check preconditions before executing
    if execution_window.check_preconditions(event, jira_state):
        executor.execute(event)
    else:
        # Adapt: Reschedule or replace with alternative
        adapted_event = reconciler.adapt(event, jira_state)
        scheduler.reschedule(adapted_event)
```

### Pattern 2: Discrete Event Simulation (DES)

**What:** Simulation advances through discrete timesteps (ticks). Each tick: (1) advance virtual clock, (2) query "what's due?", (3) execute due events, (4) schedule new events.

**When to use:** When modeling systems with distinct events happening at specific points in time (ticket transitions, comments, status changes).

**Trade-offs:**
- **Pro:** Natural fit for Jira workflow (discrete state transitions)
- **Pro:** Easy to replay and debug (state at each tick is snapshot)
- **Con:** Tick granularity limits temporal resolution (can't model sub-tick events)
- **Con:** May accumulate drift between simulation time and wall-clock time

**Example:**
```python
class EventScheduler:
    def __init__(self):
        self.event_queue: list[ScheduledEvent] = []  # Sorted by scheduled_time

    def schedule(self, event_type: str, scheduled_time: datetime, **params):
        event = ScheduledEvent(
            event_type=event_type,
            scheduled_time=scheduled_time,
            parameters=params
        )
        heapq.heappush(self.event_queue, event)

    def get_events_due(self, current_time: datetime) -> list[ScheduledEvent]:
        """Future Event List (FEL) query - core of DES."""
        due = []
        while self.event_queue and self.event_queue[0].scheduled_time <= current_time:
            due.append(heapq.heappop(self.event_queue))
        return due
```

### Pattern 3: State Reconciliation with Optimistic Execution

**What:** Execute simulation events optimistically (assume they'll succeed), then reconcile with external system (Jira). On mismatch: detect, diagnose, adapt.

**When to use:** When external system (Jira) is source of truth but you need local planning autonomy.

**Trade-offs:**
- **Pro:** Fast simulation without waiting for external API confirmation
- **Pro:** Graceful handling of manual Jira changes (user interventions)
- **Con:** Must handle conflict resolution (simulation says X, Jira says Y)
- **Con:** Requires rollback or forward-correction mechanisms

**Example:**
```python
class Reconciler:
    def reconcile(self, event: ScheduledEvent, jira_state: dict) -> ReconciliationResult:
        """Compare planned event against Jira reality."""
        expected_status = event.parameters.get("target_status")
        actual_status = jira_state.get("status")

        if expected_status != actual_status:
            # Mismatch detected
            if actual_status in TERMINAL_STATES:
                # Jira moved ahead - cancel our event
                return ReconciliationResult(action="cancel", reason="already_done")
            else:
                # Jira diverged - recalculate path
                new_path = pathfinder.calculate_path(actual_status, expected_status)
                return ReconciliationResult(action="adapt", new_events=new_path)

        return ReconciliationResult(action="proceed")
```

## Data Flow

### Request Flow (Tick Execution)

```
[n8n Cron Trigger]
    ↓
[/trigger Endpoint]
    ↓
[Load State + Advance Virtual Clock]
    ↓
[Sync with Jira] ──→ [Update sprint_number, sprint_day]
    ↓
[Query Scheduler: "What's due at simulation_time?"]
    ↓
[Execution Window Check: Preconditions met?]
    ↓         ↓
    YES       NO ──→ [Reconciler: Adapt or Reschedule]
    ↓
[Execute Event via Crew/Agent]
    ↓
[Update Jira via API]
    ↓
[Record in State + Schedule Follow-up Events]
    ↓
[Save State]
```

### Event Scheduling Flow

```
[Sprint Scenario Creation]
    ↓
[LLM Generates Event Script with Relative Times]
    (e.g., "Day 1: pickup, Day 3: blocker, Day 5: resolve")
    ↓
[Scenario Planner converts to Absolute Times]
    (sprint_start_date + day_offset = scheduled_time)
    ↓
[Events added to Scheduler Queue]
    ↓
[Each Tick: Scheduler checks "events <= current_time"]
    ↓
[Execution Window validates preconditions]
    ↓
[Crew executes ──→ Jira API]
    ↓
[On completion: Schedule next event in sequence]
```

### Reconciliation Flow

```
[Pre-Execution Check]
    ↓
[Fetch Current Jira State for Ticket]
    ↓
[Compare with Expected State from Scenario]
    ↓         ↓
    MATCH     MISMATCH
    ↓         ↓
[Execute]   [Diagnose Cause]
              ↓
         ┌────┴────┐
         │         │
    [Manual]   [Timing]
     Change    Drift
         │         │
    [Cancel]  [Reschedule]
     Event     Event
         └────┬────┘
              ↓
         [Log Adaptation]
              ↓
         [Update Scenario]
```

### Key Data Flows

1. **Script Generation → Scheduling:** LLM creates scenario script with relative day numbers → ScenarioPlanner converts to absolute timestamps → EventScheduler stores in priority queue
2. **Tick Execution:** Virtual clock advances → Scheduler returns due events → ExecutionWindow checks preconditions → Crews execute → Results update state and Jira
3. **Reconciliation Loop:** Before execution → Fetch Jira state → Compare with plan → On mismatch: cancel/adapt/reschedule → Log decision → Continue
4. **Chaos Injection:** Random roll each tick → Select event from chaos catalog → Insert into scheduler at random future time → Disrupts planned timeline
5. **Planning Horizon:** Maintain 3-7 day lookahead → When horizon < threshold: trigger LLM to extend plan → Schedule new events in future window

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1-10 teams | Monolith with in-memory event queue is fine. State in JSON. |
| 10-100 teams | Move scheduler to Redis sorted sets for performance. Consider async execution. |
| 100+ teams | Distributed scheduler (Celery/Temporal). Postgres for state. Event sourcing pattern. |

### Scaling Priorities

1. **First bottleneck:** Jira API rate limits. Solution: Batch updates, cache board state, use Jira webhooks instead of polling.
2. **Second bottleneck:** Scheduler queue size (O(n log n) operations). Solution: Partition by team/sprint, use Redis sorted sets, prune completed events.
3. **Third bottleneck:** LLM planning latency. Solution: Pre-generate common scenarios, cache scenario templates, use faster models for routine decisions.

## Anti-Patterns

### Anti-Pattern 1: Polling Jira on Every Event

**What people do:** Check Jira state via API call before every single action execution.

**Why it's wrong:**
- 10 events/tick × 60 ticks/hour = 600 API calls/hour → Rate limit violations
- Latency compounds (200ms × 10 = 2s tick duration)
- Jira's state doesn't change that fast between events

**Do this instead:**
- Fetch board snapshot once per tick
- Cache ticket states in memory for tick duration
- Use Jira webhooks to invalidate cache on external changes
- Only re-check state if reconciliation detects mismatch

### Anti-Pattern 2: Tightly Coupling Schedule to Wall-Clock Time

**What people do:** Schedule events using `datetime.now() + timedelta(hours=4)` and execute when `datetime.now() >= scheduled_time`.

**Why it's wrong:**
- Simulation must run faster than real-time for testing (compress 2-week sprint into 1 hour)
- Can't replay deterministically (wall-clock time always advances)
- Can't pause/resume simulation
- Can't handle tick delays (if tick is late, events pile up)

**Do this instead:**
- Use virtual clock: `state.simulation_time` advances by `tick_duration` each tick
- Schedule events relative to virtual time: `state.simulation_time + timedelta(hours=4)`
- Execute when `state.simulation_time >= event.scheduled_time`
- Allows time compression, deterministic replay, pause/resume

### Anti-Pattern 3: Blocking Execution on Failed Preconditions

**What people do:** When precondition fails (ticket in wrong state), throw error and halt tick execution.

**Why it's wrong:**
- One mismatch blocks entire simulation
- Fails to handle graceful degradation
- No adaptation to external changes
- Brittle in face of manual Jira interventions

**Do this instead:**
- On precondition failure: log warning, attempt reconciliation
- Reconciler provides adaptation strategy (cancel, reschedule, replace)
- Continue executing other events in same tick
- Track adaptation rate as health metric

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Jira API | Reconciliation + Optimistic Updates | Fetch board snapshot per tick, update optimistically, verify on next sync |
| LLM (Anthropic) | Request/Response for Planning | Generate scenarios, adapt on mismatch, extend planning horizon |
| n8n (Cron) | Webhook Trigger | Dumb trigger only - all logic in FastAPI, n8n just POSTs to /trigger |
| Frontend (React) | REST + Polling | Dashboard polls /api/dashboard every 15s for state updates |
| SQLite Logs | Write-only Async | Log all events/LLM calls asynchronously, never block on logging |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Orchestrator ↔ Scheduler | Query Interface | Orchestrator asks "what's due?", scheduler returns events |
| Scheduler ↔ ExecutionWindow | Validation Interface | Scheduler provides event, window checks preconditions |
| ExecutionWindow ↔ Reconciler | Diff + Adaptation | Window detects mismatch, reconciler decides adaptation |
| Orchestrator ↔ Crews | Execution Interface | Orchestrator delegates to crew, crew returns result |
| Crews ↔ JiraClient | Service Layer | Crews use JiraClient wrapper, never direct API calls |
| State ↔ Scheduler | Serialization | Scheduler state persists in state.json, loads on startup |

## New System Integration with Existing Architecture

### Build Order Dependencies

**Phase 1: Foundation (Virtual Clock + Models)**
1. Add `simulation_time: datetime` to SimulationState
2. Add `tick_duration_hours: float` config (default: 4.0)
3. Create `src/scheduling/models.py` with ScheduledEvent, ReconciliationResult
4. No dependencies on other systems - pure data models

**Phase 2: Scheduler Core**
1. Create `src/scheduling/event_scheduler.py` with priority queue
2. Depends on: Phase 1 models
3. Used by: Orchestrator (query interface)
4. Test standalone with mock events

**Phase 3: Execution Window + Reconciliation**
1. Create `src/scheduling/execution_window.py` (precondition validator)
2. Create `src/scheduling/reconciler.py` (adaptation logic)
3. Depends on: JiraClient, WorkflowPathfinder, Scheduler
4. Used by: Orchestrator (before crew execution)

**Phase 4: Integration with Orchestrator**
1. Modify `orchestrator.py` to query scheduler instead of analyzer-only flow
2. Insert ExecutionWindow check before crew execution
3. Add Reconciler call on precondition failure
4. Depends on: All scheduler components

**Phase 5: Scenario Enhancement**
1. Modify `scenario_planner.py` to output timestamped events
2. Convert relative day numbers to absolute simulation_time timestamps
3. Feed events to scheduler on scenario creation
4. Depends on: Scheduler API

**Phase 6: Chaos Injection**
1. Create `src/scheduling/chaos_engine.py`
2. Define chaos event catalog (random bugs, blockers, scope creep)
3. Add chaos injection step to tick execution
4. Depends on: Scheduler (to insert events), existing Crews (to execute)

### Integration Strategy

**Minimal Disruption Approach:**
- Existing Analyzer → Planner → Crews flow remains intact
- Scheduler sits *alongside* existing flow initially
- Orchestrator decides: use scheduler for scripted events, use analyzer for reactive opportunities
- Gradually migrate from analyzer-driven to scheduler-driven execution
- Legacy per-ticket ActiveScenario deprecated in favor of sprint-level scheduled events

**Data Flow Changes:**
- **Before:** n8n → /trigger → sync_jira → analyzer (detect) → planner (decide) → crews (execute)
- **After:** n8n → /trigger → sync_jira → **advance_clock** → **scheduler (what's due?)** → execution_window (validate) → crews (execute)

**State Migration:**
- Existing `sprint_scenario.script` contains relative day events
- On first run with scheduler: convert to absolute times and populate scheduler queue
- New scenarios generated with timestamps from start
- Old scenarios gracefully converted on load

## Sources

- [Event Driven Architecture Done Right: How to Scale Systems with Quality in 2025](https://www.growin.com/blog/event-driven-architecture-scale-systems-2025/)
- [Discrete-event simulation - Wikipedia](https://en.wikipedia.org/wiki/Discrete-event_simulation)
- [Inside Discrete-Event Simulation Software: How It Works and Why It Matters](https://www.simio.com/case-studies/inside-discrete-event-simulation-software-how-it-works-and-why-it-matters/)
- [A hierarchical architecture for time- and event-triggered real-time systems](https://www.sciencedirect.com/science/article/pii/S138376211930459X)
- [Time-triggered architecture - Wikipedia](https://en.wikipedia.org/wiki/Time-triggered_architecture)
- [Event-driven scheduling — Airflow 3.1.6 Documentation](https://airflow.apache.org/docs/apache-airflow/stable/authoring-and-scheduling/event-scheduling.html)

---
*Architecture research for: Real-time Event Scheduling with External System Reconciliation*
*Researched: 2026-01-27*
