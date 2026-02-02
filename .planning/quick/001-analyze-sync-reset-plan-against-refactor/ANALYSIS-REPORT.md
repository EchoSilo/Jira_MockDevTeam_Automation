# Sync-Reset Plan Analysis Report

**Date:** 2026-02-02
**Analyst:** Claude (Opus 4.5)
**Plan Under Review:** `silly-moseying-beaver.md` (Sync Reset - Rebuild State from Jira)

---

## Executive Summary

**Status: SIGNIFICANT GAPS IDENTIFIED**

The sync-reset plan was written against the pre-refactor codebase and **does not account for the 6-phase infrastructure refactor**. The plan only addresses legacy state management (active_scenarios, agents, sprint) but misses **11 critical stateful components** introduced in Phases 1-5.

| Category | Components Addressed | Components Missing | Coverage |
|----------|---------------------|-------------------|----------|
| Legacy State | 6 | 0 | 100% |
| Phase 1 (Time) | 0 | 1 | 0% |
| Phase 2 (Reconciliation) | 0 | 2 | 0% |
| Phase 3 (Scheduler) | 0 | 3 | 0% |
| Phase 4 (Chaos) | 0 | 1 | 0% |
| Phase 5 (Performance) | 0 | 4 | 0% |
| **TOTAL** | **6** | **11** | **35%** |

**Risk Level: HIGH** - Executing the current sync-reset plan will leave the system in an inconsistent state where legacy state is synced but new infrastructure components retain stale data.

---

## Component Coverage Matrix

### Legend
- ADDRESSED: Plan explicitly handles this component
- MISSING: Plan does not mention this component
- N/A: Component is stateless, no reset needed

| Component | Location | Stateful | Plan Status | Reset Needed | Risk if Missed |
|-----------|----------|----------|-------------|--------------|----------------|
| **Legacy State (Pre-Refactor)** |
| active_scenarios | SimulationState | Yes | ADDRESSED | Yes | - |
| completed_scenarios | SimulationState | Yes | ADDRESSED | Yes (clear) | - |
| agents workloads | SimulationState | Yes | ADDRESSED | Yes | - |
| sprint | SimulationState | Yes | ADDRESSED | Yes (inject) | - |
| planning_horizon | SimulationState | Yes | ADDRESSED | Yes (clear) | - |
| action_queue | SimulationState | Yes | ADDRESSED | Yes (clear) | - |
| sprint_scenario | SimulationState | Yes | ADDRESSED | Yes (clear) | - |
| recent_actions | SimulationState | Yes | ADDRESSED | Yes (clear) | - |
| **Phase 1: Time Infrastructure** |
| VirtualClock._simulation_time | Scheduler.clock | Yes | MISSING | Yes | HIGH |
| Clock abstraction | RealClock | No | N/A | No | - |
| **Phase 2: Reconciliation** |
| ExecutionTracker._executed | ExecutionTracker | Yes | MISSING | Yes | MEDIUM |
| ResilientJiraClient breakers | jira_read_breaker, jira_write_breaker | Yes | MISSING | Maybe | LOW |
| PreExecutionValidator | Stateless | No | N/A | No | - |
| ReconciliationEngine | Stateless | No | N/A | No | - |
| **Phase 3: Scheduler** |
| ScheduledActionStore (SQLite) | data/scheduler.db | Yes | MISSING | Yes | HIGH |
| Scheduler.queue._heap | ActionPriorityQueue | Yes | MISSING | Yes | HIGH |
| Scheduler.clock (VirtualClock) | Same as Phase 1 | Yes | MISSING | Yes | HIGH |
| **Phase 4: Chaos** |
| ChaosConfig | Loaded from settings | No | N/A | No | - |
| EventCatalog | Stateless | No | N/A | No | - |
| ConfidenceTracker | Stateless per-call | No | N/A | No | - |
| PathfindingAdapter | Stateless | No | N/A | No | - |
| **Phase 5: Performance** |
| DynamicChaosTuner.current_multiplier | _dynamic_tuner | Yes | MISSING | Yes | MEDIUM |
| DynamicChaosTuner._adjustment_history | _dynamic_tuner | Yes | MISSING | Yes | LOW |
| HeartbeatMonitor.last_tick_time | _heartbeat_monitor | Yes | MISSING | Yes | LOW |
| PerTicketCircuitBreaker._ticket_health | _per_ticket_breaker | Yes | MISSING | Yes | MEDIUM |

