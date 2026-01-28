# Roadmap: Real-Time Scripted Jira Team Simulator

**Project:** Real-time scripted Jira simulation with planning horizon and state reconciliation
**Milestone:** Transform virtual-time simulation to real-time calendar execution
**Created:** 2026-01-27
**Status:** Active

## Overview

This roadmap transforms the Jira simulator from virtual-time acceleration (5.33x speedup) to real-time calendar execution with pre-scripted scenarios spanning 2-3 sprints. The architecture shifts from reactive immediate execution to scheduled event queues with state reconciliation, chaos injection, and adaptive pathfinding when reality diverges from plan.

The 5-phase structure follows natural requirement boundaries: foundational time handling, state validation infrastructure, scheduling engine with planning horizon, realistic disruption and adaptation, and performance optimization. Each phase delivers verifiable user-observable capabilities.

## Phases

### Phase 1: Time Infrastructure & UTC Migration

**Goal:** All time handling operates in timezone-aware UTC with business hours enforcement and DST-safe sprint calculations.

**Dependencies:** None (foundational)

**Plans:** 4 plans

Plans:
- [x] 01-01-PLAN.md - Clock abstraction module with RealClock/FakeClock using Pendulum
- [x] 01-02-PLAN.md - Remove virtual time fields from SimulationState, reset state.json
- [x] 01-03-PLAN.md - Migrate all datetime.utcnow() to Clock/pendulum.now("UTC")
- [x] 01-04-PLAN.md - Business hours gate, DST detection, sprint cadence tests

**Requirements:**
- TIME-01: UTC timezone-aware datetime handling throughout codebase
- TIME-02: Virtual clock with injectable Clock abstraction (RealClock/FakeClock)
- TIME-03: Business hours gate in /trigger endpoint (M-F 9-5)
- TIME-04: DST transition detection and graceful handling
- TIME-05: Sprint cadence with Pendulum (Wednesday start, Tuesday end, 7 days)
- CONFIG-01: Remove simulation_time and tick_duration_hours from state
- CONFIG-05: Fresh state initialization (no virtual-time migration)

**Success Criteria:**
1. Developer can set business hours schedule in settings.yaml and /trigger endpoint respects it (rejects requests outside M-F 9-5)
2. Developer can inject FakeClock in tests to freeze time and advance deterministically (no flaky time-dependent tests)
3. System detects DST transitions (spring forward, fall back) and logs warning without duplicate/skipped executions
4. Sprint start/end dates calculated with Pendulum match expected calendar dates (7 real days Wednesday-Tuesday)
5. All datetime comparisons use timezone-aware UTC (no naive datetime warnings in logs)

### Phase 2: State Reconciliation & Validation

**Goal:** System validates Jira state before every action and adapts gracefully when reality diverges from simulation plan.

**Dependencies:** Phase 1 (needs consistent time comparisons)

**Plans:** 6 plans

Plans:
- [x] 02-01-PLAN.md - Pre-execution validators with optimistic locking (TDD)
- [x] 02-02-PLAN.md - Execution ID tracker for idempotency (TDD)
- [x] 02-03-PLAN.md - Reconciliation engine with adaptation strategies (TDD)
- [x] 02-04-PLAN.md - Circuit breaker wrapper for JiraClient
- [x] 02-05-PLAN.md - Staleness detection for scenario auto-removal
- [x] 02-06-PLAN.md - Orchestrator integration with reconciliation

**Requirements:**
- RECON-01: Pre-execution validation checks Jira ticket state (status, assignee, sprint)
- RECON-02: Reconciliation engine detects divergence between plan and reality
- RECON-03: Reconciler provides adaptation strategies (cancel/recalculate/reschedule)
- RECON-04: Idempotency checks using execution IDs prevent duplicate actions
- RECON-05: Scenario staleness detection auto-removes unvalidated scenarios (4+ ticks)
- RECON-06: Tombstone tracking logs why scenarios were invalidated
- RECON-07: Optimistic locking uses Jira updated timestamp for conflict detection
- RECON-08: Graceful degradation on precondition failure (skip action, log, continue)

**Success Criteria:**
1. Simulator detects when user manually transitions ticket status in Jira and skips planned transition (logs reconciliation note)
2. Simulator detects when ticket moved out of active sprint and cancels remaining actions for that ticket (logs tombstone reason)
3. Same action executed twice (due to retry) produces identical Jira state (idempotency via execution ID)
4. When Jira API returns 404 for ticket, simulator marks action as skipped and continues with other actions (no cascade failure)
5. Reconciliation metrics visible in logs show adaptation rate, skip rate, success rate per tick

