# Real-Time Scripted Jira Team Simulator

## What This Is

A multi-agent system that simulates realistic Agile development team activity in a real Jira project by planning scenarios 2-3 sprints ahead and executing them in real-time (not virtual time). The system creates scripted scenarios with specific actions scheduled to real wall-clock timestamps, reconciles with actual Jira state before execution, and adapts when random disruptions occur.

## Core Value

The simulation must operate in Jira's time domain (real calendar time), producing realistic sprint timelines and activity patterns that analytics tools can consume as if observing a real development team.

## Requirements

### Validated

<!-- Existing capabilities proven valuable in current implementation -->

- ✓ Multi-agent personality system with LLM-driven content generation — existing
- ✓ CrewAI orchestration for complex multi-agent scenarios — existing
- ✓ Jira API integration for creating/updating issues, managing sprints — existing
- ✓ React dashboard with real-time activity monitoring — existing
- ✓ LLM routing (Sonnet for complex, Haiku for routine actions) — existing
- ✓ Comprehensive logging and observability (logs.db, token tracking) — existing
- ✓ Scenario-driven execution with state machines (blocker, rework, scope_creep) — existing
- ✓ Sprint lifecycle management (creation, activation, completion) — existing

### Active

<!-- Current scope for this milestone: Real-time transformation -->

#### Core Time Model Transformation
- [ ] **TIME-01**: Remove virtual time advancement (`simulation_time`, `tick_duration_hours`)
- [ ] **TIME-02**: Ticks operate in real wall-clock time (check "what's due NOW?")
- [ ] **TIME-03**: Actions scheduled to real timestamps within 30-minute execution windows
- [ ] **TIME-04**: Business hours enforcement (M-F, 9am-5pm, configurable timezone)
- [ ] **TIME-05**: 7-day sprints match 7 real calendar days (Wednesday start, Tuesday end)

#### Scenario Planning & Scheduling
- [ ] **PLAN-01**: Maintain 2-3 sprint planning horizon at all times
- [ ] **PLAN-02**: Convert SprintScenario scripts to ScheduledActions with real timestamps
- [ ] **PLAN-03**: Schedule actions across business days, skip weekends
- [ ] **PLAN-04**: Enhanced PM agent can prioritize backlog using velocity and release goals
- [ ] **PLAN-05**: PM agent selects sprint content based on capacity and priorities
- [ ] **PLAN-06**: Track historical velocity (last 3 sprints average) for capacity planning

#### Jira Reconciliation
- [ ] **RECON-01**: Check preconditions against actual Jira state before executing actions
- [ ] **RECON-02**: Detect discrepancies (ticket status, assignee, sprint membership)
- [ ] **RECON-03**: Adapt or skip actions when Jira state doesn't match expectations
- [ ] **RECON-04**: Log reconciliation notes for observability

#### Random Event System
- [ ] **EVENT-01**: Generate random events (outages, urgent bugs, absences, blockers) based on configurable probabilities
- [ ] **EVENT-02**: Adapt active scenarios when random events occur
- [ ] **EVENT-03**: Insert/modify scheduled actions in response to events
- [ ] **EVENT-04**: Support granular chaos level configuration (per-event probabilities)

#### Execution Engine
- [ ] **EXEC-01**: Tick executor fetches actions ready for current time window
- [ ] **EXEC-02**: Execute actions via existing CrewAI crews (preserve agent behavior)
- [ ] **EXEC-03**: Mark actions as completed/skipped/adapted with timestamps
- [ ] **EXEC-04**: Handle overdue actions (past execution window)

#### State Management
- [ ] **STATE-01**: ActionQueue model to store scheduled actions
- [ ] **STATE-02**: PlanningHorizon model to track planned sprints
- [ ] **STATE-03**: Persist scheduled actions and planning state to data/state.json
- [ ] **STATE-04**: Trigger sprint planning when horizon drops below 2 future sprints

### Out of Scope

- Changing agent personalities or LLM-driven comment generation — existing system is sophisticated and working well
- Migrating existing Jira data — start fresh with proper real-time scheduling
- Real-time UI updates during action execution — existing 15s polling is sufficient
- Historical analytics dashboard — focus on simulation, not retrospective analysis
- Multiple timezone support — single configurable timezone is adequate
- Fixed-cadence or continuous releases — feature-based releases (PM decides) only

## Context

**Problem Being Solved:**
The current simulation operates in "virtual time" where each tick advances `simulation_time` by 4 hours (5.33x speedup). This causes 7-day sprints to complete in ~1.3 real days, producing compressed, unrealistic patterns in Jira. Analytics tools see sprints that appear to happen impossibly fast, with tickets transitioning through states in minutes rather than hours or days.

**Root Cause:**
Time domain mismatch. Jira operates in real calendar time (timestamps are wall-clock), but the simulation tried to fast-forward through time for testing convenience. The system needs to experience time like a real Agile team, not manipulate it.

**Technical Environment:**
- **Backend**: Python 3.11+, FastAPI, CrewAI, Anthropic Claude (Sonnet 4.5 / Haiku 3.5)
- **Frontend**: React 19, TypeScript, Vite, TailwindCSS, Zustand
- **External APIs**: Jira Cloud REST API, Anthropic API
- **Storage**: JSON state files (`data/state.json`), SQLite logs (`data/logs.db`)
- **Deployment**: Docker Compose (backend + frontend), triggered by n8n cron (every 15-45 min, M-F, 9-5)

**Existing Architecture Strengths to Preserve:**
- Multi-layered architecture (Presentation → API → Orchestration → Analysis → Planning → Execution → Services)
- Sophisticated agent system with personas and LLM routing
- Scenario state machines (normal_flow, blocker, rework, scope_creep, dependency)
- CrewAI crews for multi-agent coordination
- Comprehensive logging and observability

**Known Issues Being Addressed:**
- Sprint timelines compressed by 5.33x
- Activity patterns unrealistic (too much happening too fast)
- Analytics see impossible velocity and cycle times
- No reconciliation with actual Jira state (assumes script executes perfectly)
- No realistic disruptions or randomness beyond scenario scripts

## Constraints

- **Tech Stack**: Must use existing Python/FastAPI backend, React frontend, CrewAI orchestration — No complete framework rewrites
- **Jira Integration**: Must work with existing Jira Cloud project, respect Jira permissions and workflows
- **LLM Costs**: Continue using Haiku for routine actions, Sonnet for complex decisions — Cost optimization matters
- **Deployment Model**: Must run in Docker triggered by n8n cron — No persistent websocket connections or long-running processes
- **Business Hours**: Simulation actions only during configurable business hours (default M-F 9am-5pm) — Matches real team availability
- **Sprint Cadence**: 7-day sprints, Wednesday start, Tuesday end — Matches established pattern in plan
- **Backward Compatibility**: Start fresh, no requirement to migrate existing simulation state — Clean slate acceptable

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Replace virtual time with real-time scheduling | Jira operates in real time; virtual time creates unrealistic patterns | — Pending |
| Preserve existing agent personalities and LLM system | Agent behavior is sophisticated and working well; problem is orchestration timing | — Pending |
| Start fresh rather than migrate existing data | Existing data is based on flawed time model; clean slate is simpler | — Pending |
| Random events config-only (not runtime API) | Fully autonomous after startup; simplifies implementation | — Pending |
| Fully customizable chaos level (granular probabilities) | Maximum flexibility for different simulation scenarios | — Pending |
| 30-minute execution window for scheduled actions | Balances precision with n8n tick frequency (15-45 min intervals) | — Pending |

---
*Last updated: 2026-01-27 after initialization*
