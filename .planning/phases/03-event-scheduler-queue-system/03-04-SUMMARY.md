---
phase: 03-event-scheduler-queue-system
plan: 04
subsystem: planning
tags: [pydantic, pendulum, sprint-planning, velocity-tracking, capacity-planning]

# Dependency graph
requires:
  - phase: 01-time-infrastructure
    provides: pendulum datetime handling and UTC-first approach
provides:
  - SprintPlan model for tracking planned sprints with committed items
  - PlanningHorizon for maintaining 2-3 future sprints
  - VelocityTracker for historical velocity and capacity recommendations
affects: [03-05, 03-06, sprint-planning, capacity-planning]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Planning horizon with 2-sprint minimum and 14-day lookahead"
    - "Velocity-based capacity planning with 80% buffer"
    - "Sprint lifecycle (PLANNED → ACTIVE → COMPLETED)"

key-files:
  created:
    - src/planning/__init__.py
    - src/planning/models.py
    - src/planning/velocity_tracker.py
    - tests/test_planning_models.py
  modified: []

key-decisions:
  - "Pydantic v1 compatibility for anaconda environment (v1.10.12)"
  - "Conservative 80% buffer for capacity recommendations"
  - "2-sprint minimum with 14-day lookahead threshold"
  - "Velocity excludes in-progress sprints to avoid distortion"

patterns-established:
  - "Planning models use Pendulum for timezone-safe date handling"
  - "Velocity tracker maintains rolling 3-sprint average"
  - "PlanningHorizon.needs_planning() triggers both sprint count and time-based"

# Metrics
duration: 5min
completed: 2026-01-28
---

# Phase 03 Plan 04: Planning Models Summary

**Sprint planning models with 2-3 sprint horizon, velocity-based capacity planning, and Pydantic v1 compatibility**

## Performance

- **Duration:** 5 min
- **Started:** 2026-01-28T08:33:51Z
- **Completed:** 2026-01-28T08:38:23Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- Created SprintPlan model with sprint lifecycle (PLANNED → ACTIVE → COMPLETED)
- Implemented PlanningHorizon with 2-sprint minimum and 14-day lookahead
- Built VelocityTracker with rolling 3-sprint average excluding in-progress sprints
- Added 27 comprehensive tests covering all planning scenarios

## Task Commits

Each task was committed atomically:

1. **Task 1: Create SprintPlan and PlanningHorizon models** - `c82c342` (feat)
2. **Task 2: Create VelocityTracker** - `862b7bd` (feat)
3. **Task 3: Add planning model tests** - `72055e9` (test)

## Files Created/Modified
- `src/planning/__init__.py` - Module exports for planning models
- `src/planning/models.py` - SprintPlan and PlanningHorizon with sprint lifecycle
- `src/planning/velocity_tracker.py` - VelocityTracker with capacity recommendations
- `tests/test_planning_models.py` - 27 tests covering all planning scenarios

## Decisions Made

**Pydantic v1 compatibility**: Fixed models to use `Config` class instead of `model_config` dict because anaconda environment has Pydantic v1.10.12 (pytest runner). Changed test to use `.dict()` instead of `.model_dump()`.

**Conservative capacity buffer**: VelocityTracker recommends 80% of average velocity by default, providing safety buffer for unknowns and dependencies.

**Dual planning trigger**: PlanningHorizon.needs_planning() returns True if either fewer than 2 sprints planned OR farthest sprint ends in less than 14 days (handles both count and time-based triggers).

**Velocity calculation excludes in-progress**: get_average_velocity() filters out in_progress sprints to avoid distortion from partial work during ongoing sprints.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed Pydantic v1/v2 compatibility**
- **Found during:** Task 3 (Test execution)
- **Issue:** Anaconda's pytest uses Python 3.11 with Pydantic v1.10.12, but models used Pydantic v2 syntax (model_config dict, model_dump())
- **Fix:** Changed `model_config = {...}` to `class Config: ...` in models.py, changed test to use `.dict()` instead of `.model_dump()`
- **Files modified:** src/planning/models.py, tests/test_planning_models.py
- **Verification:** All 27 tests pass with anaconda's pytest
- **Committed in:** 72055e9 (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (blocking)
**Impact on plan:** Essential fix for test execution. No scope creep - just environment compatibility.

## Issues Encountered

**Pydantic version mismatch**: System has both Python 3.12 (with Pydantic 2.11.10) and anaconda Python 3.11 (with Pydantic 1.10.12). Pytest runs via anaconda, so models must be Pydantic v1 compatible. Fixed by using Config class pattern that works in both versions.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

**Ready for sprint planner implementation (03-05):**
- SprintPlan tracks sprint dates, committed items, and scenario assignments
- PlanningHorizon.needs_planning() provides trigger for planning cycles
- VelocityTracker.get_capacity_recommendation() provides capacity for item selection
- All models tested and working

**No blockers.** Planning models foundation complete, ready to build SprintPlanner that uses these models to select backlog items and assign scenarios.

---
*Phase: 03-event-scheduler-queue-system*
*Completed: 2026-01-28*
