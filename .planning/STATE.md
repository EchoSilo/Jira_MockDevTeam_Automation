# Project State: Real-Time Scripted Jira Team Simulator

**Last Updated:** 2026-01-28
**Current Phase:** Phase 1: Time Infrastructure & UTC Migration
**Current Plan:** 01-03 completed (3 of 4)
**Status:** In progress - executing Phase 1 plans

## Project Reference

**Core Value:** The simulation must operate in Jira's time domain (real calendar time), producing realistic sprint timelines and activity patterns that analytics tools can consume as if observing a real development team.

**Current Focus:** Transform virtual-time simulation (5.33x speedup) to real-time calendar execution with pre-scripted scenarios spanning 2-3 sprints. Shift from reactive immediate execution to scheduled event queues with state reconciliation, chaos injection, and adaptive pathfinding.

## Current Position

**Phase:** 1 of 5 - Time Infrastructure & UTC Migration
**Plan:** 3 of 4 complete
**Status:** In Progress
**Last activity:** 2026-01-28 - Completed 01-03-PLAN.md (Clock injection & UTC migration)

**Progress:** [██████████████████░░] 75% (3/4 plans in phase)

**Phase Goal:** All time handling operates in timezone-aware UTC with business hours enforcement and DST-safe sprint calculations.

**Phase Requirements:**
- TIME-01: UTC timezone-aware datetime handling throughout codebase
- TIME-02: Virtual clock with injectable Clock abstraction (RealClock/FakeClock)
- TIME-03: Business hours gate in /trigger endpoint (M-F 9-5)
- TIME-04: DST transition detection and graceful handling
- TIME-05: Sprint cadence with Pendulum (Wednesday start, Tuesday end, 7 days)
- CONFIG-01: Remove simulation_time and tick_duration_hours from state
- CONFIG-05: Fresh state initialization (no virtual-time migration)

**Phase Success Criteria:**
1. Developer can set business hours schedule in settings.yaml and /trigger endpoint respects it (rejects requests outside M-F 9-5)
2. Developer can inject FakeClock in tests to freeze time and advance deterministically (no flaky time-dependent tests)
3. System detects DST transitions (spring forward, fall back) and logs warning without duplicate/skipped executions
4. Sprint start/end dates calculated with Pendulum match expected calendar dates (7 real days Wednesday-Tuesday)
5. All datetime comparisons use timezone-aware UTC (no naive datetime warnings in logs)

## Performance Metrics

**Overall Milestone Progress:** 0/59 requirements completed (0%)

**Phase Breakdown:**
- Phase 1: 0/7 (0%)
- Phase 2: 0/8 (0%)
- Phase 3: 0/24 (0%)
- Phase 4: 0/14 (0%)
- Phase 5: 0/6 (0%)

**Recent Velocity:** N/A (no phases completed yet)

## Accumulated Context

### Key Decisions

| Decision | Rationale | Phase | Date |
|----------|-----------|-------|------|
| 5-phase structure aligned with research | Research suggests optimal grouping by time → reconciliation → scheduling → chaos → perf | All | 2026-01-27 |
| Replace virtual time with real-time scheduling | Jira operates in real time; virtual time creates unrealistic patterns | 1 | 2026-01-27 |
| Preserve existing agent personalities and LLM system | Agent behavior is sophisticated and working well; problem is orchestration timing | 3 | 2026-01-27 |
| Start fresh rather than migrate existing data | Existing data is based on flawed time model; clean slate is simpler | 1 | 2026-01-27 |
| Use typing.Protocol for Clock interface | More flexible than ABC, enables structural subtyping | 01-01 | 2026-01-28 |
| Require timezone-aware datetimes in FakeClock | Prevents naive datetime bugs at construction/set_time | 01-01 | 2026-01-28 |
| Separate advance() from set_time() in FakeClock | Relative vs absolute time changes for clarity | 01-01 | 2026-01-28 |
| ConfigDict backwards compatibility for state | Use extra="ignore" to allow old state.json files to load gracefully | 01-02 | 2026-01-28 |
| Backup state before destructive reset | Preserve old state as .backup.virtual-time for rollback capability | 01-02 | 2026-01-28 |
| Temporary datetime.now(timezone.utc) stopgap | Replace simulation_time with real-time calls until Clock injection | 01-02 | 2026-01-28 |
| Use pendulum for all timestamps | Consistent timezone-aware datetime handling across codebase | 01-03 | 2026-01-28 |
| Inject Clock only into ScenarioOrchestrator | Main execution path where time control matters for testing | 01-03 | 2026-01-28 |
| Replace datetime.now(timezone.utc) with pendulum | Unified time handling, prepares for business hours/DST work | 01-03 | 2026-01-28 |

### Open Questions

- None yet (roadmap just created)

### Todos

- [ ] Plan Phase 1 (Time Infrastructure & UTC Migration)
- [ ] Review roadmap with stakeholders
- [ ] Validate success criteria are observable and testable

### Known Blockers

- None

### Technical Debt

- Current simulation uses virtual-time model (5.33x speedup) producing unrealistic patterns
- No state reconciliation with Jira (assumes script executes perfectly)
- No realistic disruptions or randomness beyond scenario scripts
- Sprint timelines compressed (1.3 real days per 7-day sprint)

## Session Continuity

**Last Session:** Plan 01-03 execution (2026-01-28)

**What Happened:**
- Executed 01-03-PLAN.md (Clock injection & UTC migration)
- Migrated all Pydantic model defaults to use pendulum.now("UTC")
- Replaced 40+ datetime.utcnow() and datetime.now(timezone.utc) calls with pendulum
- Injected Clock parameter into ScenarioOrchestrator with RealClock default
- Updated 12 files: models, orchestrator, agents, main, services, logging
- Committed Task 1 (refactor: Pydantic models) - f4cd242
- Committed Task 2 (refactor: orchestrator/agents) - 2d62f94
- Committed Task 3 (refactor: main & services) - 5fd8be9
- Created 01-03-SUMMARY.md with full execution documentation
- Updated STATE.md with progress (3/4 plans in Phase 1 complete)

**Next Session Should:**
1. Continue Phase 1 execution with plan 01-04 (Business hours enforcement)
2. Implement business hours gate in /trigger endpoint (M-F 9-5)

**Context for Next Agent:**
- All datetime calls migrated to pendulum.now("UTC") - zero naive datetimes
- Clock injected into ScenarioOrchestrator for testability
- Tests can inject FakeClock for deterministic time control
- Ready for business hours logic using pendulum and Clock abstraction
- Phase 1 is 75% complete (3 of 4 plans)

---
*State initialized: 2026-01-27*
