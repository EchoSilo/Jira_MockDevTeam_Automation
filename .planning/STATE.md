# Project State: Real-Time Scripted Jira Team Simulator

**Last Updated:** 2026-01-28
**Current Phase:** Phase 3: Event Scheduler & Queue System (IN PROGRESS)
**Current Plan:** 03-05 complete
**Status:** Phase 3 in progress - scenario scheduler and virtual clock complete

## Project Reference

**Core Value:** The simulation must operate in Jira's time domain (real calendar time), producing realistic sprint timelines and activity patterns that analytics tools can consume as if observing a real development team.

**Current Focus:** Building event scheduler with SQLite persistence, business hours scheduling, and scenario script loading. Enables scheduled action queues that execute at specific calendar times.

## Current Position

**Phase:** 3 of 5 - Event Scheduler & Queue System (IN PROGRESS)
**Plans:** 3 of 8 complete (03-02, 03-04, 03-05)
**Status:** In progress
**Progress:** [█████████░░░░░░░░░░░] 32% (19/59 requirements)

**Phase Goal:** System validates Jira state before every action and adapts gracefully when reality diverges from simulation plan.

**Phase Plans:**
| Plan | Description | Wave | Depends On | Status |
|------|-------------|------|------------|--------|
| 02-01 | Pre-execution validators with optimistic locking | 1 | - | Complete |
| 02-02 | Execution ID tracker for idempotency | 1 | - | Complete |
| 02-03 | Reconciliation engine with adaptation strategies | 1 | - | Complete |
| 02-04 | Circuit breaker wrapper for JiraClient | 2 | 01, 02, 03 | Complete |
| 02-05 | Staleness detection for scenario auto-removal | 2 | 01, 03 | Complete |
| 02-06 | Orchestrator integration with reconciliation | 3 | All above | Complete |

**Requirements Coverage:**
- RECON-01: 02-01-PLAN, 02-06-PLAN (Pre-execution validation checks Jira ticket state) - Complete
- RECON-02: 02-03-PLAN (Reconciliation engine detects divergence) - Complete
- RECON-03: 02-03-PLAN (Reconciler provides adaptation strategies) - Complete
- RECON-04: 02-02-PLAN, 02-06-PLAN (Idempotency checks using execution IDs) - Complete
- RECON-05: 02-05-PLAN, 02-06-PLAN (Scenario staleness detection) - Complete
- RECON-06: 02-03-PLAN, 02-05-PLAN (Tombstone tracking) - Complete
- RECON-07: 02-01-PLAN (Optimistic locking via updated timestamp) - Complete
- RECON-08: 02-04-PLAN, 02-06-PLAN (Circuit breaker and metrics visibility) - Complete

**Phase Success Criteria (ALL MET):**
1. [x] Simulator detects when user manually transitions ticket status in Jira and skips planned transition (logs reconciliation note)
2. [x] Simulator detects when ticket moved out of active sprint and cancels remaining actions for that ticket (logs tombstone reason)
3. [x] Same action executed twice (due to retry) produces identical Jira state (idempotency via execution ID)
4. [x] When Jira API returns 404 for ticket, simulator marks action as skipped and continues with other actions (no cascade failure)
5. [x] Reconciliation metrics visible in logs show adaptation rate, skip rate, success rate per tick

## Performance Metrics

**Overall Milestone Progress:** 18/59 requirements completed (30%)

**Phase Breakdown:**
- Phase 1: 7/7 (100%) ✓
- Phase 2: 8/8 (100%) ✓
- Phase 3: 2/24 (8%)
- Phase 4: 0/14 (0%)
- Phase 5: 0/6 (0%)

**Recent Velocity:**
- Phase 2 completed in 2 sessions (6 plans, 3 waves)
- Phase 3 Plan 02 completed in 3 minutes (2 commits)
- Phase 3 Plan 04 completed in 5 minutes (3 commits)

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
| pybreaker uses reset_timeout not timeout_duration | API parameter naming differs from plan assumption | 2 | 2026-01-28 |
| throw_new_error_on_trip behavior | 5th failure raises CircuitBreakerError, not original exception | 2 | 2026-01-28 |
| Validation before sprint check | Run reconciliation validation before sprint membership check for fast-fail | 2 | 2026-01-28 |
| Execution ID in result dict | Pass execution_id through result for recording in caller ensures same ID used | 2 | 2026-01-28 |
| SQLite for action persistence | Simple file-based persistence without external dependencies | 3 | 2026-01-28 |
| Per-operation connection lifecycle | Open connection per operation for thread safety, no persistent connections | 3 | 2026-01-28 |
| INSERT OR REPLACE for upsert | SQLite upsert syntax enables save_action to create and update | 3 | 2026-01-28 |
| 48-hour retention for completed actions | Balance audit trail with database size via cleanup threshold | 3 | 2026-01-28 |
| Pydantic v1 compatibility for tests | Anaconda pytest uses Python 3.11 with Pydantic v1.10.12, models use Config class | 3 | 2026-01-28 |
| 80% capacity buffer | Conservative buffer for unknowns in sprint planning | 3 | 2026-01-28 |
| 2-sprint minimum + 14-day lookahead | Dual trigger for planning horizon ensures continuous coverage | 3 | 2026-01-28 |
| Velocity excludes in-progress sprints | Prevents distortion from partial work during ongoing sprints | 3 | 2026-01-28 |
| @dataclass(order=True) for heap ordering | scheduled_time as first field enables automatic heap sorting without custom comparisons | 3 | 2026-01-28 |
| Mark canceled actions SKIPPED not removed | heapq lacks efficient removal; filter by status instead | 3 | 2026-01-28 |
| 30-minute default execution window | Balances flexibility with urgency detection for scheduled actions | 3 | 2026-01-28 |
| Actions remain in heap after completion | Simplifies queue management; get_due_actions() filters by status | 3 | 2026-01-28 |
| Lazy import of litellm in BacklogPrioritizer | Import inside method to avoid test dependency issues with sys.modules mocking | 3 | 2026-01-28 |
| 24-hour cache for backlog prioritization | Balance LLM cost savings with freshness, invalidates on backlog change | 3 | 2026-01-28 |
| Type-based fallback prioritization | Bug > Task > Story > Feature when LLM unavailable ensures graceful degradation | 3 | 2026-01-28 |
| Routine model (Haiku) for backlog ranking | Cost-effective for structured ranking tasks vs Sonnet | 3 | 2026-01-28 |
| VirtualClock tick duration 0.75 hours | Matches n8n cron cadence (45 minutes) for realistic simulation pacing | 3 | 2026-01-28 |
| Weekend actions moved to Monday | Use BusinessHoursScheduler.next_business_day() for consistency | 3 | 2026-01-28 |
| Random time distribution 0-7.99 hours | Ensures actions stay within 9am-5pm without spilling to next day | 3 | 2026-01-28 |
| Conditional BacklogPrioritizer import | Wrapped in try/except to allow tests without litellm dependency | 3 | 2026-01-28 |

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

