---
phase: 04-adaptive-pathfinding-chaos-injection
plan: 02
subsystem: chaos-injection
tags: [chaos-engineering, random-events, probability, testing, tdd]

# Dependency graph
requires:
  - phase: 04-01
    provides: RandomEvent model and ChaosConfig loader with validation
provides:
  - RandomEventGenerator with two-stage probability rolling
  - Weighted event type selection using random.choices
  - Event-specific creation logic for all 6 chaos types
  - Deterministic seed support for testing
affects: [04-03-event-catalog, 04-04-coordinator, 04-05-integration]

# Tech tracking
tech-stack:
  added: [random.Random for seeded randomness]
  patterns: [TDD with RED-GREEN cycles, probability-based event generation, event-specific factory methods]

key-files:
  created:
    - src/chaos/event_generator.py
    - tests/test_event_generator.py
  modified:
    - src/chaos/__init__.py

key-decisions:
  - "Use stdlib random.Random with seed for deterministic testing"
  - "Two-stage dice rolling: base chance then weighted selection"
  - "Event-specific creation logic in _create_event() method"
  - "team_absence affects agents, other events affect tickets"

patterns-established:
  - "Seeded RNG pattern: Pass optional seed to constructor, use self.rng throughout"
  - "Event factory pattern: Single _create_event() method handles all event types"
  - "Probability filtering: Zero-probability events filtered before weighted selection"

# Metrics
duration: 3min
completed: 2026-01-28
---

# Phase 04 Plan 02: Random Event Generator Summary

**Probability-based chaos event generator with two-stage dice rolling and deterministic seed support for testing**

## Performance

- **Duration:** 3 min
- **Started:** 2026-01-28T20:31:06Z
- **Completed:** 2026-01-28T20:34:05Z
- **Tasks:** 2 (TDD: RED → GREEN)
- **Files modified:** 3

## Accomplishments
- RandomEventGenerator with configurable probability-based event generation
- Two-stage dice rolling: base_event_chance then weighted event type selection
- Event-specific creation logic for all 6 chaos types with proper targeting
- Comprehensive test suite with 13 tests verifying probability behavior and determinism
- production_outage always critical severity, team_absence affects agents with duration

## Task Commits

Each TDD task was committed atomically:

1. **Task 1: RED - Write failing tests** - `feb97f2` (test)
   - 13 comprehensive tests for probability behavior
   - Tests for zero-probability filtering
   - Tests for event-specific targeting rules
   - Tests for deterministic behavior with seeds

2. **Task 2: GREEN - Implement RandomEventGenerator** - `caa7596` (feat)
   - RandomEventGenerator class with seeded random.Random
   - roll_for_event() with two-stage probability logic
   - _create_event() with event-type-specific details
   - All 13 tests passing

_TDD cycle: RED (failing tests) → GREEN (implementation) → No refactor needed_

## Files Created/Modified
- `src/chaos/event_generator.py` - RandomEventGenerator with probability rolling and event creation
- `tests/test_event_generator.py` - 13 tests verifying generator behavior (281 lines)
- `src/chaos/__init__.py` - Export RandomEventGenerator

## Decisions Made

**Two-stage dice rolling approach:**
- Stage 1: Roll against base_event_chance (e.g., 0.1 = 10% per tick)
- Stage 2: If triggered, weighted random.choices() selects event type
- Rationale: Separates "should event occur" from "which event" decisions

**Seeded random.Random for testing:**
- Constructor accepts optional seed parameter
- Deterministic sequences enable reliable test assertions
- Production uses seed=None for non-deterministic behavior

**Event-specific targeting rules:**
- production_outage: 2-3 tickets, always critical severity
- urgent_bug: 1-2 tickets, high severity
- team_absence: 1 agent, 2-4 tick duration, medium severity
- external_blocker: 1 ticket, medium severity
- priority_shift: 1-2 tickets, medium severity
- scope_change: 1 ticket, high severity

**Zero-probability filtering:**
- Events with probability 0.0 excluded before weighted selection
- Prevents impossible events from being selected
- Verified by test_zero_probability_events_never_selected

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test assertion for team_absence events**
- **Found during:** Task 2 (GREEN phase test run)
- **Issue:** Test assumed all events affect tickets, but team_absence legitimately affects agents only
- **Fix:** Added conditional check - team_absence verifies affected_agents > 0, others verify affected_tickets > 0
- **Files modified:** tests/test_event_generator.py
- **Verification:** All 13 tests pass
- **Committed in:** caa7596 (part of GREEN phase commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Necessary correction for proper validation of different event types. No scope creep.

## Issues Encountered
None - TDD flow worked smoothly with RED → GREEN cycle completing in one iteration.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness

**Ready for 04-03 (EventCatalog):**
- RandomEventGenerator can create events on demand
- Deterministic seed support enables testing
- All 6 event types working with proper targeting

**Ready for 04-04 (Coordinator):**
- Generator provides roll_for_event() interface
- Returns Optional[RandomEvent] for easy null checking
- Config-driven enable/disable via ChaosConfig.enabled

**No blockers:** All CHAOS-01, CHAOS-03, CHAOS-04 requirements met.

---
*Phase: 04-adaptive-pathfinding-chaos-injection*
*Completed: 2026-01-28*