---

## Gap Details by Phase

### Phase 1: Time Infrastructure

**Missing Component: VirtualClock**

- **Location:** `src/scheduling/virtual_clock.py`, instantiated in `lifespan()` as part of Scheduler
- **State:** `_simulation_time` (pendulum.DateTime)
- **Current value:** Initialized to `pendulum.now("UTC")` at app startup, advances via `advance()` calls
- **Issue:** After sync-reset, VirtualClock may be far ahead of real time if many ticks have occurred
- **Required reset:** `virtual_clock.set_time(pendulum.now("UTC"))` to resync with wall clock
- **Risk:** HIGH - TickExecutor uses this clock to determine which actions are "due"; if simulation time is ahead, no actions will execute

### Phase 2: Reconciliation

**Missing Component: ExecutionTracker**

- **Location:** `src/reconciliation/execution_tracker.py`, instantiated per-request (not global)
- **State:** `_executed` dict mapping execution_id -> ExecutionRecord
- **Current behavior:** Created fresh per /trigger call, so NOT a problem
- **Issue:** If future versions make this persistent, it would need reset
- **Required reset:** `tracker._executed.clear()` (but currently not needed)
- **Risk:** MEDIUM - Not an issue currently, but could cause duplicate-prevention false positives if persisted

**Missing Component: Circuit Breakers (pybreaker)**

- **Location:** `src/reconciliation/circuit_breaker.py`, module-level `jira_read_breaker`, `jira_write_breaker`
- **State:** Internal pybreaker state (failure count, circuit state)
- **Issue:** If circuit was open before sync-reset (Jira was down), it stays open after
- **Required reset:** Breakers auto-reset after timeout (60s reads, 120s writes), but manual reset available
- **Risk:** LOW - Self-correcting, but could block first few requests after sync-reset

### Phase 3: Scheduler (CRITICAL)

**Missing Component: ScheduledActionStore (SQLite)**

- **Location:** `src/scheduling/persistence.py`, db at `data/scheduler.db`
- **State:** `scheduled_actions` table with all pending/completed actions
- **Issue:** Sync-reset clears `action_queue` in SimulationState but SQLite retains all actions
- **Required reset:** Either `DELETE FROM scheduled_actions WHERE status = 'pending'` or drop/recreate table
- **Risk:** HIGH - On next /trigger, Scheduler._load_pending_actions() reloads stale actions from SQLite

**Missing Component: Scheduler.queue._heap**

- **Location:** `src/scheduling/scheduler.py` -> `ActionPriorityQueue`
- **State:** In-memory heap of ScheduledAction objects
- **Issue:** Even if SQLite cleared, in-memory heap retains actions until app restart
- **Required reset:** `scheduler.queue._heap.clear()` or recreate Scheduler instance
- **Risk:** HIGH - Stale actions will execute, likely failing precondition checks

**Missing Component: VirtualClock in Scheduler**

- **Same as Phase 1** - the Scheduler holds a reference to VirtualClock
- Must reset via `scheduler.clock.set_time(pendulum.now("UTC"))`

### Phase 4: Chaos

All chaos components are stateless or configuration-based. No reset needed.

However, if a sync-reset happens mid-sprint:
- ConfidenceTracker calculates fidelity based on scenario execution counts
- Scenario data will be cleared, so fidelity calculation may be skewed until next sprint

**Risk:** LOW - Fidelity will recalculate cleanly on fresh scenario data

### Phase 5: Performance (MODERATE)

**Missing Component: DynamicChaosTuner**

- **Location:** `src/chaos/dynamic_tuner.py`, instantiated in `_initialize_performance_components()`
- **State:** `current_multiplier` (float, EMA-smoothed), `_adjustment_history` (list)
- **Issue:** Multiplier represents learned chaos tolerance; reset loses tuning history
- **Required reset:** `_dynamic_tuner.reset()` (sets multiplier to 1.0, clears history)
- **Risk:** MEDIUM - Chaos injection returns to default intensity, may be too high/low for current team state

**Missing Component: HeartbeatMonitor**

