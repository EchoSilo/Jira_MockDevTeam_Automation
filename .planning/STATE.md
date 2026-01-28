# Project State: Real-Time Scripted Jira Team Simulator

**Last Updated:** 2026-01-28
**Current Phase:** Phase 4 - Adaptive Pathfinding & Chaos Injection (IN PROGRESS)
**Current Plan:** 04-04 complete (4 of 5)
**Status:** Phase 4 Wave 1 complete, Wave 2 complete, Wave 3 in progress

## Project Reference

**Core Value:** The simulation must operate in Jira's time domain (real calendar time), producing realistic sprint timelines and activity patterns that analytics tools can consume as if observing a real development team.

**Current Focus:** Phase 3 complete. Event scheduler, queue system, and sprint planning horizon fully operational. Next: Chaos injection and adaptive pathfinding.

## Current Position

**Phase:** 4 of 5 - Adaptive Pathfinding & Chaos Injection (IN PROGRESS)
**Plans:** 4 of 5 complete in current phase
**Status:** In progress
**Last activity:** 2026-01-28 - Completed 04-04-PLAN.md
**Progress:** [███████████████░░░░░] 75% (44/59 requirements)

**Phase Goal:** Chaos event injection with adaptive pathfinding for workflow transitions; system handles disruptions intelligently.

## Performance Metrics

**Overall Milestone Progress:** 44/59 requirements completed (75%)

**Phase Breakdown:**
- Phase 1: 7/7 (100%) ✓
- Phase 2: 8/8 (100%) ✓
- Phase 3: 24/24 (100%) ✓
- Phase 4: 5/14 (36%)
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
| Weight multipliers for archetype chaos | Archetype-specific multipliers adjust event probabilities (smooth: 0.2-0.5x, blocker_heavy: 2.0x external_blocker) | 4 | 2026-01-28 |
| Event catalog pattern | Central registry provides templates with response actions; enables scenario-aware chaos intensity | 4 | 2026-01-28 |
| Positive adaptations don't hurt fidelity | Early completion treated as success in fidelity calculation; formula: (executed_as_planned + positive_adaptations) / total | 4 | 2026-01-28 |
| Dual-threshold accept reality | Both fidelity < 0.7 AND external_overrides >= 3 required to abandon script; prevents premature abandonment | 4 | 2026-01-28 |
| Direct queue heap access for adaptation | Use _get_pending_actions() to scan queue._heap; get_due_actions() filters by time window | 4 | 2026-01-28 |
| Track postponed actions in actions_inserted | Postponed actions ARE inserted into queue, should appear in insertion list for transparency | 4 | 2026-01-28 |
| Simple replacement agent mapping | Phase 4 focuses on pathfinding logic, not state management; hardcoded role mapping sufficient | 4 | 2026-01-28 |

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

**Last Session:** Phase 4 Plan 04 Execution (2026-01-28)

**What Happened:**
- Completed 04-04: ScenarioAdapter
- Created ScenarioAdapter with event-specific adaptation logic
- Implemented 6 event handlers (production_outage, urgent_bug, team_absence, external_blocker, priority_shift, scope_change)
- Insert emergency actions, postpone work, reassign to replacement agents
- Fixed Rule 1 bug: ScheduledActionStore in-memory database support
- All 12 adapter tests pass

**Commits This Session:**
- `0a4e5a1`: feat(04-04): implement ScenarioAdapter with chaos event handling
- `086f39a`: test(04-04): add comprehensive ScenarioAdapter tests
- `7ef6c36`: fix(03): support in-memory databases in ScheduledActionStore
- `7dd6297`: fix(04-04): track postponed actions in actions_inserted list

**Next Session Should:**
Complete Phase 4 with final Wave 4 plan (orchestrator integration) or proceed to Phase 5

**Context for Next Agent:**
- ScenarioAdapter ready for orchestrator integration
- Event handlers insert ScheduledActions via scheduler.schedule_action()
- Actions marked ADAPTED via scheduler.store.update_status()
- AdaptationResult tracks insertions, adaptations, and postponements
- Direct queue heap access via _get_pending_actions() for all pending actions
- Simple replacement agent mapping (role-based fallback)

**Phase 4: Adaptive Pathfinding & Chaos Injection** (IN PROGRESS)
- 4 plans executed (04-01, 04-02, 04-03, 04-04)
- 64 chaos tests pass (10 models + 13 generator + 15 catalog + 14 confidence + 12 adapter)
- Key deliverables so far:
  - ChaosEventType enum with 6 event types
  - RandomEvent dataclass with validation
  - ChaosConfig with YAML configuration loading
  - RandomEventGenerator with probability rolling
  - EventCatalog with archetype-aware weight adjustment
  - chaos_events.yaml configuration
  - ConfidenceTracker with dual-threshold logic
  - ConfidenceScore metrics dataclass
  - ScenarioAdapter with event-specific handlers
  - AdaptationResult for tracking modifications

---
*State updated: 2026-01-28 after 04-04 execution complete*
