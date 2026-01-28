# Requirements: Real-Time Scripted Jira Team Simulator

**Defined:** 2026-01-27
**Core Value:** The simulation must operate in Jira's time domain (real calendar time), producing realistic sprint timelines and activity patterns.

## v1 Requirements

Requirements for transforming the virtual-time simulation into a real-time scripted scenario system. Each maps to roadmap phases.

### Time Infrastructure

- [ ] **TIME-01**: All datetime handling converted to timezone-aware UTC (prevent DST bugs in sprint day calculations)
- [ ] **TIME-02**: Virtual clock interface with injectable Clock abstraction (RealClock for production, FakeClock for deterministic testing)
- [ ] **TIME-03**: Business hours gate in /trigger endpoint respects M-F 9-5 schedule from settings.yaml
- [ ] **TIME-04**: DST transition detection with graceful handling (no duplicate/missing executions during clock changes)
- [ ] **TIME-05**: Sprint cadence calculations use Pendulum for timezone-safe arithmetic (Wednesday start, Tuesday end, 7-day duration)

### State Reconciliation

- [ ] **RECON-01**: Pre-execution validation checks Jira ticket state before action (status, assignee, sprint membership)
- [ ] **RECON-02**: Reconciliation engine detects divergence between simulation plan and Jira reality
- [ ] **RECON-03**: Reconciler provides adaptation strategies (cancel if done, recalculate if diverged, reschedule if timing drift)
- [ ] **RECON-04**: Idempotency checks using execution IDs prevent duplicate comments and transitions
- [ ] **RECON-05**: Scenario staleness detection auto-removes scenarios not validated in 4+ ticks
- [ ] **RECON-06**: Tombstone tracking logs why scenarios were invalidated by external changes
- [ ] **RECON-07**: Optimistic locking uses Jira updated timestamp to detect concurrent modifications
- [ ] **RECON-08**: Graceful degradation on precondition failure (skip action, log discrepancy, continue)

### Event Scheduler

- [ ] **SCHED-01**: Priority queue maintains scheduled actions sorted by simulation_time using heap operations
- [ ] **SCHED-02**: Scheduler provides "what's due now?" query interface with execution window logic
- [ ] **SCHED-03**: ScheduledAction model includes scheduled_time, execution_window_minutes (30 min default), preconditions, agent_id, ticket_key, parameters
- [ ] **SCHED-04**: Schedule persistence to data/state.json (or SQLite if restart survival required)
- [ ] **SCHED-05**: Virtual clock advances simulation_time by tick_duration_hours each tick (enables time compression)
- [ ] **SCHED-06**: ScenarioScheduler converts SprintScenario script days (1-7) to absolute timestamps with business hours distribution
- [ ] **SCHED-07**: Weekend skipping ensures no actions scheduled on Saturday/Sunday
- [ ] **SCHED-08**: Action status tracking (pending/ready/completed/skipped/adapted) with executed_at timestamps
- [ ] **SCHED-09**: Overdue action handling marks actions past execution window as skipped with logging

### Planning Horizon

- [ ] **PLAN-01**: PlanningHorizon model maintains 2-3 future sprint plans ahead of active sprint
- [ ] **PLAN-02**: Trigger sprint planning when horizon drops below 2 planned sprints
- [ ] **PLAN-03**: Enhanced PM agent prioritizes backlog using velocity and release goals via LLM
- [ ] **PLAN-04**: PM agent selects sprint content based on capacity (historical velocity average)
- [ ] **PLAN-05**: Velocity tracker records committed vs completed points per sprint
- [ ] **PLAN-06**: Average velocity calculation from last 3 sprints for capacity planning
- [ ] **PLAN-07**: SprintPlan model includes sprint_id, start_date (Wednesday), end_date (Tuesday), committed_items, scenario_id, status (planned/active/completed)
- [ ] **PLAN-08**: Sprint planning flow: backlog fetch → PM prioritize → select items → generate scenario → schedule actions → create Jira sprint

### Chaos Injection

