# Project State: Real-Time Scripted Jira Team Simulator

**Last Updated:** 2026-01-28
**Current Phase:** Phase 2: State Reconciliation & Validation
**Current Plan:** Wave 2 in progress (02-04 prep done, 02-05 complete)
**Status:** Wave 2 partial (02-05 complete)

## Project Reference

**Core Value:** The simulation must operate in Jira's time domain (real calendar time), producing realistic sprint timelines and activity patterns that analytics tools can consume as if observing a real development team.

**Current Focus:** Transform virtual-time simulation (5.33x speedup) to real-time calendar execution with pre-scripted scenarios spanning 2-3 sprints. Shift from reactive immediate execution to scheduled event queues with state reconciliation, chaos injection, and adaptive pathfinding.

## Current Position

**Phase:** 2 of 5 - State Reconciliation & Validation
**Plans:** 6 plans, 4 complete (02-01, 02-02, 02-03, 02-05)
**Status:** Wave 2 in progress
**Progress:** [█████░░░░░░░░░░░░░░░] 22% (13/59 requirements)

**Phase Goal:** System validates Jira state before every action and adapts gracefully when reality diverges from simulation plan.

**Phase Plans:**
| Plan | Description | Wave | Depends On | Status |
|------|-------------|------|------------|--------|
| 02-01 | Pre-execution validators with optimistic locking | 1 | - | Complete |
| 02-02 | Execution ID tracker for idempotency | 1 | - | Complete |
| 02-03 | Reconciliation engine with adaptation strategies | 1 | - | Complete |
| 02-04 | Circuit breaker wrapper for JiraClient | 2 | 01, 02, 03 | In Progress (pybreaker added) |
| 02-05 | Staleness detection for scenario auto-removal | 2 | 01, 03 | Complete |
| 02-06 | Orchestrator integration with reconciliation | 3 | All above | Pending |

**Requirements Coverage:**
- RECON-01: 02-01-PLAN (Pre-execution validation checks Jira ticket state) - Complete
- RECON-02: 02-03-PLAN (Reconciliation engine detects divergence) - Complete
- RECON-03: 02-03-PLAN (Reconciler provides adaptation strategies) - Complete
- RECON-04: 02-02-PLAN (Idempotency checks using execution IDs) - Complete
- RECON-05: 02-05-PLAN (Scenario staleness detection) - Complete
- RECON-06: 02-03-PLAN, 02-05-PLAN (Tombstone tracking) - Complete
- RECON-07: 02-01-PLAN (Optimistic locking via updated timestamp) - Complete
- RECON-08: 02-04-PLAN, 02-06-PLAN (Graceful degradation) - In Progress

**Phase Success Criteria:**
1. Simulator detects when user manually transitions ticket status in Jira and skips planned transition (logs reconciliation note)
2. Simulator detects when ticket moved out of active sprint and cancels remaining actions for that ticket (logs tombstone reason)
3. Same action executed twice (due to retry) produces identical Jira state (idempotency via execution ID)
4. When Jira API returns 404 for ticket, simulator marks action as skipped and continues with other actions (no cascade failure)
5. Reconciliation metrics visible in logs show adaptation rate, skip rate, success rate per tick

## Performance Metrics

**Overall Milestone Progress:** 13/59 requirements completed (22%)

**Phase Breakdown:**
- Phase 1: 7/7 (100%) ✓
- Phase 2: 6/8 (75%) - RECON-01 through RECON-07 complete, RECON-08 in progress
- Phase 3: 0/24 (0%)
- Phase 4: 0/14 (0%)
- Phase 5: 0/6 (0%)

**Recent Velocity:** Phase 1 completed in 1 session (4 plans, 3 waves)

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
| ISO day-of-week in config, Pendulum internally | Config uses standard ISO numbering (1=Mon), converted for Pendulum | 1 | 2026-01-28 |
| pybreaker for circuit breaker | Battle-tested Python library (1M+ downloads) for Jira API protection | 2 | 2026-01-28 |
| Tick-based staleness (not wall-clock) | 4 ticks threshold handles business hours correctly (overnight gaps) | 2 | 2026-01-28 |
| Separate read/write circuit breakers | Writes more sensitive (fail_max=3) than reads (fail_max=5) | 2 | 2026-01-28 |
| Status progression ordinal map | STATUS_ORDER (To Do=0 to Done=4) determines forward/backward divergence | 2 | 2026-01-28 |
| 3-retry threshold for transient errors | Transient errors RESCHEDULE only if retry_count < 3 to prevent infinite loops | 2 | 2026-01-28 |
| Case-sensitive status comparison | Jira status names are exact (e.g., "In Progress" != "in progress") | 2 | 2026-01-28 |
| Flexible timestamp input for optimistic locking | validate_with_timestamp() accepts both ISO 8601 strings and pendulum.DateTime | 2 | 2026-01-28 |
| Graceful API error handling | API errors return ValidationResult(valid=False) instead of raising exceptions | 2 | 2026-01-28 |
| Default staleness threshold of 4 ticks | ~3 hours at 45-min cadence, handles overnight gaps | 2 | 2026-01-28 |
| Tombstone records for staleness cleanup | Include scenario_id, ticket_key, reason, last_phase for audit | 2 | 2026-01-28 |

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
  - 20 tests covering clock, business hours, sprint cadence

### Open Questions

- None currently

### Todos

- [x] Plan Phase 2 (State Reconciliation & Validation)
- [x] Research Jira API for precondition checks (completed in 02-RESEARCH.md)
- [x] Design idempotency key format and storage (completed in 02-02-PLAN)
- [ ] Complete 02-04 (Circuit Breaker - pybreaker dependency added)
- [x] Complete 02-05 (Staleness Detection)
- [ ] Complete 02-06 (Orchestrator Integration)

### Known Blockers

- None

### Technical Debt

- Tests require Python 3.12 (anaconda has older Pydantic)
- Some tests use hardcoded dates that may need adjustment

## Session Continuity

**Last Session:** Phase 2 Plan 05 Execution (2026-01-28)

**What Happened:**
- Completed 02-05: Staleness Detection
- Added cleanup_stale_scenarios() function with tombstone records
- 19 tests pass for staleness detection (253 lines)
- Note: Task 1 was pre-committed in 02-04 prep

**Commits This Session:**
- `92b049e`: feat(02-05): create staleness cleanup function
- `33266b0`: test(02-05): add staleness detection tests

**Next Session Should:**
1. Complete 02-04 (Circuit Breaker) - pybreaker dependency already added
2. Then 02-06 (Orchestrator Integration)

**Context for Next Agent:**
- Wave 2 partial: 02-05 complete, 02-04 needs circuit breaker implementation
- src/reconciliation/ module exports: ValidationResult, PreExecutionValidator, OptimisticLockingValidator, ExecutionTracker, ExecutionRecord, ReconciliationEngine, ReconciliationResult, AdaptationStrategy, cleanup_stale_scenarios
- pybreaker>=1.1.0 already in requirements.txt (added in d0ed2c4)
- ActiveScenario has staleness methods: is_stale(), mark_validated(), increment_validation_miss()

---
*State updated: 2026-01-28 after completing 02-05-PLAN*
