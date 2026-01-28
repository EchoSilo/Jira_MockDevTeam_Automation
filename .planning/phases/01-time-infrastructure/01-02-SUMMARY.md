---
phase: 01-time-infrastructure
plan: 02
subsystem: infra
tags: [pydantic, state-management, cleanup]

# Dependency graph
requires:
  - phase: 01-01
    provides: Clock abstraction with Pendulum
provides:
  - Cleaned SimulationState model without virtual time fields
  - Fresh state.json reset for real-time operation
  - Codebase migrated to datetime.now(timezone.utc) temporarily
affects: [01-03, state-management, orchestration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pydantic ConfigDict(extra='ignore') for backwards compatibility"
    - "Temporary datetime.now(timezone.utc) until Clock injection"

key-files:
  created:
    - data/state.json.backup.virtual-time
  modified:
    - src/state/models.py
    - data/state.json
    - src/main.py
    - src/orchestrator/orchestrator.py

key-decisions:
  - "Used ConfigDict(extra='ignore') for graceful handling of old state.json files with virtual time fields"
  - "Backed up old state before reset to preserve historical data"
  - "Replaced all simulation_time with datetime.now(timezone.utc) as temporary stopgap until Clock injection"

patterns-established:
  - "State model evolution with backwards compatibility via Pydantic extra='ignore'"
  - "State backup before destructive operations"

# Metrics
duration: 9min
completed: 2026-01-28
---

# Phase 01 Plan 02: Virtual Time Cleanup Summary

**Removed virtual time model (simulation_time, tick_duration_hours) from SimulationState and reset state.json for real-time operation**

## Performance

- **Duration:** 9min 12sec
- **Started:** 2026-01-28T05:46:02Z
- **Completed:** 2026-01-28T05:55:14Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- SimulationState model cleaned of virtual time fields (simulation_time, tick_duration_hours)
- Old state.json backed up and fresh state created without virtual time
- All codebase references updated to use datetime.now(timezone.utc) temporarily
- Backwards compatibility enabled via Pydantic ConfigDict

## Task Commits

Each task was committed atomically:

1. **Task 1: Remove virtual time fields from SimulationState** - `3ba8918` (refactor)
2. **Task 2: Backup and reset state.json** - `a0beb4d` (chore)
3. **Task 3: Update callers in main.py and orchestrator** - `ed0e4d7`, `b921ec6` (refactor)

## Files Created/Modified
- `src/state/models.py` - Removed simulation_time and tick_duration_hours fields, added ConfigDict(extra="ignore")
- `data/state.json` - Reset to fresh state without virtual time fields
- `data/state.json.backup.virtual-time` - Backup of old state with virtual time for reference
- `src/main.py` - Replaced state.simulation_time with datetime.now(timezone.utc)
- `src/orchestrator/orchestrator.py` - Removed simulation_time advancement and replaced references

## Decisions Made
- **ConfigDict backwards compatibility:** Used Pydantic's `ConfigDict(extra="ignore")` to allow old state.json files with virtual time fields to load gracefully without errors. This prevents breakage if someone loads an old backup.
- **State backup strategy:** Created `.backup.virtual-time` suffix to preserve old state before destructive reset, allowing rollback if needed.
- **Temporary datetime.now():** Used `datetime.now(timezone.utc)` as temporary replacement for `state.simulation_time` until Plan 03 injects Clock properly. This is a stopgap, not final solution.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

**Linter auto-reverts:** VSCode linter repeatedly reverted changes to main.py and orchestrator.py during editing. Resolved by committing immediately after edits to lock in changes before linter could revert.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Ready for Plan 03 (Clock Injection):
- SimulationState is clean, no virtual time fields to interfere
- All simulation_time references removed from codebase
- State.json is fresh and ready for real-time operation
- Temporary datetime.now(timezone.utc) calls are marked as stopgap (easy to find and replace with Clock)

**Note for Plan 03:** Search for `datetime.now(timezone.utc)` to find all locations that need Clock injection.

---
*Phase: 01-time-infrastructure*
*Completed: 2026-01-28*