### Phase 3: Event Scheduler & Queue System

**Goal:** Actions scheduled to real calendar timestamps within 30-minute execution windows; system maintains 2-3 sprint planning horizon.

**Dependencies:** Phase 2 (needs reconciliation for scheduled action validation)

**Plans:** 0 plans

Plans:
- [ ] TBD (created by /gsd:plan-phase)

**Requirements:**
- SCHED-01: Priority queue maintains actions sorted by scheduled_time (heap operations)
- SCHED-02: Scheduler provides "what's due now?" query with execution window logic
- SCHED-03: ScheduledAction model (scheduled_time, window, preconditions, agent, ticket, params)
- SCHED-04: Schedule persistence to data/state.json or SQLite
- SCHED-05: Virtual clock advances simulation_time by tick_duration_hours each tick
- SCHED-06: ScenarioScheduler converts script days (1-7) to absolute timestamps
- SCHED-07: Weekend skipping (no actions scheduled Saturday/Sunday)
- SCHED-08: Action status tracking (pending/ready/completed/skipped/adapted)
- SCHED-09: Overdue action handling (past execution window marked skipped)
- PLAN-01: PlanningHorizon model maintains 2-3 future sprint plans
- PLAN-02: Trigger sprint planning when horizon drops below 2 sprints
- PLAN-03: Enhanced PM agent prioritizes backlog using velocity and goals (LLM)
- PLAN-04: PM agent selects sprint content based on capacity (historical velocity)
- PLAN-05: Velocity tracker records committed vs completed points per sprint
- PLAN-06: Average velocity calculation from last 3 sprints
- PLAN-07: SprintPlan model (sprint_id, dates, committed_items, scenario_id, status)
- PLAN-08: Sprint planning flow (fetch backlog -> prioritize -> select -> generate scenario -> schedule actions -> create Jira sprint)
- CONFIG-02: Add planning_horizon and action_queue to SimulationState
- CONFIG-04: Sprint configuration (duration_days=7, start_day=wednesday, horizon=3)
- EXEC-01: TickExecutor replaces orchestrator time-advancement logic
- EXEC-02: Each tick: check events -> get ready actions -> reconcile -> execute -> update state
- EXEC-03: Execution via existing CrewAI crews (preserve agent personalities)
- EXEC-04: Mark actions completed/skipped/adapted with timestamps
- EXEC-05: Handle overdue actions by marking skipped with log entry

**Success Criteria:**
1. PM agent automatically triggers sprint planning when only 1 future sprint remains in horizon (maintains 2-3 sprints lookahead)
2. Developer views scheduled actions in data/state.json showing timestamps spanning next 2-3 sprints with business hours distribution
3. /trigger endpoint queries scheduler for actions due in current 30-minute window and executes only those (respects execution window)
4. Actions scheduled on Friday 4pm-5pm have no follow-ups until Monday 9am (weekend skipping works)
5. Sprint created in Jira matches SprintPlan dates (Wednesday start, Tuesday end, 7 calendar days) and committed items from backlog prioritization

### Phase 4: Adaptive Pathfinding & Chaos Injection

**Goal:** System injects random realistic disruptions and adapts scenario scripts when Jira state diverges from expectations.

**Dependencies:** Phase 3 (needs scheduler to insert chaos events and reschedule adapted actions)

**Plans:** 0 plans

Plans:
- [ ] TBD (created by /gsd:plan-phase)

**Requirements:**
- CHAOS-01: RandomEventGenerator with per-event-type probabilities (outage, bug, absence, blocker, priority_shift, scope_change)
- CHAOS-02: Granular chaos level config in settings.yaml (custom probabilities, not just presets)
- CHAOS-03: RandomEvent model (event_type, triggered_at, affected_tickets, description, severity)
- CHAOS-04: Dice rolling each tick against configured probabilities
- CHAOS-05: Event catalog with weighted selection by scenario archetype
- ADAPT-01: ScenarioAdapter modifies active scenario when random events occur
- ADAPT-02: Insert emergency response actions for production outages (pause non-critical work)
- ADAPT-03: Reassign actions to other agents when team member absence occurs
- ADAPT-04: Insert bug fix actions and postpone other work for urgent bugs
- ADAPT-05: Add blocker discussion actions and extend timelines for external blockers
- ADAPT-06: Scenario confidence score (script_fidelity) tracks % events executed vs adapted
- ADAPT-07: Accept reality threshold - abandon script if 3+ events overridden
- ADAPT-08: Adaptive pathfinding recalculates workflow path when status diverges
- CONFIG-03: Update settings.yaml with random_events section (per-event probabilities)

