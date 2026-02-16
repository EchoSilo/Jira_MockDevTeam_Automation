# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Jira Team Simulator - a multi-agent system that generates realistic development team activity in Jira for productivity analytics testing. Simulates 9 agents across 2 teams performing actions like status transitions, comments, story creation, and work logging.

## Common Commands

```bash
# Backend setup
pip install -r requirements.txt

# Run backend locally
uvicorn src.main:app --reload

# Run tests
pytest tests/ -v

# Frontend setup
cd frontend
npm install

# Run frontend dev server
npm run dev

# Build frontend for production
npm run build

# Build and run entire stack with Docker
docker-compose up --build
```

## Docker Deployment

The application runs in Docker in production. **After making code changes, you must rebuild and restart the container:**

```bash
# Rebuild and restart (recommended after code changes)
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Quick restart (if only config changes, no code)
docker-compose restart

# View logs
docker-compose logs -f jira-simulator
```

The Docker build includes both frontend (built during image creation) and backend. Changes to `src/`, `frontend/src/`, or `config/` require a rebuild.

## Architecture

```
                                    ┌─────────────────────┐
                                    │  React Frontend     │
                                    │  (Dashboard, Chat)  │
                                    └──────────┬──────────┘
                                               │ HTTP
                                               ↓
n8n (cron scheduler) → POST /trigger → FastAPI Backend
                                               │
                               ┌───────────────┼───────────────┐
                               ↓               ↓               ↓
                        BusinessHours    ChaosEngine    TickExecutor
                         Validator          ↓               │
                               │      RandomEvents     ┌────┴────┐
                               │           ↓           ↓         ↓
                               │    ScenarioAdapter  Scheduler  Reconciliation
                               │           ↓           ↓         ↓
                               └───────────┴───────────┴─────────┘
                                               │
                                         Agents (Crews)
                                               ↓
                                          JiraClient
                                               ↓
                                          Jira API
                                               │
                          ┌────────────────────┴────────────────────┐
                          ↓                                         ↓
                  data/state.json                         data/scheduler.db
                  (simulation state)                    (scheduled actions)
```

**Frontend to Backend:**
- React frontend at `http://localhost:5173` (dev) or served from backend in production
- REST API calls to backend (`http://localhost:8000/api/*`)
- 15-second polling for real-time dashboard updates
- WebSocket for interactive chat features

**Key Execution Flow:**
1. n8n triggers `/trigger` endpoint on schedule (every ~45 min, M-F, 9-5)
2. **Business Hours Gate**: Validates request occurs during configured business hours (FastAPI dependency)
3. **Clock**: Advances simulation time via injectable Clock abstraction (RealClock/FakeClock)
4. **Chaos Engine**: Rolls dice for random events (urgent bugs, team absence, blockers)
5. **Scenario Adapter**: Modifies active scenarios based on chaos events
6. **Scheduler**: Retrieves due actions from priority queue (heapq) within 30-min execution window
7. **Reconciliation**: Pre-execution validation checks Jira state matches expectations
8. **TickExecutor**: Executes 2-5 actions with reconciliation strategies (PROCEED/SKIP/CANCEL/RECALCULATE)
9. **Pathfinding**: On status divergence, recalculates optimal workflow path
10. Agents use `JiraClient` for API calls and `LLMService` for generating content

**Core Modules:**

| Module | Purpose |
|--------|---------|
| `src/time/` | Clock protocol (RealClock/FakeClock), business hours validation, DST detection |
| `src/scheduling/` | Scheduled actions, priority queue, SQLite persistence, business hours scheduler |
| `src/planning/` | Sprint planning, velocity tracking, capacity-based backlog selection |
| `src/orchestrator/` | TickExecutor (replaces immediate execution with scheduled execution) |
| `src/reconciliation/` | Pre-execution validation, ReconciliationEngine, adaptation strategies |
| `src/chaos/` | Random event generation, scenario adaptation, PathfindingAdapter |
| `src/monitoring/` | HeartbeatMonitor, DynamicChaosTuner, PerTicketCircuitBreaker |
| `src/agents/` | Agent classes (PM, Developer, QA, TechLead) |
| `src/crews/` | CrewAI integration for agent execution |
| `src/services/` | JiraClient, LLMService |
| `src/state/` | SimulationState models, state persistence |

**Agent hierarchy:**
- `BaseAgent` (abstract): Common interface with `should_act()`, `act()`, template selection
- `PMAgent`: Creates stories, prioritizes backlog, plans sprints
- `DeveloperAgent`: Picks up tasks, transitions status, logs work
- `QAAgent`: Tests tickets, files bugs, rejects/approves work
- `TechLeadAgent`: Architectural reviews, code review comments

**LLM routing:**
- `LLMService` routes to Haiku (routine actions) or Sonnet (complex actions like story creation)
- Complex actions defined in `config/settings.yaml` under `llm.complex_actions`

