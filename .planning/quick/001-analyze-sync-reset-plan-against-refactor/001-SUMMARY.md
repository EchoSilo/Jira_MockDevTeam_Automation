---
phase: quick-001
plan: 01
subsystem: state-management
tags: [sync-reset, gap-analysis, refactor-compatibility]

metrics:
  duration: ~15m
  completed: 2026-02-02
---

# Quick Task 001: Sync-Reset Plan Analysis Summary

**One-liner:** Identified 11 missing stateful components in sync-reset plan (35% coverage) - critical gaps in VirtualClock, SQLite store, and performance monitors

## Tasks Completed

| Task | Name | Status |
|------|------|--------|
| 1 | Component Gap Analysis | Complete |
| 2 | Conflict and Risk Analysis | Complete |
| 3 | Write Analysis Report | Complete |

## Key Findings

### Coverage Assessment
- **Addressed:** 6 legacy state components (active_scenarios, agents, sprint, etc.)
- **Missing:** 11 new infrastructure components from Phases 1-5
- **Coverage:** 35% (6/17 stateful components)

### Critical Gaps (HIGH Risk)
1. **VirtualClock** - Simulation time will be desynchronized from real time
2. **ScheduledActionStore (SQLite)** - Stale actions persist in database
3. **Scheduler.queue._heap** - In-memory queue retains old actions

### Moderate Gaps (MEDIUM Risk)
4. **PerTicketCircuitBreaker** - Unhealthy tickets stay blocked
5. **DynamicChaosTuner** - Loses learned chaos tuning parameters
6. **ExecutionTracker** - Currently not an issue but could be if persisted

### Minor Gaps (LOW Risk)
7. **HeartbeatMonitor** - False alert on first tick after reset
8. **Global circuit breakers** - Self-correcting after timeout

### Key Conflicts Identified
1. **SQLite vs SimulationState mismatch** - action_queue cleared but SQLite retains data
2. **VirtualClock desync** - New actions never become "due" if clock is ahead
3. **SprintScenario vs ActiveScenario** - Mixed model state after sync-reset
4. **PlanningHorizon mapping** - Jira API may not provide expected data format

## Recommendations Summary

### Must Fix (Priority 1)
- Clear SQLite scheduled_actions table
- Reset VirtualClock to pendulum.now("UTC")
- Clear in-memory Scheduler queue

### Should Fix (Priority 2)
- Reset PerTicketCircuitBreaker
- Reset DynamicChaosTuner
- Reset HeartbeatMonitor

### Consider (Priority 3-4)
- Decide on SprintScenario regeneration strategy
- Document chaos tuning reset impact
- Validate PlanningHorizon Jira API mapping

## Artifacts

| Artifact | Path |
|----------|------|
| Full Analysis Report | `.planning/quick/001-analyze-sync-reset-plan-against-refactor/ANALYSIS-REPORT.md` |

## Next Steps

1. Update sync-reset plan to include Phase 3-5 infrastructure resets
2. Implement the updated sync-reset endpoint
3. Add verification tests for complete state reset
4. Consider adding a "reset type" parameter (soft=legacy only, hard=full infrastructure)

---
*Analysis completed 2026-02-02*
