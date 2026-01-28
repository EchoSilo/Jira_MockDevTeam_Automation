---
phase: 04-adaptive-pathfinding-chaos-injection
plan: 03
subsystem: chaos-injection
tags: [chaos-engineering, yaml, event-catalog, scenario-archetypes, weighted-selection]

# Dependency graph
requires:
  - phase: 04-01
    provides: ChaosEventType enum, RandomEvent dataclass, ChaosConfig
  - phase: 03
    provides: ScenarioArchetype enum from sprint scenarios
provides:
  - EventCatalog class with template lookup and archetype-aware weight adjustment
  - chaos_events.yaml configuration with 6 event templates and 6 archetype weight profiles
  - Scenario-aware chaos injection capability
affects: [04-04-random-event-generator, 04-05-agent-adaptive-pathfinding]

# Tech tracking
tech-stack:
  added: []
  patterns: [event-catalog-pattern, archetype-weight-multipliers]

key-files:
  created:
    - config/chaos_events.yaml
    - src/chaos/event_catalog.py
    - tests/test_event_catalog.py
  modified:
    - src/chaos/__init__.py

key-decisions:
  - "Weight multipliers instead of absolute probabilities for archetype adjustments"
  - "Blocker-heavy sprints get 2.0x external blockers vs baseline"
  - "Smooth sprints get 0.2-0.5x disruptions across all event types"
  - "Recovery sprints minimize new disruptions (0.2-0.5x) for stabilization"

patterns-established:
  - "EventCatalog: Central registry for event templates with archetype-aware weighting"
  - "Template pattern: description_template, default_severity, requires_response_action"
  - "Weight multiplier pattern: 1.0 = baseline, 2.0 = double, 0.5 = half"

# Metrics
duration: 3min
completed: 2026-01-28
---

# Phase 4 Plan 3: Event Catalog with Archetype Weights Summary

**Event catalog with scenario-aware chaos injection using archetype weight multipliers for 6 sprint types**

## Performance

- **Duration:** 3 min
- **Started:** 2026-01-28T20:31:04Z
- **Completed:** 2026-01-28T20:34:21Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- Event catalog with templates for all 6 chaos event types
- Archetype-specific weight multipliers for 6 sprint types
- EventCatalog class with probability adjustment by scenario archetype
- Blocker-heavy sprints get 2x external blockers, smooth sprints get 0.2-0.5x disruptions

## Task Commits

Each task was committed atomically:

1. **Task 1: Create chaos_events.yaml configuration** - `0146641` (feat)
2. **Task 2: Create EventCatalog class** - `0d3ce4b` (feat)
3. **Task 3: Add unit tests for EventCatalog** - `8b7d030` (test)

## Files Created/Modified
- `config/chaos_events.yaml` - Event templates and archetype weight multipliers
- `src/chaos/event_catalog.py` - EventCatalog class with template lookup and weight adjustment
- `src/chaos/__init__.py` - Export EventCatalog
- `tests/test_event_catalog.py` - Comprehensive test coverage (15 tests)

## Decisions Made

**Weight multipliers for archetype-aware chaos intensity:**
- Smooth sprints: 0.2-0.5x multipliers (minimal disruptions)
- Blocker-heavy: 2.0x external_blocker (double baseline)
- Overloaded: 1.5x urgent_bug and priority_shift
- Rework: 1.5x urgent_bug (more bugs from rework cycle)
- Crunch: 0.3x team_absence (no absences during crunch)
- Recovery: 0.2-0.5x new disruptions (stabilization focus)

**Response action pattern:**
- Templates include requires_response_action flag
- Production outages require tech_lead emergency_response
- External blockers require pm blocker_discussion
- Urgent bugs require developer fix_urgent_bug

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

**Test enum naming mismatch:**
- Initial tests used uppercase enum names (ChaosEventType.PRODUCTION_OUTAGE)
- ChaosEventType uses lowercase_underscore (ChaosEventType.production_outage)
- Fixed with global replace across test file
- All 15 tests passing after correction

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

**Ready for next phases:**
- Event catalog provides templates for RandomEventGenerator (04-04)
- Archetype weight system ready for integration with scenario engine
- Response action patterns defined for adaptive agent behavior (04-05)

**Integration points:**
- RandomEventGenerator will use EventCatalog to select and format events
- Scenario engine will pass current archetype to adjust_probabilities()
- Agent pathfinding will use response_action details for adaptive responses

**Verification:**
- All 15 EventCatalog tests passing
- Blocker-heavy archetype correctly doubles external blocker probability (0.15 → 0.30)
- Templates loaded for all 6 event types and 6 archetypes

---
*Phase: 04-adaptive-pathfinding-chaos-injection*
*Completed: 2026-01-28*
