# Project State: Real-Time Scripted Jira Team Simulator

**Last Updated:** 2026-01-28
**Current Phase:** Phase 2: State Reconciliation & Validation
**Current Plan:** Wave 1 complete, ready for Wave 2
**Status:** Wave 1 complete (02-01, 02-02, 02-03)

## Project Reference

**Core Value:** The simulation must operate in Jira's time domain (real calendar time), producing realistic sprint timelines and activity patterns that analytics tools can consume as if observing a real development team.

**Current Focus:** Transform virtual-time simulation (5.33x speedup) to real-time calendar execution with pre-scripted scenarios spanning 2-3 sprints. Shift from reactive immediate execution to scheduled event queues with state reconciliation, chaos injection, and adaptive pathfinding.

## Current Position

**Phase:** 2 of 5 - State Reconciliation & Validation
**Plans:** 6 plans created
**Status:** Planned, ready for execution
**Progress:** [███░░░░░░░░░░░░░░░░░] 14% (8/59 requirements)

**Phase Goal:** System validates Jira state before every action and adapts gracefully when reality diverges from simulation plan.

**Phase Plans:**
| Plan | Description | Wave | Depends On | Status |
|------|-------------|------|------------|--------|
| 02-01 | Pre-execution validators with optimistic locking | 1 | - | Pending |
| 02-02 | Execution ID tracker for idempotency | 1 | - | Complete |
| 02-03 | Reconciliation engine with adaptation strategies | 1 | - | Complete |
| 02-04 | Circuit breaker wrapper for JiraClient | 2 | 01, 02, 03 | Pending |
| 02-05 | Staleness detection for scenario auto-removal | 2 | 01, 03 | Pending |
| 02-06 | Orchestrator integration with reconciliation | 3 | All above | Pending |

**Requirements Coverage:**
- RECON-01: 02-01-PLAN (Pre-execution validation checks Jira ticket state)
- RECON-02: 02-03-PLAN (Reconciliation engine detects divergence)
- RECON-03: 02-03-PLAN (Reconciler provides adaptation strategies)
- RECON-04: 02-02-PLAN (Idempotency checks using execution IDs)
- RECON-05: 02-05-PLAN (Scenario staleness detection)
- RECON-06: 02-03-PLAN, 02-05-PLAN (Tombstone tracking)
- RECON-07: 02-01-PLAN (Optimistic locking via updated timestamp)
- RECON-08: 02-04-PLAN, 02-06-PLAN (Graceful degradation)

**Phase Success Criteria:**
1. Simulator detects when user manually transitions ticket status in Jira and skips planned transition (logs reconciliation note)
2. Simulator detects when ticket moved out of active sprint and cancels remaining actions for that ticket (logs tombstone reason)
3. Same action executed twice (due to retry) produces identical Jira state (idempotency via execution ID)
4. When Jira API returns 404 for ticket, simulator marks action as skipped and continues with other actions (no cascade failure)
5. Reconciliation metrics visible in logs show adaptation rate, skip rate, success rate per tick

## Performance Metrics

**Overall Milestone Progress:** 10/59 requirements completed (17%)

**Phase Breakdown:**
- Phase 1: 7/7 (100%) ✓
- Phase 2: 3/8 (38%) - RECON-02, RECON-03, RECON-04 complete (partial RECON-06)
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
- [ ] Execute Phase 2 plans via /gsd:execute-phase

### Known Blockers

- None

### Technical Debt

- Tests require pendulum in pytest environment (currently using different Python env)
- Some tests use hardcoded dates that may need adjustment

## Session Continuity

**Last Session:** Phase 2 Planning (2026-01-28)

**What Happened:**
- Created 6 executable plans for Phase 2
- Wave 1 (parallel): 02-01 Validators, 02-02 Execution Tracker, 02-03 Reconciler
- Wave 2 (parallel): 02-04 Circuit Breaker, 02-05 Staleness Detection
- Wave 3 (sequential): 02-06 Orchestrator Integration
- All plans have must_haves with truths, artifacts, and key_links
- ROADMAP.md updated with plan list

**Next Session Should:**
1. Run `/gsd:execute-phase 2` to execute all 6 plans
2. Wave 1 plans can run in parallel (no dependencies)
3. Wave 2 plans depend on Wave 1 completion
4. Wave 3 (02-06) depends on all previous plans

**Context for Next Agent:**
- Research is complete in 02-RESEARCH.md (patterns, libraries, architecture)
- Plans are TDD-style with clear must_haves and verification criteria
- New dependency: pybreaker>=1.1.0 (add to requirements.txt in 02-04)
- New module: src/reconciliation/ (validators, models, reconciler, execution_tracker, staleness, circuit_breaker)
- Integration point: ScenarioOrchestrator._execute_action() gets pre-validation

---
*State updated: 2026-01-28 after Phase 2 planning (6 plans created)*
