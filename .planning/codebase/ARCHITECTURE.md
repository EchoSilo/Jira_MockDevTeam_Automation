# Architecture

**Analysis Date:** 2026-01-27

## Pattern Overview

**Overall:** Multi-layered scenario-driven simulation architecture using CrewAI orchestration

**Key Characteristics:**
- **Scenario-driven execution**: Tracks active scenarios through defined state machines (normal_flow, blocker, rework, scope_creep, dependency)
- **Three-phase tick cycle**: Analyze → Plan → Execute → Update
- **LLM-driven decisions**: Sonnet (complex) and Haiku (routine) models route decisions based on action complexity
- **State persistence**: JSON-based state file maintains simulation continuity between API calls
- **CrewAI crews**: Specialized teams of agents handle different scenario types (TicketLifecycleCrew, BlockerCrew, ReworkCrew, etc.)
- **Dual dashboard**: Real-time frontend (React 19) + backend API exposing simulation state

## Layers

**Presentation Layer:**
- Purpose: Real-time dashboard UI and interactive interfaces
- Location: `frontend/src/`
- Contains: React components, Zustand stores, API hooks, type definitions
- Depends on: Backend REST API (`/api/*` endpoints) and WebSocket (`/ws/chat`)
- Used by: End users viewing simulation metrics, team status, release notes

**API/FastAPI Layer:**
- Purpose: HTTP interface for frontend, state exposure, scenario management
- Location: `src/main.py` (entry point), endpoints exposed as GET/POST
- Contains: Route handlers, health checks, trigger endpoint, dashboard data endpoints
- Depends on: Orchestrator, JiraClient, state management, logging writer
- Used by: Frontend polling (15s), n8n cron scheduler, external integrations

**Orchestration Layer:**
- Purpose: Coordinate simulation ticks through analyzer → planner → executor cycle
- Location: `src/orchestrator/orchestrator.py`
- Contains: ScenarioOrchestrator class managing the full workflow
- Depends on: Analyzer, Planner, Crews, JiraTools, JiraClient, LLMService
- Used by: `/trigger` endpoint during each simulation tick

**Analysis Layer:**
- Purpose: Rules-based detection of opportunities and board state assessment
- Location: `src/orchestrator/analyzer.py`
- Contains: ScenarioAnalyzer class identifying pick-up items, scenario advancement opportunities
- Depends on: JiraClient, SimulationState, settings config
- Used by: ScenarioOrchestrator.run_tick() phase 1

**Planning Layer:**
- Purpose: LLM-driven decision making on which actions to execute
- Location: `src/orchestrator/planner.py`
- Contains: ScenarioPlanner class generating action lists with Sonnet reasoning
- Depends on: LLMService, SimulationState, SprintScenario, ReleaseDirective
- Used by: ScenarioOrchestrator.run_tick() phase 2

**Execution Layer (Crews):**
- Purpose: Execute planned actions through CrewAI agent teams
- Location: `src/crews/`
- Contains: Multiple crew classes (TicketLifecycleCrew, BlockerCrew, ReworkCrew, ScopeCreepCrew, DependencyCrew, SprintPlanningCrew)
- Depends on: JiraTools, LLMService, persona configs, active scenarios
- Used by: ScenarioOrchestrator._execute_action() during phase 3

**State Management Layer:**
- Purpose: Persist and manage simulation state across ticks
- Location: `src/state/`
- Contains: SimulationState (Pydantic model), ActiveScenario, AgentState, SprintScenario
- Depends on: JSON persistence (`data/state.json`), scenario models
- Used by: All layers for state queries and updates

**Service Layer:**
- Purpose: Provide external integrations (Jira, LLM, logging)
- Location: `src/services/`
- Contains: JiraClient (Jira REST API wrapper), LLMService (LLM routing and content generation)
- Depends on: External APIs (Jira Cloud, Anthropic)
- Used by: Orchestrator, Crews, Analyzer for actual work execution