**Process Adherence:**
- Issue type permissions: Devs/QA/Tech Leads work on Stories, Bugs, Tasks only. Epics are PM-only.
- Sprint integration: Items must be in active sprint to be worked on (Board ID: 4)
- Epic lifecycle: Epic status syncs with children; Epics auto-assigned to team PMs
- Sprint planning: PMs plan 7-day sprints on Wednesdays; maintains 2-3 future sprints
- Violation cleanup: Gradually fixes process violations with explanatory comments

## Scheduling & Event System

**Scheduled Actions:**
- Actions are scheduled with calendar timestamps (not executed immediately)
- 30-minute execution window per action
- Priority queue (heapq) orders by scheduled_time
- SQLite persistence (`data/scheduler.db`) survives restarts
- Weekend skipping: Friday PM → Monday AM

**Action Status Flow:**
```
PENDING → READY → COMPLETED
              ↘ SKIPPED (overdue/invalid)
              ↘ ADAPTED (reconciliation changed plan)
```

**Sprint Planning:**
- PM agents plan 2-3 sprints ahead (planning horizon)
- Velocity tracking from last 3 sprints for capacity calculation
- Automatic planning triggers when horizon < 2 sprints
- Wednesday start, Tuesday end, 7-day cadence

## State Reconciliation

**Pre-Execution Validation:**
- Checks Jira ticket status matches expected state before action execution
- Detects manual changes, external modifications, and state drift

**Reconciliation Strategies:**
| Strategy | When Used | Effect |
|----------|-----------|--------|
| PROCEED | State matches expectations | Execute action normally |
| SKIP | Minor divergence, action no longer relevant | Mark action skipped, continue |
| CANCEL | Ticket moved out of sprint/reassigned | Cancel remaining scenario actions |
| RECALCULATE | Status diverged significantly | Invoke PathfindingAdapter for new path |
| RESCHEDULE | Temporary blocker | Reschedule action for later |

**Pathfinding:**
- When status diverges, WorkflowPathfinder calculates new path to target status
- PathfindingAdapter schedules new actions based on recalculated path

## Chaos Injection

**Random Events:** Generated each tick based on configurable probabilities
- `urgent_bug`: Inserts bug fix actions
- `production_outage`: Pauses scenario work
- `team_absence`: Reassigns actions to other agents
- `external_blocker`: Extends timelines
- `priority_change`: Reorders backlog items
- `scope_change`: Modifies story requirements

**Scenario Adaptation:**
- ScenarioAdapter modifies active scenarios based on chaos events
- ConfidenceTracker monitors scenario completion probability
- "Accept reality" at <70% confidence + 3 consecutive overrides

## Performance & Reliability

**Circuit Breakers:**
- PerTicketCircuitBreaker: 3 consecutive failures opens breaker
- Prevents infinite retry loops on problematic tickets

**Timeouts:**
- 10 seconds per action
- 45 seconds total per tick
- Max 4 actions per tick

**Monitoring:**
- HeartbeatMonitor: Alerts on tick gaps > 67 minutes
- DynamicChaosTuner: Adjusts chaos probabilities based on sprint health
- Sprint completion < 60% reduces chaos by 20%

## Detailed Architecture Reference

**IMPORTANT:** For complex debugging, feature development, or understanding execution flow, refer to `ARCHITECTURE.md`. It contains:

- **Execution Flow Diagrams**: Step-by-step sequence of `/trigger` endpoint
- **State Machine Diagrams**: Sprint lifecycle, scenario phase transitions
- **Dependency Graph**: What depends on what for correct operation
- **Critical Invariants**: Conditions that must always be true
- **Known Edge Cases**: Common failure scenarios and their causes
- **Quick Debugging Reference**: Checklist for common issues

Always consult `ARCHITECTURE.md` when:
- Modifying sprint lifecycle logic
- Changing state synchronization
- Debugging "state out of sync" issues
- Adding new detection/completion mechanisms

## Configuration

- `config/settings.yaml`: Simulation parameters, LLM models, action weights, cycle times, chaos probabilities
- `config/personas.yaml`: Agent definitions with Jira account IDs, personas, behaviors
- `config/templates.yaml`: Comment templates for routine actions (reduces LLM costs)

**Key settings.yaml sections:**
```yaml
schedule:
  days: [1, 2, 3, 4, 5]  # Monday-Friday (ISO 8601)
  start_hour: 9
  end_hour: 17
  timezone: "America/New_York"

sprint:
  duration_days: 7
  start_day: "Wednesday"  # Wed start, Tue end
  planning_horizon: 3     # Maintain 2-3 future sprints

random_events:
  enabled: true
  urgent_bug_probability: 0.10
  team_absence_probability: 0.05
  external_blocker_probability: 0.03
  # ... other event types

performance:
  max_actions_per_tick: 4
  action_timeout_seconds: 10
  tick_timeout_seconds: 45
```

