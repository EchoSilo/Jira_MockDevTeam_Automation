---
phase: 03-event-scheduler-queue-system
plan: 05
subsystem: scheduling
tags: [pendulum, datetime, business-hours, scenario-scripts, calendar-conversion]

# Dependency graph
requires:
  - phase: 03-01
    provides: "ScheduledAction dataclass with heap-compatible ordering"
  - phase: 03-03
    provides: "BusinessHoursScheduler for weekend/time validation"
provides:
  - "VirtualClock for simulation time advancement (45-minute ticks)"
  - "ScenarioScheduler converts script days (1-7) to calendar timestamps"
  - "Weekend skipping logic (Saturday/Sunday → Monday)"
  - "Random time distribution within business hours (9am-5pm)"
affects: [03-06, 03-07, 03-08]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Script day-to-calendar conversion with weekend skipping"
    - "Random time distribution within business hours for realistic patterns"
    - "VirtualClock abstraction for simulation time tracking"

key-files:
  created:
    - src/scheduling/virtual_clock.py
    - src/planning/scenario_scheduler.py
    - tests/test_scenario_scheduler.py
  modified:
    - src/planning/__init__.py

key-decisions:
  - "VirtualClock advances by 0.75 hours (45 minutes) to match n8n tick cadence"
  - "Weekend actions moved to Monday via BusinessHoursScheduler integration"
  - "Random time distribution uses uniform(0, 7.99) hours to stay within workday"
  - "Graceful handling of missing litellm dependency in planning module"
  - "Test dates corrected: Feb 2 2026 is Monday, not Feb 5 (Thursday)"

patterns-established:
  - "TDD cycle: RED (failing tests) → GREEN (implementation) → REFACTOR (cleanup)"
  - "Script actions with 'day' field (1-7) converted to pendulum.DateTime timestamps"
  - "Business hours constraint: 9am-5pm weekdays only"

# Metrics
duration: 6min
completed: 2026-01-28
---

# Phase 03 Plan 05: Scenario Scheduler Summary

**VirtualClock for simulation time and ScenarioScheduler converting sprint scripts (day 1-7) to calendar timestamps with weekend skipping and randomized business hours**

## Performance

- **Duration:** 6 minutes
- **Started:** 2026-01-28T13:47:43Z
- **Completed:** 2026-01-28T13:53:50Z
- **Tasks:** 3 (TDD cycle)
- **Files modified:** 4

## Accomplishments

- VirtualClock tracks simulation time independent of wall clock with configurable tick duration
- ScenarioScheduler converts relative script days (1-7) to actual calendar timestamps
- Weekend actions automatically moved to Monday (respects business hours)
- Actions distributed randomly throughout workday (9am-5pm) for realistic patterns
- 15 comprehensive tests covering VirtualClock and ScenarioScheduler functionality

## Task Commits

Each task was committed atomically following TDD cycle:

1. **Task 1: Write failing tests** - `1b6837f` (test)
   - 6 VirtualClock tests (now, advance, set_time, custom tick duration)
   - 9 ScenarioScheduler tests (day mapping, weekend skipping, time randomization)
   - All 15 tests failing (RED phase)

2. **Task 2: Implement VirtualClock** - `20feb5d` (feat)
   - Simple wrapper around pendulum.DateTime with add() for time advancement
   - Default tick_duration_hours: 0.75 (45 minutes matches n8n cadence)
   - All 6 VirtualClock tests pass (GREEN phase)

3. **Task 3: Implement ScenarioScheduler** - `aead6c6` (feat)
   - Converts script day numbers (1-7) to calendar timestamps
   - Weekend actions moved to Monday via BusinessHoursScheduler
   - Random time distribution within 8-hour workday
   - Fixed planning module __init__.py to handle missing litellm dependency
   - Corrected test dates (Feb 2 2026 is Monday)
   - All 15 tests pass (GREEN phase)

## Files Created/Modified

- `src/scheduling/virtual_clock.py` - VirtualClock for simulation time advancement
- `src/planning/scenario_scheduler.py` - Converts scenario scripts to scheduled actions
- `tests/test_scenario_scheduler.py` - 15 comprehensive tests for both classes
- `src/planning/__init__.py` - Added conditional import for BacklogPrioritizer (missing litellm)

## Decisions Made

**VirtualClock tick duration:** Default 0.75 hours (45 minutes) matches n8n cron cadence for realistic simulation pacing

**Weekend skipping strategy:** Use BusinessHoursScheduler.next_business_day() to move Saturday/Sunday actions to Monday at business hours start

**Time randomization:** Random offset 0-7.99 hours from 9am ensures actions stay within 9am-5pm window without spilling to next day

**Test date selection:** Feb 2 2026 (Monday) chosen for predictable weekday testing vs Feb 5 (Thursday)

**Conditional imports:** BacklogPrioritizer import wrapped in try/except to allow tests to run despite missing litellm dependency

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed planning module import error**
- **Found during:** Task 3 (ScenarioScheduler tests)
- **Issue:** `src.planning.__init__.py` unconditionally imported `BacklogPrioritizer` which requires `litellm` package (not installed)
- **Fix:** Wrapped BacklogPrioritizer import in try/except block, added conditional __all__ export
- **Files modified:** `src/planning/__init__.py`
- **Verification:** ScenarioScheduler imports successfully, tests run
- **Committed in:** aead6c6 (Task 3 commit)

**2. [Rule 1 - Bug] Corrected test date assumptions**
- **Found during:** Task 3 (ScenarioScheduler test failures)
- **Issue:** Tests assumed Feb 5 2026 was Wednesday (actually Thursday), causing date assertion failures
- **Fix:** Changed sprint_start dates to Feb 2 2026 (Monday) for predictable weekday math
- **Files modified:** `tests/test_scenario_scheduler.py`
- **Verification:** All 15 tests pass with correct date arithmetic
- **Committed in:** aead6c6 (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking import, 1 bug)
**Impact on plan:** Both auto-fixes necessary for tests to run. No scope creep.

## Issues Encountered

**Time distribution initially pushed to next day:** First implementation used random.uniform(0, 8) which could add 8+ hours including minutes, pushing Friday 9am + 8 hours to after 5pm. Fixed by capping at 7.99 hours and setting time directly at business hours start + offset.

**BusinessHoursScheduler.next_business_day() adds a day first:** Method designed for "next" business day, not "current or next". Addressed by checking is_business_day() first in _distribute_time_within_day().

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

**Ready for next phase:**
- VirtualClock provides simulation time tracking for testing
- ScenarioScheduler ready to convert scenario scripts to action queues
- Weekend skipping and business hours enforcement working correctly

**Next steps:**
- Load scenario scripts from JSON files (03-06)
- Integrate ScenarioScheduler with sprint planning (03-07)
- Build execution queue with VirtualClock for time-based triggering (03-08)

**No blockers or concerns**

---
*Phase: 03-event-scheduler-queue-system*
*Completed: 2026-01-28*