**Success Criteria:**
1. Chaos engine randomly injects urgent bug event (configured 10% probability per tick) and simulator inserts bug fix actions for affected tickets
2. When team member absence event occurs, simulator reassigns scheduled actions for that agent to other team members (respects roles)
3. When Jira ticket status manually changed from "In Progress" to "Done", adaptive pathfinding skips remaining planned transitions for that ticket (logs adaptation)
4. Scenario confidence score visible in logs/dashboard shows script_fidelity drops below 70% after 3+ external changes (triggers accept reality mode)
5. Developer can configure custom chaos probabilities in settings.yaml (e.g., 5% outage, 15% blocker, 0% absence) and simulation respects them

### Phase 5: Performance Optimization & Dynamic Tuning

**Goal:** System executes actions asynchronously within tick budget and dynamically adjusts chaos probabilities based on sprint completion feedback.

**Dependencies:** Phase 4 (needs baseline chaos implementation to tune against)

**Plans:** 0 plans

Plans:
- [ ] TBD (created by /gsd:plan-phase)

**Requirements:**
- PERF-01: Async action execution with asyncio.gather for independent actions
- PERF-02: Aggressive timeout budgets (15s planning, 10s per action) prevent tick overruns
- PERF-03: Max actions per tick cap (4 for busy mode) prevents exceeding n8n interval
- PERF-04: Dynamic chaos probability adjustment via feedback loop from sprint completion rates
- PERF-05: Heartbeat monitoring alerts if tick gap exceeds 1.5x expected interval
- PERF-06: Circuit breaker per ticket prevents unbounded retry loops on persistent failures

**Success Criteria:**
1. /trigger endpoint returns 200 within 45 seconds even with 4 actions queued (async execution with timeout enforcement)
2. When single action times out after 10 seconds, other independent actions continue executing (no cascade failure)
3. When sprint completion rate drops below 60%, dynamic tuner reduces chaos probabilities by 20% for next sprint (feedback loop)
4. When same ticket fails precondition checks 3 times in a row, circuit breaker marks it unhealthy and skips future actions (prevents retry loop)
5. Heartbeat monitoring logs warning if tick gap exceeds 67 minutes (1.5x the 45-minute expected interval)

## Progress

| Phase | Status | Requirements | Completed | Progress |
|-------|--------|--------------|-----------|----------|
| Phase 1: Time Infrastructure & UTC Migration | ✓ Complete | 7 | 7 | 100% |
| Phase 2: State Reconciliation & Validation | ✓ Complete | 8 | 8 | 100% |
| Phase 3: Event Scheduler & Queue System | Not Started | 24 | 0 | 0% |
| Phase 4: Adaptive Pathfinding & Chaos Injection | Not Started | 14 | 0 | 0% |
| Phase 5: Performance Optimization & Dynamic Tuning | Not Started | 6 | 0 | 0% |

**Total:** 59 requirements, 15 completed (25%)

## Phase Dependencies

```
Phase 1: Time Infrastructure
    |
Phase 2: State Reconciliation <- depends on consistent time comparisons
    |
Phase 3: Event Scheduler <- depends on reconciliation for validation
    |
Phase 4: Chaos & Adaptation <- depends on scheduler to insert/reschedule events
    |
Phase 5: Performance Tuning <- depends on baseline chaos to tune against
```

## Notes

**Phase ordering rationale:**
- Phase 1 first: DST bugs and timezone inconsistencies are systemic risks affecting all features; must fix foundational time handling before building scheduling on top
- Phase 2 before 3: Reconciliation patterns must be established before scheduler adds complexity; idempotency is prerequisite for scheduled retries
- Phase 3 before 4: Event scheduler is infrastructure for chaos injection; can't inject random disruptions without queue to hold them
- Phase 4 before 5: Chaos and adaptation are core value; prove these work before optimizing
- Phase 5 last: Performance optimization after functionality validated; premature optimization risks complicating debugging

**Research flags:**
- Phase 3 may need deeper research on APScheduler persistence patterns for Docker environments (SQLAlchemy job store setup, volume mounting)
- Phase 4 may need graph search algorithm research for Jira workflow transitions (Dijkstra vs A* vs BFS for status transition graphs with cycles)

---
*Last updated: 2026-01-28 after Phase 2 execution complete (6 plans, 129 tests)*