**Tools Layer:**
- Purpose: Provide high-level Jira operations to CrewAI agents
- Location: `src/tools/`
- Contains: JiraTools (wrapped Jira operations), ContextTools
- Depends on: JiraClient, logging integration
- Used by: CrewAI agents within each crew

**Logging Layer:**
- Purpose: Comprehensive observability across LLM calls, Jira API calls, events
- Location: `src/logging/`
- Contains: AsyncLogWriter, LogDatabase, CrewAI callbacks, logged wrappers
- Depends on: SQLite database (`data/logs.db`), state tracking
- Used by: All layers for instrumentation and debugging

## Data Flow

**Per-Tick Flow:**

1. **Tick Initiation** (`/trigger` endpoint)
   - Load current state from `data/state.json`
   - Initialize virtual clock if missing
   - Inject active Jira sprint data into state
   - Detect sprint transitions (e.g., Sprint 7 → Sprint 8)
   - Check for new simulation day, advance if needed

2. **Analysis Phase**
   - ScenarioAnalyzer.analyze() → board snapshot
   - Identify tickets in To Do, In Progress, Code Review, Testing statuses
   - Detect opportunities: pick-up items, advance opportunities for active scenarios
   - Build workflow graph for pathfinding
   - [Optional] Run Release Management coordination phase

3. **Planning Phase**
   - ScenarioPlanner.plan_tick() receives analysis + state + intensity
   - Sonnet LLM generates action decisions with reasoning
   - Filters actions by permissions, workload, scenario balance
   - Validates against sprint membership requirements
   - Returns list of planned actions (max 5 per tick)

4. **Execution Phase** (per action)
   - Set logging context (agent, ticket, scenario)
   - Route to appropriate crew based on action type
   - Crew executes task: calls JiraTools → JiraClient → Jira API
   - Log result, errors, token usage
   - Clear context after execution

5. **State Update Phase** (per action)
   - Verify Jira operation succeeded (jira_success flag)
   - Update scenario phase based on action type (PICKED_UP → IN_PROGRESS → IN_REVIEW → IN_TESTING → COMPLETED)
   - Update agent state (assign/unassign tickets)
   - Record action to history
   - Complete scenario if terminal phase reached

6. **Tick Completion**
   - Advance simulation time by tick_duration_hours
   - Save updated state to disk
   - End logging session with stats
   - Return TriggerResponse with actions, errors, analysis summary

**State Management:**

- **Source of truth for sprint**: Jira active sprint (injected early in tick)
- **Source of truth for workflow**: Jira issue statuses (queried in analyzer)
- **Simulation-specific data**: Scenarios, agent workloads, action history (persisted in state.json)
- **Sync mechanism**: sync_state_with_jira() compares expected scenarios with actual Jira state, creates/completes scenarios as needed

## Key Abstractions

**ActiveScenario:**
- Purpose: Tracks progression of a single ticket through workflow with complexity, phase, rejection count
- Examples: `src/state/models.py` ActiveScenario class
- Pattern: State machine (PICKED_UP → IN_PROGRESS → IN_REVIEW → IN_TESTING → COMPLETED, with branch states for BLOCKED, REJECTED, etc.)

**SprintScenario:**
- Purpose: Tracks entire sprint with scripted events, mood progression, archetype (smooth_sprint, blocker_heavy, crunch_sprint, etc.)
- Examples: `src/scenarios/sprint_scenario.py` SprintScenario class
- Pattern: Script-driven execution - defines events per day, executes in sequence, tracks completion

**CrewAI Crew:**
- Purpose: Multi-agent team executing a specific scenario type (e.g., BlockerCrew for blocker scenarios)
- Examples: `src/crews/ticket_lifecycle_crew.py`, `src/crews/blocker_crew.py`
- Pattern: Each crew has tasks + agents, runs synchronously with callbacks for logging

