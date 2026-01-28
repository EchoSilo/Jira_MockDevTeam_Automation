# Project State: Real-Time Scripted Jira Team Simulator

**Last Updated:** 2026-01-28
**Current Phase:** Phase 1: Time Infrastructure & UTC Migration
**Current Plan:** 01-02 completed (2 of 4)
**Status:** In progress - executing Phase 1 plans

## Project Reference

**Core Value:** The simulation must operate in Jira's time domain (real calendar time), producing realistic sprint timelines and activity patterns that analytics tools can consume as if observing a real development team.

**Current Focus:** Transform virtual-time simulation (5.33x speedup) to real-time calendar execution with pre-scripted scenarios spanning 2-3 sprints. Shift from reactive immediate execution to scheduled event queues with state reconciliation, chaos injection, and adaptive pathfinding.

## Current Position

**Phase:** 1 of 5 - Time Infrastructure & UTC Migration
**Plan:** 2 of 4 complete
**Status:** In Progress
**Last activity:** 2026-01-28 - Completed 01-02-PLAN.md (Virtual time cleanup)

**Progress:** [████████████░░░░░░░░] 50% (2/4 plans in phase)

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

**Last Session:** Plan 01-02 execution (2026-01-28)

**What Happened:**
- Executed 01-02-PLAN.md (Virtual time cleanup)
- Removed simulation_time and tick_duration_hours from SimulationState model
- Added ConfigDict(extra="ignore") for backwards compatibility
- Backed up old state.json as .backup.virtual-time
- Created fresh state.json without virtual time fields
- Replaced all state.simulation_time with datetime.now(timezone.utc) in main.py and orchestrator.py
- Committed Task 1 (refactor: remove fields) - 3ba8918
- Committed Task 2 (chore: backup and reset state) - a0beb4d
- Committed Task 3 (refactor: update callers) - ed0e4d7, b921ec6
- Created 01-02-SUMMARY.md with full execution documentation
- Updated STATE.md with progress (2/4 plans in Phase 1 complete)

**Next Session Should:**
1. Continue Phase 1 execution with plan 01-03 (Clock injection into codebase)
2. Replace all datetime.now(timezone.utc) with Clock injection pattern

**Context for Next Agent:**
- Virtual time model completely removed from codebase
- State.json is fresh, no virtual time fields
- All datetime.now(timezone.utc) calls are temporary stopgap (marked for Clock injection)
- Clock abstraction ready from 01-01 (src.time module)
- Phase 1 is 50% complete (2 of 4 plans)

---
*State initialized: 2026-01-27*
