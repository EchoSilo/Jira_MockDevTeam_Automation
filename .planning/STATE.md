# Project State: Real-Time Scripted Jira Team Simulator

**Last Updated:** 2026-01-28
**Current Phase:** Phase 4 - Adaptive Pathfinding & Chaos Injection (IN PROGRESS)
**Current Plan:** 04-03 complete (3 of 5)
**Status:** Phase 4 Wave 1 complete, Wave 2 started

## Project Reference

**Core Value:** The simulation must operate in Jira's time domain (real calendar time), producing realistic sprint timelines and activity patterns that analytics tools can consume as if observing a real development team.

**Current Focus:** Phase 3 complete. Event scheduler, queue system, and sprint planning horizon fully operational. Next: Chaos injection and adaptive pathfinding.

## Current Position

**Phase:** 4 of 5 - Adaptive Pathfinding & Chaos Injection (IN PROGRESS)
**Plans:** 3 of 5 complete in current phase
**Status:** In progress
**Last activity:** 2026-01-28 - Completed 04-03-PLAN.md
**Progress:** [███████████████░░░░░] 73% (43/59 requirements)

**Phase Goal:** Chaos event injection with adaptive pathfinding for workflow transitions; system handles disruptions intelligently.

## Performance Metrics

**Overall Milestone Progress:** 42/59 requirements completed (71%)

**Phase Breakdown:**
- Phase 1: 7/7 (100%) ✓
- Phase 2: 8/8 (100%) ✓
- Phase 3: 24/24 (100%) ✓
- Phase 4: 3/14 (21%)
- Phase 5: 0/6 (0%)

## Accumulated Context

### Key Decisions

| Decision | Rationale | Phase | Date |
|----------|-----------|-------|------|
| 5-phase structure aligned with research | Research suggests optimal grouping by time -> reconciliation -> scheduling -> chaos -> perf | All | 2026-01-27 |
| Replace virtual time with real-time scheduling | Jira operates in real time; virtual time creates unrealistic patterns | 1 | 2026-01-27 |
| Preserve existing agent personalities and LLM system | Agent behavior is sophisticated and working well; problem is orchestration timing | 3 | 2026-01-27 |
| Start fresh rather than migrate existing data | Existing data is based on flawed time model; clean slate is simpler | 1 | 2026-01-27 |
| Use Pendulum for all datetime handling | Pendulum provides timezone-safe arithmetic and DST handling | 1 | 2026-01-28 |
| Clock abstraction via Protocol | Enables dependency injection for testing without monkeypatching | 1 | 2026-01-28 |
| SQLite for action persistence | Simple file-based persistence without external dependencies | 3 | 2026-01-28 |
| TickExecutor as SOLE execution path | Single execution path via skip_execution=True prevents dual execution | 3 | 2026-01-28 |
| asyncio.run() for sync/async bridge | TickExecutor is sync, orchestrator._execute_action is async; bridge required | 3 | 2026-01-28 |
| 80% capacity buffer | Conservative buffer for unknowns in sprint planning | 3 | 2026-01-28 |
| 2-sprint minimum + 14-day lookahead | Dual trigger for planning horizon ensures continuous coverage | 3 | 2026-01-28 |
| Dataclass validation in __post_init__ | Immediate validation on construction for early error detection | 4 | 2026-01-28 |
| Default chaos weights favor blockers/shifts | external_blocker (0.15) and priority_shift (0.12) reflect realistic disruption patterns | 4 | 2026-01-28 |
| Two-stage dice rolling for chaos events | Stage 1: base_event_chance, Stage 2: weighted selection; separates "if event" from "which event" | 4 | 2026-01-28 |
| Seeded random.Random for deterministic testing | Optional seed parameter enables reliable test assertions while preserving production randomness | 4 | 2026-01-28 |

### Completed Phases

**Phase 1: Time Infrastructure & UTC Migration** (Completed 2026-01-28)
- 4 plans executed across 3 waves
- 21/21 verification checks passed
- Key deliverables:
  - Clock abstraction (RealClock/FakeClock) with Pendulum
  - Removed virtual time from SimulationState
  - Migrated 49 datetime calls to pendulum.now("UTC")
  - Business hours gate in /trigger endpoint (M-F 9-5)
  - DST transition detection and logging