## Environment Variables

Required in `.env`:
```
JIRA_URL=https://yoursite.atlassian.net
JIRA_EMAIL=your-email@domain.com
JIRA_API_TOKEN=your-api-token
PROJECT_KEY=YOUR_PROJECT_KEY
ANTHROPIC_API_KEY=your-anthropic-api-key
```

## API Endpoints

### Simulation Control

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check and Jira connectivity |
| `/trigger` | POST | Run one simulation tick (business hours validated) |
| `/state` | GET | View current simulation state |
| `/reset` | POST | Reset simulation state |
| `/sync-reset` | POST | Sync state with Jira and reset discrepancies |
| `/plan-sprint` | POST | Manually trigger sprint planning |

### Agent & Activity

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/agents` | GET | List configured agents with status |
| `/scenarios` | GET | List active scenarios |
| `/scenario/current` | GET | Get current scenario details |
| `/chat` | POST | Send chat message to PM agent |

### Sprint & Release Data

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sprint-data` | GET | Current sprint metrics and progress |
| `/api/assignment-trends` | GET | Assignment trend data for charts |
| `/api/releases/versions` | GET | List Jira versions |
| `/api/releases/versions/{name}/progress` | GET | Version completion progress |
| `/api/releases/versions/{name}/issues` | GET | Issues in version |
| `/api/releases/history` | GET | Release notes history |
| `/api/releases/{version}/download/{format}` | GET | Download release notes |
| `/api/releases/{version}/generate-notes` | POST | Generate release notes |

### Frontend Integration

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/dashboard` | GET | Combined data for dashboard (state + agents + scenarios) |
| `/api/dashboard?team=alpha` | GET | Filter by team (alpha or beta) |
| `/ws/chat` | WebSocket | Chat interface with PMs |

## Frontend

**Location:** `frontend/` directory

**Tech Stack:**
- React 19 with TypeScript
- Vite for bundling
- TailwindCSS + Radix UI for styling
- Zustand for state management
- Recharts for visualizations
- React Router for navigation

**Key Directories:**
- `src/pages/` - Page components (Dashboard, Chat, Settings)
- `src/components/` - Reusable components (common, dashboard, chat)
- `src/store/` - Zustand stores (theme, dashboard, chat)
- `src/hooks/` - Custom hooks for data fetching
- `src/lib/` - Utilities and transformers

**Running Frontend:**
```bash
cd frontend
npm install           # First time only
npm run dev          # Dev server at http://localhost:5173
npm run build        # Production build
npm run lint         # Check code quality
```

**Features:**
- Real-time dashboard with 15s auto-refresh
- Interactive PM chat interface
- Team filtering (Alpha/Beta)
- Light/dark theme support
- Responsive design
- Error boundaries for backend unavailability

## State Management

**Dual Persistence Model:**

| File | Purpose | Format |
|------|---------|--------|
| `data/state.json` | Simulation state (agents, scenarios, sprints) | JSON |
| `data/scheduler.db` | Scheduled actions queue | SQLite |

**state.json tracks:**
- Last run timestamp, current sprint info
- Per-agent: last action time, daily action count, assigned tickets
- Active scenarios with phases and action scripts
- Planning horizon (2-3 future sprint plans)
- Velocity history for capacity calculation
- Recent actions log

**scheduler.db tracks:**
- Scheduled actions with timestamps and execution windows
- Action status (PENDING/READY/COMPLETED/SKIPPED/ADAPTED)
- Preconditions for reconciliation (expected_status, expected_assignee)
- Execution results and timing

**Time Handling:**
- All timestamps are timezone-aware UTC (Pendulum library)
- Injectable Clock protocol (RealClock for production, FakeClock for tests)
- Business hours validation at API boundary (configurable in settings.yaml)
- DST transitions detected and logged

State resets daily counters and advances sprint day automatically on new day detection.

## Testing

**Clock Abstraction Pattern:**
- Use `FakeClock` (from `src/time/clock.py`) for deterministic tests
- Inject clock via constructor, never call `datetime.now()` directly
- All time operations use Pendulum for timezone-aware UTC

```python
# Test example
from src.time.clock import FakeClock
import pendulum

def test_business_hours():
    clock = FakeClock(pendulum.parse("2026-01-28 10:00:00", tz="America/New_York"))
    executor = TickExecutor(clock=clock, ...)
    # clock.advance(hours=2) to move time forward
```

**Test Files:**
- `tests/test_tick_executor.py`: Scheduled execution tests
- `tests/test_pathfinding_*.py`: Pathfinding and reconciliation
- `tests/test_scheduler.py`: Priority queue and scheduling
- `tests/test_chaos_*.py`: Chaos injection and adaptation

**Running Tests:**
```bash
pytest tests/ -v                              # All tests
pytest tests/test_pathfinding_integration.py  # Integration tests
pytest tests/ -k "scheduler"                  # Pattern match
```