- [ ] **CHAOS-01**: RandomEventGenerator with configurable probabilities per event type (production_outage, urgent_bug, team_absence, external_blocker, priority_shift, scope_change)
- [ ] **CHAOS-02**: Granular chaos level configuration in settings.yaml (per-event probabilities, not just presets)
- [ ] **CHAOS-03**: RandomEvent model includes event_type, triggered_at, affected_tickets, description, severity
- [ ] **CHAOS-04**: Dice rolling each tick against configured probabilities to generate events
- [ ] **CHAOS-05**: Event catalog with weighted selection based on scenario archetype (smooth vs blocker-heavy)

### Scenario Adaptation

- [ ] **ADAPT-01**: ScenarioAdapter modifies active scenario when random events occur
- [ ] **ADAPT-02**: Insert emergency response actions for production outages (pause non-critical work)
- [ ] **ADAPT-03**: Reassign actions to other agents when team member absence occurs
- [ ] **ADAPT-04**: Insert bug fix actions and postpone other work for urgent bugs
- [ ] **ADAPT-05**: Add blocker discussion actions and extend timelines for external blockers
- [ ] **ADAPT-06**: Scenario confidence score (script_fidelity metric) tracks % events executed vs adapted
- [ ] **ADAPT-07**: Accept reality threshold - abandon script if 3+ events overridden by external changes
- [ ] **ADAPT-08**: Adaptive pathfinding recalculates workflow path when Jira state diverges from expected status

### Execution Engine

- [ ] **EXEC-01**: TickExecutor replaces orchestrator time-advancement logic
- [ ] **EXEC-02**: Each tick: check random events → get ready actions → reconcile → execute → update state
- [ ] **EXEC-03**: Execution via existing CrewAI crews (preserve agent personalities and LLM routing)
- [ ] **EXEC-04**: Mark actions completed/skipped/adapted with timestamps and reconciliation notes
- [ ] **EXEC-05**: Handle overdue actions (past execution window) by marking skipped and logging

### Performance & Optimization

- [ ] **PERF-01**: Async action execution with asyncio.gather for independent actions
- [ ] **PERF-02**: Aggressive timeout budgets (15s planning, 10s per action) prevent tick overruns
- [ ] **PERF-03**: Max actions per tick cap (4 for busy mode) prevents exceeding n8n interval
- [ ] **PERF-04**: Dynamic chaos probability adjustment via feedback loop from sprint completion rates
- [ ] **PERF-05**: Heartbeat monitoring alerts if tick gap exceeds 1.5x expected interval
- [ ] **PERF-06**: Circuit breaker per ticket prevents unbounded retry loops on persistent failures

### Configuration & Migration

- [ ] **CONFIG-01**: Remove simulation_time and tick_duration_hours from SimulationState model
- [ ] **CONFIG-02**: Add planning_horizon and action_queue fields to SimulationState
- [ ] **CONFIG-03**: Update settings.yaml with real_time, random_events, velocity, releases sections
- [ ] **CONFIG-04**: Sprint configuration: duration_days=7, start_day=wednesday, planning_horizon_sprints=3
- [ ] **CONFIG-05**: Fresh state initialization (no migration of existing virtual-time data)

## v2 Requirements

Deferred to future release. Tracked but not in current scope.

### Advanced Features

- **ADVAN-01**: Multi-team orchestration with cross-team dependency scenarios
- **ADVAN-02**: Simulation time control UI (pause, fast-forward, rewind for demos)
- **ADVAN-03**: Event replay and audit trail for debugging scenario execution
- **ADVAN-04**: Realistic timing variance with jitter (±10% on action execution times)
- **ADVAN-05**: Continuous execution mode with websocket triggers (alternative to cron)
- **ADVAN-06**: Millisecond-precision timing for high-frequency scenarios
- **ADVAN-07**: Perfect script adherence mode (force through precondition failures for testing)
- **ADVAN-08**: Multiple timezone support for distributed team simulation

### Analytics & Observability