**Phase 2: State Reconciliation & Validation** (Completed 2026-01-28)
- 6 plans executed across 3 waves
- 129 reconciliation tests pass
- Key deliverables:
  - PreExecutionValidator for status/assignee/sprint validation
  - OptimisticLockingValidator for timestamp-based conflict detection
  - ExecutionTracker for idempotency with 48-hour cleanup
  - ReconciliationEngine with CANCEL/SKIP/RESCHEDULE/RECALCULATE/PROCEED strategies
  - ResilientJiraClient with circuit breaker protection (read: 5/60s, write: 3/120s)
  - Staleness detection via validation_tick_count (threshold: 4 ticks)
  - Orchestrator integration: pre-execution validation, metrics logging, stale cleanup

**Phase 3: Event Scheduler & Queue System** (In Progress)
- 3 plans completed (03-02, 03-04, 03-05)
- 25 tests pass (10 persistence, 15 scenario scheduler)
- Key deliverables so far:
  - ScheduledAction dataclass with heap-compatible ordering
  - ActionStatus enum (PENDING, READY, COMPLETED, SKIPPED, ADAPTED)
  - ScheduledActionStore with SQLite persistence
  - VirtualClock for simulation time advancement (0.75 hour ticks)
  - ScenarioScheduler converts script days (1-7) to calendar timestamps
  - Weekend skipping and business hours enforcement

### Open Questions

- None currently

### Todos

- [x] Plan Phase 2 (State Reconciliation & Validation)
- [x] Research Jira API for precondition checks (completed in 02-RESEARCH.md)
- [x] Design idempotency key format and storage (completed in 02-02-PLAN)
- [x] Complete 02-04 (Circuit Breaker)
- [x] Complete 02-05 (Staleness Detection)
- [x] Complete 02-06 (Orchestrator Integration)
- [ ] Plan Phase 3 (Event Scheduling & Pre-scripted Scenarios)

### Known Blockers

- None

### Technical Debt

- Anaconda has Pydantic v1.10.12 (Python 3.11), system Python has v2.11.10 (Python 3.12)
- Planning models use Pydantic v1-compatible Config class for test compatibility
- Some tests use hardcoded dates that may need adjustment
- Added pytest-asyncio dependency for orchestrator tests

## Session Continuity

**Last Session:** Phase 3 Plan 05 Execution (2026-01-28)

**What Happened:**
- Completed 03-05: Scenario Scheduler & Virtual Clock (TDD)
- Created VirtualClock for simulation time advancement (0.75 hour ticks)
- Created ScenarioScheduler for script-to-calendar conversion
- Weekend skipping logic (Saturday/Sunday → Monday)
- Random time distribution within business hours (9am-5pm)
- Fixed BacklogPrioritizer import issue (conditional try/except)
- Fixed test date assumptions (Feb 2 2026 is Monday)
- Created 15 comprehensive tests (all pass)

**Commits This Session:**
- `1b6837f`: test(03-05): add failing tests for VirtualClock and ScenarioScheduler
- `20feb5d`: feat(03-05): implement VirtualClock for simulation time
- `aead6c6`: feat(03-05): implement ScenarioScheduler for sprint script conversion

**Next Session Should:**
1. Continue with remaining Phase 3 plans (03-06, 03-07, 03-08)
2. Load scenario scripts from JSON files
3. Integrate ScenarioScheduler with sprint planning
4. Build execution queue with VirtualClock

**Context for Next Agent:**
- Phase 3 progress: 3/8 plans complete (03-02 persistence, 03-04 models, 03-05 scheduler)
- VirtualClock provides simulation time tracking for testing
- ScenarioScheduler ready to convert scenario scripts to action queues
- Weekend skipping and business hours enforcement working correctly

---
*State updated: 2026-01-28 after completing 03-05-PLAN*
