# Project State: Real-Time Scripted Jira Team Simulator

**Last Updated:** 2026-01-28
**Current Phase:** Phase 2: State Reconciliation & Validation
**Current Plan:** Not yet planned
**Status:** Phase 1 complete, awaiting Phase 2 planning

## Project Reference

**Core Value:** The simulation must operate in Jira's time domain (real calendar time), producing realistic sprint timelines and activity patterns that analytics tools can consume as if observing a real development team.

**Current Focus:** Transform virtual-time simulation (5.33x speedup) to real-time calendar execution with pre-scripted scenarios spanning 2-3 sprints. Shift from reactive immediate execution to scheduled event queues with state reconciliation, chaos injection, and adaptive pathfinding.

## Current Position

**Phase:** 2 of 5 - State Reconciliation & Validation
**Plan:** None (Phase 1 just completed)
**Status:** Not Started
**Progress:** [██░░░░░░░░░░░░░░░░░░] 12% (7/59 requirements)

**Phase Goal:** System validates Jira state before every action and adapts gracefully when reality diverges from simulation plan.

**Phase Requirements:**
- RECON-01: Pre-execution validation checks Jira ticket state (status, assignee, sprint)
- RECON-02: Reconciliation engine detects divergence between plan and reality
- RECON-03: Reconciler provides adaptation strategies (cancel/recalculate/reschedule)
- RECON-04: Idempotency checks using execution IDs prevent duplicate actions
- RECON-05: Scenario staleness detection auto-removes unvalidated scenarios (4+ ticks)
- RECON-06: Tombstone tracking logs why scenarios were invalidated
- RECON-07: Optimistic locking uses Jira updated timestamp for conflict detection
- RECON-08: Graceful degradation on precondition failure (skip action, log, continue)

**Phase Success Criteria:**
1. Simulator detects when user manually transitions ticket status in Jira and skips planned transition (logs reconciliation note)
2. Simulator detects when ticket moved out of active sprint and cancels remaining actions for that ticket (logs tombstone reason)
3. Same action executed twice (due to retry) produces identical Jira state (idempotency via execution ID)
4. When Jira API returns 404 for ticket, simulator marks action as skipped and continues with other actions (no cascade failure)
5. Reconciliation metrics visible in logs show adaptation rate, skip rate, success rate per tick

## Performance Metrics

**Overall Milestone Progress:** 7/59 requirements completed (12%)

**Phase Breakdown:**
- Phase 1: 7/7 (100%) ✓
- Phase 2: 0/8 (0%)
- Phase 3: 0/24 (0%)
- Phase 4: 0/14 (0%)
- Phase 5: 0/6 (0%)

**Recent Velocity:** Phase 1 completed in 1 session (4 plans, 3 waves)

## Accumulated Context

### Key Decisions

| Decision | Rationale | Phase | Date |
|----------|-----------|-------|------|
| 5-phase structure aligned with research | Research suggests optimal grouping by time → reconciliation → scheduling → chaos → perf | All | 2026-01-27 |
| Replace virtual time with real-time scheduling | Jira operates in real time; virtual time creates unrealistic patterns | 1 | 2026-01-27 |
| Preserve existing agent personalities and LLM system | Agent behavior is sophisticated and working well; problem is orchestration timing | 3 | 2026-01-27 |
| Start fresh rather than migrate existing data | Existing data is based on flawed time model; clean slate is simpler | 1 | 2026-01-27 |
| Use Pendulum for all datetime handling | Pendulum provides timezone-safe arithmetic and DST handling | 1 | 2026-01-28 |
| Clock abstraction via Protocol | Enables dependency injection for testing without monkeypatching | 1 | 2026-01-28 |
| ISO day-of-week in config, Pendulum internally | Config uses standard ISO numbering (1=Mon), converted for Pendulum | 1 | 2026-01-28 |

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

- [ ] Plan Phase 2 (State Reconciliation & Validation)
- [ ] Research Jira API for precondition checks (updated timestamp, status fields)
- [ ] Design idempotency key format and storage

### Known Blockers

- None

### Technical Debt

- Tests require pendulum in pytest environment (currently using different Python env)
- Some tests use hardcoded dates that may need adjustment

## Session Continuity

**Last Session:** Phase 1 Execution (2026-01-28)

**What Happened:**
- Executed all 4 plans in Phase 1 across 3 waves
- Wave 1 (parallel): 01-01 Clock abstraction, 01-02 Remove virtual time
- Wave 2 (sequential): 01-03 UTC migration (depends on 01-01, 01-02)
- Wave 3 (sequential): 01-04 Business hours (depends on 01-03)
- Verifier checked 21 must-haves, all passed
- Updated ROADMAP.md, REQUIREMENTS.md, STATE.md

**Next Session Should:**
1. Run `/gsd:discuss-phase 2` to gather context for State Reconciliation
2. Or `/gsd:plan-phase 2` to plan directly if context is clear
3. Phase 2 focuses on Jira state validation and adaptation strategies

**Context for Next Agent:**
- Phase 1 infrastructure is solid: Clock abstraction, pendulum throughout, business hours gate
- Phase 2 builds on this: uses Clock for timestamp comparisons, pendulum for date math
- Key challenge: detecting when Jira state diverges from expected (external edits)
- Existing code has no reconciliation logic - this is net new functionality

---
*State updated: 2026-01-28 after Phase 1 completion*