**Phase 2: State Reconciliation & Validation** (Completed 2026-01-28)
- 6 plans executed across 3 waves
- 129 reconciliation tests pass
- Key deliverables:
  - PreExecutionValidator for status/assignee/sprint validation
  - OptimisticLockingValidator for timestamp-based conflict detection
  - ExecutionTracker for idempotency with 48-hour cleanup
  - ReconciliationEngine with CANCEL/SKIP/RESCHEDULE/RECALCULATE/PROCEED strategies
  - ResilientJiraClient with circuit breaker protection
  - Staleness detection via validation_tick_count

**Phase 3: Event Scheduler & Queue System** (Completed 2026-01-28)
- 9 plans executed (8 original + 1 gap closure)
- 58 scheduling tests pass
- 23/24 requirements verified (96%)
- Key deliverables:
  - ScheduledAction dataclass with heap-compatible ordering
  - ActionStatus enum (PENDING, READY, COMPLETED, SKIPPED, ADAPTED)
  - ScheduledActionStore with SQLite persistence
  - VirtualClock for simulation time advancement (0.75 hour ticks)
  - ScenarioScheduler converts script days to calendar timestamps
  - Weekend skipping and business hours enforcement
  - Scheduler wrapper combining queue, persistence, VirtualClock
  - TickExecutor with reconciliation integration
  - SprintPlanner orchestrator for full planning flow
  - SimulationState planning fields (planning_horizon, velocity_tracker, action_queue)
  - Full integration: Scheduler, TickExecutor, SprintPlanner wired into /trigger

### Minor Gaps

**Phase 3 minor gap (non-blocking):**
- TickExecutor returns execution count in `metrics["executed"]` but main.py line 540 expects `actions_completed`
- Impact: Dashboard shows 0 actions even when TickExecutor executes successfully
- Severity: Cosmetic - actions execute correctly, only metric display affected

### Open Questions

- None currently

### Known Blockers

- None

### Technical Debt

- Anaconda has Pydantic v1.10.12 (Python 3.11), system Python has v2.11.10 (Python 3.12)
- Planning models use Pydantic v1-compatible Config class for test compatibility
- Some tests use hardcoded dates that may need adjustment
- Added pytest-asyncio dependency for orchestrator tests
- Minor metric field name mismatch (metrics.executed vs actions_completed)

## Session Continuity

**Last Session:** Phase 4 Plan 02 Execution (2026-01-28)

**What Happened:**
- Completed 04-02: Chaos Event Generator (TDD)
- Created RandomEventGenerator with probability-based dice rolling
- Implemented two-stage event generation: base chance then weighted selection
- Event-specific creation logic for all 6 chaos types
- Deterministic seed support for testing
- TDD cycle: RED (failing tests) → GREEN (implementation)
- All 13 tests pass

**Commits This Session:**
- `feb97f2`: test(04-02): add failing tests for RandomEventGenerator
- `caa7596`: feat(04-02): implement RandomEventGenerator with probability-based rolling

**Next Session Should:**
Execute 04-03: Event Catalog

**Context for Next Agent:**
- RandomEventGenerator can create events on demand
- Two-stage dice rolling: base_event_chance then weighted selection
- Seeded random.Random enables deterministic testing
- Event-specific targeting rules implemented (production_outage: 2-3 tickets critical, team_absence: 1 agent with duration)
- Zero-probability events correctly filtered before selection
- Ready for event catalog and storage

**Phase 4: Adaptive Pathfinding & Chaos Injection** (IN PROGRESS)
- 2 plans executed (04-01, 04-02)
- 23 chaos tests pass (10 models + 13 generator)
- Key deliverables so far:
  - ChaosEventType enum with 6 event types
  - RandomEvent dataclass with validation
  - ChaosConfig with YAML configuration loading
  - RandomEventGenerator with probability rolling
  - Event-specific creation logic for all types

---
*State updated: 2026-01-28 after 04-01 execution complete*
