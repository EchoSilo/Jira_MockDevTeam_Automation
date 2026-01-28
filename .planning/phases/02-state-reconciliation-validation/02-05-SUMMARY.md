---
phase: 02-state-reconciliation-validation
plan: 05
subsystem: reconciliation
tags: [staleness, validation, tick-based, cleanup, tombstone]

# Dependency graph
requires:
  - phase: 02-01
    provides: Pre-execution validators for status/sprint/assignee validation
  - phase: 02-03
    provides: Reconciliation engine with adaptation strategies
provides:
  - ActiveScenario validation tracking fields (last_validated, validation_tick_count)
  - is_stale() method using tick count (not wall-clock time)
  - mark_validated() method to reset tick count
  - increment_validation_miss() method to track missed validations
  - cleanup_stale_scenarios() function with tombstone records
affects: [02-06, orchestrator-integration, scenario-lifecycle]

# Tech tracking
tech-stack:
  added: []
  patterns: [tick-based staleness, tombstone records]

key-files:
  created:
    - src/reconciliation/staleness.py
    - tests/test_staleness_detection.py
  modified:
    - src/state/models.py
    - src/reconciliation/__init__.py

key-decisions:
  - "Tick-based staleness (not wall-clock time) handles business hours correctly"
  - "Default threshold of 4 ticks (~3 hours at 45-min cadence)"
  - "Tombstone records include scenario_id, ticket_key, reason, last_phase"

patterns-established:
  - "Tick-based validation: increment_validation_miss() on skip, mark_validated() on success"
  - "Tombstone pattern: dict with scenario_id, ticket_key, reason, last_phase"

# Metrics
duration: 4min
completed: 2026-01-28
---

# Phase 2 Plan 5: Staleness Detection Summary

**Tick-based staleness detection for scenarios unvalidated for 4+ ticks with tombstone records**

## Performance

- **Duration:** 4 min
- **Started:** 2026-01-28T07:13:02Z
- **Completed:** 2026-01-28T07:17:06Z
- **Tasks:** 3 (Task 1 was pre-committed in 02-04 prep)
- **Files modified:** 4

## Accomplishments
- ActiveScenario model enhanced with validation_tick_count and last_validated fields
- is_stale() method checks tick count against threshold (default 4)
- cleanup_stale_scenarios() removes unvalidated scenarios and returns tombstone records
- 19 comprehensive tests covering all staleness detection requirements

## Task Commits

Each task was committed atomically:

1. **Task 1: Add validation tracking fields** - `d0ed2c4` (pre-committed in 02-04 prep)
2. **Task 2: Create staleness cleanup function** - `92b049e` (feat)
3. **Task 3: Write staleness detection tests** - `33266b0` (test)

## Files Created/Modified
- `src/state/models.py` - Added last_validated, validation_tick_count fields and staleness methods
- `src/reconciliation/staleness.py` - cleanup_stale_scenarios function with tombstone generation
- `src/reconciliation/__init__.py` - Export cleanup_stale_scenarios
- `tests/test_staleness_detection.py` - 19 tests (253 lines) covering staleness behavior

## Decisions Made
- Tick-based staleness (not wall-clock time) handles business hours correctly - 4 ticks at 45-minute cadence could span overnight
- Default threshold of 4 ticks provides ~3 hours of tolerance during business hours
- Tombstone records include scenario_id, ticket_key, reason, and last_phase for audit trail

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Task 1 fields were already committed as part of 02-04 preparation - proceeded with Tasks 2 and 3 only
- pytest in anaconda environment has older Pydantic - used Python 3.12 directly

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Staleness detection ready for integration in 02-06 (Orchestrator Integration)
- cleanup_stale_scenarios() can be called at tick start before action execution
- Tombstone records available for logging/metrics

---
*Phase: 02-state-reconciliation-validation*
*Completed: 2026-01-28*