- **ANALY-01**: State divergence dashboard showing script vs reality comparison
- **ANALY-02**: Chaos event impact analysis (how disruptions affected velocity)
- **ANALY-03**: Reconciliation metrics (adaptation rate, skip rate, success rate)
- **ANALY-04**: Performance dashboard with tick execution time breakdown
- **ANALY-05**: Velocity trend analysis and prediction

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Changing agent personalities | Existing LLM-driven comment generation is sophisticated and working well; problem is orchestration timing not content |
| Migrating existing simulation data | Existing data based on flawed virtual-time model; clean slate is simpler and clearer |
| Real-time UI updates during execution | Existing 15-second polling is sufficient; websocket adds complexity without clear benefit |
| Historical analytics dashboard | Focus on simulation, not retrospective analysis; Jira itself provides historical analytics |
| Fixed-cadence releases | Feature-based releases (PM decides when ready) better reflects real Agile teams |
| Continuous delivery mode | Contradicts cron-triggered discrete event design; increase tick frequency instead |
| Sub-minute execution precision | False accuracy given n8n cron granularity (15-45 min intervals); day-level scheduling sufficient |
| Perfect script adherence | Reality always diverges; adaptation is a feature not a bug; forcing through breaks realism |
| Rollback capability | Jira doesn't support transaction rollback; must be conservative (check-then-act) not optimistic |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| TIME-01 | Phase 1 | Pending |
| TIME-02 | Phase 1 | Pending |
| TIME-03 | Phase 1 | Pending |
| TIME-04 | Phase 1 | Pending |
| TIME-05 | Phase 1 | Pending |
| RECON-01 | Phase 2 | Pending |
| RECON-02 | Phase 2 | Pending |
| RECON-03 | Phase 2 | Pending |
| RECON-04 | Phase 2 | Pending |
| RECON-05 | Phase 2 | Pending |
| RECON-06 | Phase 2 | Pending |
| RECON-07 | Phase 2 | Pending |
| RECON-08 | Phase 2 | Pending |
| SCHED-01 | Phase 3 | Pending |
| SCHED-02 | Phase 3 | Pending |
| SCHED-03 | Phase 3 | Pending |
| SCHED-04 | Phase 3 | Pending |
| SCHED-05 | Phase 3 | Pending |
| SCHED-06 | Phase 3 | Pending |
| SCHED-07 | Phase 3 | Pending |
| SCHED-08 | Phase 3 | Pending |
| SCHED-09 | Phase 3 | Pending |
| PLAN-01 | Phase 3 | Pending |
| PLAN-02 | Phase 3 | Pending |
| PLAN-03 | Phase 3 | Pending |
| PLAN-04 | Phase 3 | Pending |
| PLAN-05 | Phase 3 | Pending |
| PLAN-06 | Phase 3 | Pending |
| PLAN-07 | Phase 3 | Pending |
| PLAN-08 | Phase 3 | Pending |
| CHAOS-01 | Phase 4 | Pending |
| CHAOS-02 | Phase 4 | Pending |
| CHAOS-03 | Phase 4 | Pending |
| CHAOS-04 | Phase 4 | Pending |
| CHAOS-05 | Phase 4 | Pending |
| ADAPT-01 | Phase 4 | Pending |
| ADAPT-02 | Phase 4 | Pending |
| ADAPT-03 | Phase 4 | Pending |
| ADAPT-04 | Phase 4 | Pending |
| ADAPT-05 | Phase 4 | Pending |
| ADAPT-06 | Phase 4 | Pending |
| ADAPT-07 | Phase 4 | Pending |
| ADAPT-08 | Phase 4 | Pending |
| PERF-01 | Phase 5 | Pending |
| PERF-02 | Phase 5 | Pending |
| PERF-03 | Phase 5 | Pending |
| PERF-04 | Phase 5 | Pending |
| PERF-05 | Phase 5 | Pending |
| PERF-06 | Phase 5 | Pending |
| CONFIG-01 | Phase 1 | Pending |
| CONFIG-02 | Phase 3 | Pending |
| CONFIG-03 | Phase 4 | Pending |
| CONFIG-04 | Phase 3 | Pending |
| CONFIG-05 | Phase 1 | Pending |
| EXEC-01 | Phase 3 | Pending |
| EXEC-02 | Phase 3 | Pending |
| EXEC-03 | Phase 3 | Pending |
| EXEC-04 | Phase 3 | Pending |
| EXEC-05 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 59 total
- Mapped to phases: 59
- Unmapped: 0 ✓

---
*Requirements defined: 2026-01-27*
*Last updated: 2026-01-27 after roadmap creation*