**SimulationState:**
- Purpose: Central state object tracking agents, scenarios, recent actions, sprint info
- Examples: `src/state/models.py` SimulationState class
- Pattern: Pydantic model with helper methods (get_scenario_by_ticket, get_agent_state, record_action)

**ReleaseDirective:**
- Purpose: Instructions for PMs to create versions, assign to issues, release
- Examples: `src/state/models.py` ReleaseDirective class
- Pattern: Timestamped instructions tracked in release_state.active_directives

## Entry Points

**`/trigger` Endpoint:**
- Location: `src/main.py` (lines 356-493)
- Triggers: n8n cron scheduler (every ~45 min, M-F, 9-5)
- Responsibilities: Loads state, runs full tick cycle, saves state, returns summary
- Returns: TriggerResponse with actions taken, errors, analysis

**`/health` Endpoint:**
- Location: `src/main.py` (lines 341-353)
- Triggers: Frontend health check, n8n scheduler validation
- Responsibilities: Returns Jira connectivity status, last run time, simulation day
- Uses: CachedHealthCheck for 60-second TTL

**`/api/dashboard` Endpoint:**
- Location: Not fully shown but implied by `/state` and status endpoints
- Triggers: Frontend polling every 15 seconds
- Responsibilities: Returns combined state, sprint data, agents, scenarios
- Uses: CachedState for 5-second TTL to reduce file I/O

**FastAPI Application Lifespan:**
- Location: `src/main.py` (lines 231-266)
- Startup: Loads config (settings.yaml, personas.yaml, templates.yaml), initializes logging database
- Shutdown: Stops async log writer
- Used by: FastAPI to manage initialization and cleanup

## Error Handling

**Strategy:** Defensive with fallback chains and state consistency checks

**Patterns:**
- **Sprint validation**: Actions validate sprint membership before execution; auto-add to sprint if missing
- **Agent fallbacks**: If assigned agent unavailable, escalate through role-based fallback chain
- **State consistency**: Log jira_success flag; only update state if Jira operation succeeded (prevents state drift)
- **Exception catching**: Per-action try/except in orchestrator; collects errors in results list without stopping tick
- **Logging context isolation**: Set/clear context for each action to prevent cross-contamination

**Example (from orchestrator.py lines 589-603):**
```python
if action_type in self.sprint_required_actions and ticket_key:
    if not self._validate_sprint_requirement(ticket_key):
        # Try to auto-fix by adding to active sprint
        if self._auto_fix_sprint_membership(ticket_key):
            logger.info(f"Auto-added {ticket_key} to active sprint before {action_type}")
        else:
            return {
                "action_type": action_type,
                "ticket_key": ticket_key,
                "error": "Ticket not in active sprint and could not be added",
                "skipped": True,
                "reason": "sprint_violation",
            }
```

## Cross-Cutting Concerns

**Logging:** Comprehensive logging via AsyncLogWriter in `src/logging/`
- **CrewAI LLM calls**: CrewAILoggingCallback intercepts tokens, models, usage
- **Jira API calls**: LoggedJiraClient wraps JiraClient, logs endpoint + params
- **Orchestrator events**: _log_event() records phase transitions (tick_start, analyze, plan, action_result, tick_complete)
- **Session tracking**: Per-tick session with intensity, sprint context, stats aggregation

**Validation:** Permission-based action filtering in ScenarioPlanner
- **Issue type permissions**: Developers/QA work on Stories/Bugs/Tasks only; PMs own Epics
- **Sprint membership**: Work actions require active sprint membership
- **Agent availability**: Fallback chains ensure developers available for work

**Authentication:** Per-agent Jira authentication
- **JiraClient**: Single shared instance using simulator account credentials
- **Agent identity**: Track agent_id in logging context, record in action history
- **Credential sources**: Load from .env file (JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN)

---

*Architecture analysis: 2026-01-27*
