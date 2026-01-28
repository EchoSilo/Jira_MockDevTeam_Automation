---
phase: 01-time-infrastructure
plan: 03
subsystem: infra
tags: [pendulum, timezone, utc, clock, testing, time]

# Dependency graph
requires:
  - phase: 01-01
    provides: Clock abstraction (RealClock/FakeClock) with Protocol interface
  - phase: 01-02
    provides: Clean state model without virtual time fields
provides:
  - All datetime calls migrated to pendulum.now("UTC") for timezone-aware timestamps
  - Clock injected into ScenarioOrchestrator for deterministic testing
  - Zero naive datetime calls in codebase
  - Pydantic models use pendulum for default timestamps
affects: [01-04, testing, all-future-time-dependent-code]

# Tech tracking
tech-stack:
  added: [pendulum (timezone-aware datetime library)]
  patterns:
    - "Clock injection pattern: orchestrator accepts Clock parameter with RealClock default"
    - "Pydantic timestamp pattern: Field(default_factory=lambda: pendulum.now('UTC'))"
    - "pendulum.now('UTC') for all one-off timestamps in methods"

key-files:
  created: []
  modified:
    - src/state/models.py
    - src/logging/models.py
    - src/scenarios/sprint_scenario.py
    - src/orchestrator/orchestrator.py
    - src/orchestrator/analyzer.py
    - src/agents/coordinator_agent.py
    - src/agents/release_manager_agent.py
    - src/main.py
    - src/state/simulation_state.py
    - src/services/jira_client.py
    - src/logging/writer.py
    - src/logging/database.py

key-decisions:
  - "Use pendulum.now('UTC') for Pydantic defaults and one-off timestamps (simple, consistent)"
  - "Inject Clock into orchestrator only (main execution path for testing control)"
  - "Replace all datetime.utcnow() and datetime.now(timezone.utc) calls (eliminates naive datetime bugs)"

patterns-established:
  - "Clock injection: ScenarioOrchestrator.__init__ accepts clock: Clock = None parameter"
  - "Pydantic timestamps: Use lambda: pendulum.now('UTC') in Field default_factory"
  - "Method timestamps: Direct pendulum.now('UTC') calls for consistency"

# Metrics
duration: 10min
completed: 2026-01-28
---

# Phase 1 Plan 3: Clock Injection & UTC Migration Summary

**Migrated 40+ datetime calls to pendulum/Clock: timezone-aware UTC timestamps throughout codebase with Clock injection for testable orchestration**

## Performance

- **Duration:** 10 min
- **Started:** 2026-01-28T05:58:44Z
- **Completed:** 2026-01-28T06:08:54Z
- **Tasks:** 3
- **Files modified:** 12

## Accomplishments
- All Pydantic model defaults use pendulum.now("UTC") for timezone-aware timestamps
- Clock injected into ScenarioOrchestrator with RealClock default
- Zero datetime.utcnow() or naive datetime.now() calls in entire src/
- Tests can inject FakeClock for deterministic time control
- All imports verified working without errors

## Task Commits

Each task was committed atomically:

1. **Task 1: Migrate Pydantic model defaults to pendulum** - `f4cd242` (refactor)
2. **Task 2: Migrate orchestrator, analyzer, and agents to Clock/pendulum** - `2d62f94` (refactor)
3. **Task 3: Migrate remaining files and wire Clock into main.py** - `5fd8be9` (refactor)

## Files Created/Modified

### Pydantic Models (Task 1)
- `src/state/models.py` - All Field default_factory calls use pendulum.now("UTC"), method bodies use pendulum
- `src/logging/models.py` - All log entry timestamps use pendulum.now("UTC")
- `src/scenarios/sprint_scenario.py` - Sprint scenario timestamps use pendulum.now("UTC")

### Orchestrator & Agents (Task 2)
- `src/orchestrator/orchestrator.py` - Clock injection in __init__, self.clock.now() for tick timing, self.clock.today() for dates
- `src/orchestrator/analyzer.py` - pendulum.now("UTC") for analysis timestamps
- `src/agents/coordinator_agent.py` - pendulum.now("UTC") for directive timestamps
- `src/agents/release_manager_agent.py` - pendulum.now("UTC") for release planning

### Main & Services (Task 3)
- `src/main.py` - All datetime.now(timezone.utc) replaced with pendulum.now("UTC"), RealClock wired to orchestrator
- `src/state/simulation_state.py` - pendulum.now("UTC") for state management
- `src/services/jira_client.py` - pendulum.now("UTC") for cache timestamps
- `src/logging/writer.py` - pendulum.now("UTC") for session timestamps
- `src/logging/database.py` - pendulum.now("UTC") for log retention cutoff

## Decisions Made

**1. Use pendulum for all timestamps (not just Clock injection)**
- Rationale: Consistent timezone-aware datetime handling across entire codebase
- Pattern: pendulum.now("UTC") returns timezone-aware datetime that works with Pydantic
- Benefit: Eliminates naive datetime bugs, works seamlessly with existing datetime comparisons

**2. Inject Clock only into ScenarioOrchestrator**
- Rationale: Orchestrator is main execution path where time control matters for testing
- Alternative considered: Inject into every service/agent (too complex, unclear benefit)
- Benefit: Single injection point keeps migration simple, enables test time control where needed

**3. Replace datetime.now(timezone.utc) with pendulum.now("UTC")**
- Rationale: Consistent API, better timezone support, same timezone-aware output
- Pattern: All datetime.now(timezone.utc) → pendulum.now("UTC")
- Benefit: Unified time handling, prepares for future business hours/DST work

## Deviations from Plan

None - plan executed exactly as written.

All 40+ datetime calls migrated without issues. No unexpected dependencies or blockers.

## Issues Encountered

None - migration completed smoothly.

All imports verified working. Verification checks confirmed:
- Zero datetime.utcnow() calls in src/
- Zero naive datetime.now() calls in src/
- All imports succeed
- RecentAction timestamp is timezone-aware UTC

## User Setup Required

None - no external service configuration required.

This is an internal refactor with no user-facing changes.

## Next Phase Readiness

**Ready for Phase 1 Plan 4 (Business hours enforcement):**
- Clock abstraction ready for business hours logic
- All timestamps timezone-aware for DST handling
- pendulum library available for business hours calculations
- No blockers or concerns

**Key context for plan 01-04:**
- ScenarioOrchestrator has clock: Clock parameter
- All timestamps use pendulum.now("UTC")
- RealClock instantiated in main.py trigger_simulation() function
- Tests can inject FakeClock to bypass business hours in test scenarios

---
*Phase: 01-time-infrastructure*
*Completed: 2026-01-28*
