---
phase: 03-event-scheduler-queue-system
plan: 06
subsystem: planning
tags: [capacity-planning, llm-ranking, backlog-prioritization, velocity-tracking, caching]

# Dependency graph
requires:
  - phase: 03-event-scheduler-queue-system
    plan: 04
    provides: VelocityTracker for capacity calculations
provides:
  - CapacityPlanner for selecting backlog items within capacity limits
  - BacklogPrioritizer for LLM-based business value ranking with caching
affects: [sprint-planning, backlog-management, pm-agent]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Capacity-based sprint planning with 80% velocity buffer"
    - "LLM-based backlog prioritization with 24-hour caching"
    - "Fallback prioritization by type and priority when LLM unavailable"
    - "Lazy import of litellm for test isolation"

key-files:
  created:
    - src/planning/capacity_planner.py
    - src/planning/backlog_prioritizer.py
    - tests/test_capacity_planning.py
  modified:
    - src/planning/__init__.py

key-decisions:
  - "Lazy import of litellm: Import inside method to avoid test dependency issues"
  - "80% capacity buffer default: Conservative estimate for unknown complexity"
  - "24-hour cache for prioritization: Balance cost savings with freshness"
  - "Type-based fallback: Bugs > Tasks > Stories > Features when LLM fails"
  - "Routine model (Haiku) for prioritization: Cost-effective for ranking task"

patterns-established:
  - "CapacityPlanner uses VelocityTracker for historical capacity calculation"
  - "BacklogPrioritizer accepts pre-sorted backlog or sorts via LLM"
  - "Estimate unestimated items by type (Bug: 2, Task: 3, Story: 5, Feature: 8)"
  - "Cache invalidation based on backlog composition and time elapsed"

# Metrics
duration: 11min
completed: 2026-01-28
---

# Phase 03 Plan 06: Capacity Planning & Backlog Prioritization Summary

**Velocity-based capacity planning with LLM business value ranking and 24-hour caching**

## Performance

- **Duration:** 11 min
- **Started:** 2026-01-28T13:42:35Z
- **Completed:** 2026-01-28T13:53:11Z
- **Tasks:** 3
- **Files created:** 3

## Accomplishments

- Created CapacityPlanner for selecting backlog items within velocity-derived capacity
- Built BacklogPrioritizer using LLM (Haiku) for business value ranking with 24-hour cache
- Added 22 comprehensive tests (10 for CapacityPlanner, 12 for BacklogPrioritizer)
- Implemented fallback prioritization (type + priority) for LLM failures
- Lazy import of litellm for test isolation without requiring dependency

## Task Commits

Each task was committed atomically:

1. **Task 1: Create CapacityPlanner** - `2ccf646` (feat)
2. **Task 2: Create BacklogPrioritizer** - `4b5a616` (feat)
3. **Task 3: Add capacity planning tests** - `4bd620b` (test)

## Files Created/Modified

- `src/planning/capacity_planner.py` - Capacity-based item selection using VelocityTracker
- `src/planning/backlog_prioritizer.py` - LLM-based ranking with caching and fallback
- `tests/test_capacity_planning.py` - 22 tests covering all planning scenarios
- `src/planning/__init__.py` - Added exports for CapacityPlanner and BacklogPrioritizer

## Decisions Made

**Lazy import of litellm**: Import litellm inside the `prioritize()` method rather than at module level. This allows tests to run without the litellm dependency by mocking via `sys.modules`. Prevents `ModuleNotFoundError` during test collection.

**Conservative 80% capacity buffer**: CapacityPlanner defaults to 80% of historical velocity to provide buffer for unknowns, dependencies, and unplanned work. Prevents sprint overcommitment.

**24-hour cache for prioritization**: BacklogPrioritizer caches LLM results for 24 hours to reduce API costs. Cache invalidates when backlog composition changes or time expires. Balances cost savings with freshness.

**Type-based fallback prioritization**: When LLM fails or is unavailable, fall back to type priority (Bug > Task > Story > Feature) then Jira priority field. Ensures graceful degradation without blocking sprint planning.

**Routine model (Haiku) for ranking**: Use claude-3-5-haiku for backlog prioritization since it's a simpler ranking task. Saves cost compared to Sonnet while maintaining quality for structured output.

## Deviations from Plan

None - plan executed exactly as written. All tasks completed successfully with all tests passing.

## Issues Encountered

**litellm import in tests**: Initial implementation had module-level import of litellm, causing test collection failures when litellm wasn't installed. Fixed by:
1. Moving import inside method (lazy import)
2. Using `patch.dict(sys.modules, {'litellm': mock})` in tests for proper mocking

No blocking issues - fix applied during Task 3 development.

## User Setup Required

None - no external service configuration required. LLMService already configured in existing codebase.

## Next Phase Readiness

**Ready for sprint planner implementation:**
- CapacityPlanner.select_items() provides capacity-aware item selection
- BacklogPrioritizer.prioritize() ranks backlog by business value
- VelocityTracker provides capacity recommendations from historical data
- All components tested and working

**Integration points for PM agent:**
- PM agent will use BacklogPrioritizer to rank backlog items
- Then use CapacityPlanner to select items fitting within capacity
- VelocityTracker provides capacity based on last 3 completed sprints

**No blockers.** Capacity planning foundation complete, ready for PM agent integration.

---
*Phase: 03-event-scheduler-queue-system*
*Completed: 2026-01-28*