- **Location:** `src/monitoring/heartbeat.py`, instantiated in `_initialize_performance_components()`
- **State:** `last_tick_time` (pendulum.DateTime)
- **Issue:** After sync-reset, gap detection will fire false alert on next tick
- **Required reset:** `_heartbeat_monitor.reset()` (sets last_tick_time to None)
- **Risk:** LOW - Only causes one false alert in logs

**Missing Component: PerTicketCircuitBreaker**

- **Location:** `src/reconciliation/circuit_breaker.py`, instantiated in `_initialize_performance_components()`
- **State:** `_ticket_health` dict mapping ticket_key -> TicketHealth
- **Issue:** Tickets marked unhealthy before sync-reset stay unhealthy (won't be actioned)
- **Required reset:** `_per_ticket_breaker.reset_all()`
- **Risk:** MEDIUM - Unhealthy tickets from before reset won't get processed

---

## Conflict Analysis

### Conflict 1: SimulationState.action_queue vs SQLite Store

**Severity: HIGH**

**Description:**
- Plan clears `state.action_queue` (list in SimulationState)
- But `ScheduledActionStore` (SQLite at `data/scheduler.db`) is separate
- On next app restart or when Scheduler reinitializes, SQLite data is reloaded

**Impact:**
1. Cleared action_queue appears empty
2. Next /trigger calls `scheduler._load_pending_actions()`
3. Stale actions from before sync-reset are loaded back into memory
4. These actions reference old tickets/scenarios that no longer exist

**Resolution Required:**
- Sync-reset must also clear SQLite: `store.cleanup_old_actions(max_age_hours=0)` or direct DELETE

### Conflict 2: VirtualClock Desync with Real Time

**Severity: HIGH**

**Description:**
- VirtualClock advances 45 minutes per tick
- After many ticks, simulation_time >> real wall clock time
- Sync-reset doesn't touch VirtualClock
- TickExecutor.get_due_actions() uses VirtualClock.now() to filter actions

**Impact:**
1. VirtualClock is at (e.g.) 2026-02-10 15:00 (8 days ahead)
2. New actions scheduled from Jira reality are timestamped near 2026-02-02
3. These actions are never "due" because VirtualClock is ahead of them
4. Simulation appears stuck - no actions execute

**Resolution Required:**
- Reset VirtualClock: `scheduler.clock.set_time(pendulum.now("UTC"))`

### Conflict 3: Sprint Scenario vs Legacy ActiveScenario

**Severity: MEDIUM**

**Description:**
- Plan uses `sync_state_with_jira()` which creates **ActiveScenario** objects (legacy per-ticket)
- But the new scheduler uses **SprintScenario** (Phase 3/4) for sprint-level orchestration
- These are different models with different purposes

**Impact:**
1. Sync-reset creates legacy ActiveScenarios from Jira tickets
2. SprintScenario is cleared separately (plan does mention this)
3. But SprintPlanner expects SprintScenario for proper script-based execution
4. Mixed model state: ActiveScenarios exist but no SprintScenario to orchestrate them

**Resolution Required:**
- Either: Generate new SprintScenario after sync-reset
- Or: Accept that sync-reset returns to "legacy mode" (ad-hoc actions, no sprint script)

### Conflict 4: Planning Horizon from Jira

**Severity: LOW**

**Description:**
- Plan mentions `_sync_planning_horizon_from_jira()` to populate from Jira future sprints
- Jira API `get_future_sprints()` may return different data than expected
- PlanningHorizon model expects SprintPlan objects with specific fields

**Impact:**
1. Jira returns raw sprint data (id, name, start_date, end_date)
2. PlanningHorizon expects capacity, committed_points, etc.
3. Mapping may be incomplete or require defaults

**Resolution Required:**
- Verify Jira API response format
- Add mapping logic or accept empty/default capacity values

---

## Recommendations (Prioritized)

### Priority 1: CRITICAL (Must Fix Before Implementation)

1. **Clear SQLite Action Store**
   ```python
   # In sync-reset endpoint
   store = app.state.scheduler.store
   conn = store._get_connection()
   conn.execute("DELETE FROM scheduled_actions")
   conn.commit()
   ```

2. **Reset VirtualClock to Real Time**
   ```python
   # In sync-reset endpoint
   app.state.scheduler.clock.set_time(pendulum.now("UTC"))
   ```

3. **Clear In-Memory Action Queue**
   ```python
   # In sync-reset endpoint
   app.state.scheduler.queue._heap.clear()
   ```

### Priority 2: HIGH (Should Fix)

4. **Reset Per-Ticket Circuit Breaker**
   ```python
   # In sync-reset endpoint
   if _per_ticket_breaker:
       _per_ticket_breaker.reset_all()
   ```

5. **Reset Dynamic Chaos Tuner**
   ```python
   # In sync-reset endpoint
   if _dynamic_tuner:
       _dynamic_tuner.reset()
   ```

6. **Reset Heartbeat Monitor**
   ```python
   # In sync-reset endpoint
   if _heartbeat_monitor:
       _heartbeat_monitor.reset()
   ```

### Priority 3: MEDIUM (Consider)

7. **Decide on SprintScenario Regeneration**
   - Option A: Accept "legacy mode" after sync-reset (no sprint script)
   - Option B: Add SprintScenario generation to sync-reset (more complex)
   - Recommendation: Option A for initial implementation

8. **Document Chaos Tuning Reset Impact**
   - Add warning that sync-reset loses learned chaos parameters
   - First few sprints after reset may have suboptimal chaos intensity

### Priority 4: LOW (Nice to Have)

9. **Global Circuit Breaker Reset**
   - Not strictly needed (auto-resets after timeout)
   - But could add `jira_read_breaker.reset()` for immediate recovery

10. **Validate Planning Horizon Jira Mapping**
    - Test `get_future_sprints()` API response
    - Ensure mapping to PlanningHorizon works correctly

---

## Suggested Plan Updates

The sync-reset plan should be updated to include:

### New Section: Phase 3-5 Infrastructure Reset

```python
# Add to sync_reset_state() endpoint after line "Clear planning_horizon and action_queue"

# === Phase 3: Scheduler Infrastructure ===
# Clear SQLite action store
scheduler = app.state.scheduler
conn = scheduler.store._get_connection()
conn.execute("DELETE FROM scheduled_actions")
conn.commit()
if not scheduler.store._conn:  # File-based DB
    conn.close()

# Clear in-memory queue
scheduler.queue._heap.clear()

# Reset VirtualClock to real time
scheduler.clock.set_time(pendulum.now("UTC"))

# === Phase 5: Performance Components ===
# Reset per-ticket circuit breaker
if _per_ticket_breaker:
    _per_ticket_breaker.reset_all()

# Reset dynamic chaos tuner (loses tuning history)
if _dynamic_tuner:
    _dynamic_tuner.reset()

# Reset heartbeat monitor
if _heartbeat_monitor:
    _heartbeat_monitor.reset()
```

### Updated "What Gets Reset" Section

Add to the plan's reset list:
- `ScheduledActionStore` (SQLite) - cleared
- `Scheduler.queue._heap` - cleared
- `VirtualClock` - reset to current real time
- `PerTicketCircuitBreaker` - all tickets reset to healthy
- `DynamicChaosTuner` - multiplier reset to 1.0
- `HeartbeatMonitor` - last_tick cleared

### New Verification Step

Add to verification section:
```bash
# Verify scheduler state cleared
sqlite3 data/scheduler.db "SELECT COUNT(*) FROM scheduled_actions WHERE status='pending'"
# Should return: 0
```

---

## Appendix: Component Locations

| Component | File Path | Line (approx) |
|-----------|-----------|---------------|
| VirtualClock | `src/scheduling/virtual_clock.py` | 8 |
| Scheduler | `src/scheduling/scheduler.py` | 16 |
| ScheduledActionStore | `src/scheduling/persistence.py` | 13 |
| ExecutionTracker | `src/reconciliation/execution_tracker.py` | 55 |
| ResilientJiraClient | `src/reconciliation/circuit_breaker.py` | 94 |
| PerTicketCircuitBreaker | `src/reconciliation/circuit_breaker.py` | 212 |
| DynamicChaosTuner | `src/chaos/dynamic_tuner.py` | 28 |
| HeartbeatMonitor | `src/monitoring/heartbeat.py` | 27 |
| SimulationState | `src/state/models.py` | 836 |
| SprintScenario | `src/scenarios/sprint_scenario.py` | 152 |
| Lifespan init | `src/main.py` | 339-398 |
| _initialize_performance_components | `src/main.py` | 182-217 |
| _initialize_chaos_components | `src/main.py` | 156-179 |
