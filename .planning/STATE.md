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
**Plan:** 4 of 4 complete
**Status:** Phase Complete
**Last activity:** 2026-01-28 - Completed 01-04-PLAN.md (Business hours & sprint cadence)

**Progress:** [████████████████████] 100% (4/4 plans in phase)

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
| ISO day-of-week (1-7) in config, Pendulum 0-based (0-6) internally | Config uses standard ISO numbering, converted for Pendulum compatibility | 01-04 | 2026-01-28 |
| Business hours config cached globally | Avoid repeated file reads on every /trigger request | 01-04 | 2026-01-28 |
| DST transitions logged as warnings, not errors | Detection for debugging without blocking execution | 01-04 | 2026-01-28 |

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

**Last Session:** Plan 01-04 execution (2026-01-28)

**What Happened:**
- Executed 01-04-PLAN.md (Business hours & sprint cadence)
- Created business hours validation module with DST detection
- Wired validate_business_hours dependency into POST /trigger endpoint
- Created 12 comprehensive tests for business hours and sprint cadence
- Fixed day-of-week mapping bug (ISO 1-7 vs Pendulum 0-6)
- Committed Task 1 (feat: business hours module) - 43e95c6
- Committed Task 2 (feat: /trigger dependency) - ca12d46
- Committed Task 3 (test: business hours tests + bug fix) - 3af3fdb
- Created 01-04-SUMMARY.md with full execution documentation
- Updated STATE.md with Phase 1 completion (4/4 plans complete)

**Next Session Should:**
1. Begin Phase 2: State Reconciliation & Jira Sync
2. Implement state snapshot comparison and drift detection

**Context for Next Agent:**
- Phase 1 complete: All time infrastructure in place
- /trigger endpoint enforces M-F 9-5 business hours (returns 403 outside hours)
- DST transitions detected and logged without breaking execution
- Sprint cadence validated with 7-day Wed-Tue calculations
- FakeClock enables deterministic time testing throughout codebase
- All datetime operations use timezone-aware pendulum UTC

---
*State initialized: 2026-01-27*
