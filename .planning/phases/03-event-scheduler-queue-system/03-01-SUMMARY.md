---
phase: 03-event-scheduler-queue-system
plan: 01
subsystem: scheduling
tags: [pendulum, heapq, priority-queue, tdd, datetime, scheduling]

# Dependency graph
requires:
  - phase: 01-time-infrastructure
    provides: Clock abstraction with Pendulum for timezone-safe operations
provides:
  - ScheduledAction model with execution windows and status tracking
  - ActionPriorityQueue for efficient "what's due now?" queries
  - Heap-based action scheduling with O(log n) operations
affects: [03-02, 03-03, 03-04, 03-05, 03-06]

# Tech tracking
tech-stack:
  added: [heapq (stdlib), dataclasses (stdlib)]
  patterns: [TDD with RED-GREEN-REFACTOR, heap-based priority scheduling, execution windows]

key-files:
  created:
    - src/scheduling/models.py
    - src/scheduling/priority_queue.py
    - tests/test_scheduling_models.py
    - tests/test_priority_queue.py
  modified:
    - src/scheduling/__init__.py

key-decisions:
  - "Use @dataclass(order=True) with scheduled_time as comparison key for automatic heap ordering"
  - "Mark canceled actions as SKIPPED instead of removing from heap (heapq doesn't support efficient removal)"
  - "Default 30-minute execution window for all actions"
  - "Actions remain in heap after completion/skip; get_due_actions() filters by status"

patterns-established:
  - "TDD pattern: Write failing tests first, implement to pass, commit atomically"
  - "Execution window pattern: scheduled_time + window_minutes defines when action is due"
  - "Status lifecycle: PENDING → READY/COMPLETED/SKIPPED/ADAPTED"

# Metrics
duration: 13min
completed: 2026-01-28
---

# Phase 03 Plan 01: Action Scheduling Foundation Summary

**Heap-based priority queue with execution windows enabling efficient "what's due now?" queries in O(log n) time using pendulum timestamps**

## Performance

- **Duration:** 13 min
- **Started:** 2026-01-28T08:33:46Z
- **Completed:** 2026-01-28T08:46:32Z
- **Tasks:** 2 (TDD with 3 commits)
- **Files modified:** 5
- **Tests:** 41 tests, 100% pass

## Accomplishments

- ScheduledAction model with is_due()/is_overdue() methods for execution window checking
- ActionPriorityQueue with heap-based O(log n) push/pop operations
- 30-minute default execution windows for realistic action scheduling
- Comprehensive test coverage (20 ScheduledAction tests, 21 priority queue tests)

## Task Commits

Each task was committed atomically following TDD:

1. **Task 1: ScheduledAction Model** - TDD cycle
   - `47d16dc` test(03-01): add tests for ScheduledAction model
   - *(implementation from 03-02: models.py already existed)*

2. **Task 2: ActionPriorityQueue** - TDD cycle
   - `198356a` test(03-01): add tests for ActionPriorityQueue
   - `26bed91` feat(03-01): implement ActionPriorityQueue

## Files Created/Modified

- `src/scheduling/models.py` - ScheduledAction dataclass with ActionStatus enum, execution window methods
- `src/scheduling/priority_queue.py` - Heap-based priority queue with push/pop/get_due_actions
- `src/scheduling/__init__.py` - Module exports for ScheduledAction, ActionStatus, ActionPriorityQueue
- `tests/test_scheduling_models.py` - 20 tests covering ScheduledAction behavior
- `tests/test_priority_queue.py` - 21 tests covering priority queue operations

## Decisions Made

**1. Use @dataclass(order=True) for automatic heap ordering**
- **Rationale:** Python's heapq requires orderable objects. By making scheduled_time the first field with order=True, actions automatically sort by scheduled_time (earliest first)
- **Impact:** Eliminates need for custom comparison or wrapper classes

**2. Mark canceled actions as SKIPPED instead of heap removal**
- **Rationale:** heapq doesn't support efficient removal of arbitrary elements (requires O(n) search + reheapify)
- **Impact:** Canceled actions remain in heap but are excluded from get_due_actions() via status filter

**3. 30-minute default execution window**
- **Rationale:** Balances flexibility (action can execute within reasonable time after scheduled_time) with urgency detection (overdue after 30 minutes)
- **Impact:** Actions have "soft" deadlines; is_overdue() triggers at scheduled_time + 30 minutes

**4. Actions remain in heap after completion**
- **Rationale:** Simplifies queue management (no need to clean up after every execution)
- **Impact:** get_due_actions() filters by status == PENDING; completed/skipped actions accumulate in heap

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Modified test to avoid pendulum time travel dependency**
- **Found during:** Running ScheduledAction tests
- **Issue:** Test used pendulum.travel_to() which requires optional "test" extra not installed
- **Fix:** Changed test_mark_completed to check executed_at is within before_time/after_time range instead of exact time
- **Files modified:** tests/test_scheduling_models.py
- **Verification:** All 20 ScheduledAction tests pass without pendulum[test] dependency
- **Committed in:** 47d16dc (test commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Test modification necessary to run without optional dependency. No behavioral changes to implementation.

## Issues Encountered

None - plan executed smoothly following TDD methodology.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

**Ready for next phases:**
- ScheduledAction model provides foundation for scenario script storage (03-02)
- ActionPriorityQueue enables BusinessHoursScheduler to query due actions (03-03)
- Execution window pattern supports capacity-aware scheduling (03-04)
- Status tracking (PENDING/COMPLETED/SKIPPED) enables scenario progress monitoring (03-05)

**No blockers.**

**Context for next phases:**
- ScheduledAction.scenario_id links actions to scenario scripts
- ScheduledAction.params stores action-specific data (ticket_key, comment text, etc.)
- ActionPriorityQueue.get_due_actions() is the core query for "what should run now?"
- Overdue detection (is_overdue) enables staleness cleanup and adaptive scheduling

---
*Phase: 03-event-scheduler-queue-system*
*Completed: 2026-01-28*
