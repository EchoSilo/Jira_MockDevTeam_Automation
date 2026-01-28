---
phase: 03
plan: 08
subsystem: sprint-planning
tags: [sprint-planning, planning-horizon, velocity-tracking, capacity-planning, scheduling-integration]

requires:
  - 03-04-SUMMARY  # ScenarioScheduler for converting scripts to calendar timestamps
  - 03-05-SUMMARY  # VirtualClock for simulation time
  - 03-06-SUMMARY  # CapacityPlanner, VelocityTracker, BacklogPrioritizer
  - 03-07-SUMMARY  # Scheduler, ScheduledAction for action scheduling

provides:
  - SprintPlanner orchestrator for full sprint planning flow
  - SimulationState planning fields (planning_horizon, velocity_tracker)
  - Sprint planning trigger logic (horizon < 2 sprints)
  - Sprint configuration in settings.yaml

affects:
  - 03-01  # Orchestrator will integrate SprintPlanner for planning triggers
  - 04-*   # Sprint planning provides foundation for realistic sprint lifecycle

tech-stack:
  added: []
  patterns:
    - "Sprint planning orchestration with backlog -> capacity -> scheduling flow"
    - "Planning horizon management (2-3 future sprints)"
    - "Velocity-based capacity planning with 80% buffer"
    - "Wednesday sprint starts (configurable)"

key-files:
  created:
    - src/planning/sprint_planner.py
    - tests/test_sprint_planning_flow.py
  modified:
    - src/state/models.py
    - src/planning/__init__.py
    - config/settings.yaml

decisions:
  - decision: "Add planning_horizon and velocity_tracker to SimulationState as serialized dicts"
    rationale: "Enables state persistence while avoiding circular imports"
    phase: 03-08
    date: 2026-01-28
  - decision: "SprintPlanner uses mode='json' for model_dump()"
    rationale: "Ensures pendulum.DateTime objects serialize to ISO strings in Pydantic v2"
    phase: 03-08
    date: 2026-01-28
  - decision: "Fallback prioritization by type when LLM unavailable"
    rationale: "Graceful degradation: Bug > Task > Story > Feature when BacklogPrioritizer fails"
    phase: 03-08
    date: 2026-01-28
  - decision: "Default capacity of 20 points for new teams"
    rationale: "Reasonable starting point when no velocity history exists"
    phase: 03-08
    date: 2026-01-28

metrics:
  duration: "9 minutes"
  completed: 2026-01-28
  commits: 4
  tests-added: 15
  tests-passing: 15
---

# Phase 3 Plan 08: Sprint Planning Flow & State Integration Summary

Sprint planning orchestrator integrating backlog fetching, LLM prioritization, velocity-based capacity planning, scenario generation, and action scheduling with planning horizon management in SimulationState.

## What Was Built

### Core Components

**1. SimulationState Planning Fields (src/state/models.py)**
- Added `planning_horizon` field (serialized PlanningHorizon)
- Added `velocity_tracker` field (serialized VelocityTracker)
- Added `get_planning_horizon()` / `set_planning_horizon()` methods
- Added `get_velocity_tracker()` / `set_velocity_tracker()` methods
- Added `needs_sprint_planning()` method (checks horizon < 2 sprints)

**2. SprintPlanner Orchestrator (src/planning/sprint_planner.py)**
- `check_and_plan()`: Triggers planning when horizon < 2 sprints
- `plan_next_sprint()`: Full planning flow
  - Fetch backlog from Jira (Story/Bug/Task)
  - Prioritize using BacklogPrioritizer (with fallback to type-based)
  - Calculate capacity from velocity (80% buffer)
  - Select items within capacity
  - Generate scenario scripts
  - Schedule actions via ScenarioScheduler
  - Create sprint in Jira
  - Update planning horizon
- `_calculate_sprint_start()`: Wednesday start dates (configurable)
- `record_sprint_completion()`: Track velocity after sprint ends

**3. Configuration (config/settings.yaml)**
- `sprint.start_day`: wednesday
- `sprint.planning_horizon_sprints`: 3
- `sprint.capacity_buffer`: 0.8
- `scheduler.tick_duration_hours`: 0.75
- `scheduler.execution_window_minutes`: 30
- `scheduler.max_actions_per_tick`: 4

**4. Integration Tests (tests/test_sprint_planning_flow.py)**
- 15 tests covering:
  - Planning trigger logic
  - Sprint plan creation
  - State updates
  - Wednesday sprint starts
  - Velocity-based capacity
  - Sprint completion recording
  - Fallback prioritization
  - SimulationState integration

## Planning Flow

```
1. Check Horizon
   └─> needs_sprint_planning() → horizon < 2 sprints?

2. Fetch Backlog
   └─> JiraClient.get_issues_not_in_sprint([Story, Bug, Task])

3. Prioritize
   └─> BacklogPrioritizer (LLM) OR fallback (Bug > Task > Story > Feature)

4. Calculate Capacity
   └─> VelocityTracker.get_average_velocity() * 0.8

5. Select Items
   └─> CapacityPlanner.select_items(backlog, capacity)

6. Generate Scenario
   └─> _generate_item_script() → [pick_up, progress, review, qa]

7. Schedule Actions
   └─> ScenarioScheduler.convert_scenario_to_actions()
   └─> Scheduler.schedule_actions()

8. Create Jira Sprint
   └─> JiraClient.create_sprint(name, start_date, end_date)

9. Update State
   └─> horizon.add_sprint_plan(sprint_plan)
   └─> state.set_planning_horizon(horizon)
```

## Key Design Decisions

### Serialized Planning State
Store planning_horizon and velocity_tracker as dicts in SimulationState, convert to Pydantic models on access. Avoids circular imports and enables JSON persistence.

### Wednesday Sprint Starts
Configurable `start_day` (default: wednesday) ensures realistic sprint cadence aligned with common real-world practices (mid-week planning).

### Fallback Prioritization
When LLM unavailable, fall back to type-based priority: Bug (highest) > Task > Story > Feature. Ensures graceful degradation.

### Conservative Capacity
Use 80% of average velocity as capacity buffer. Accounts for unknowns and prevents over-commitment.

### Default Capacity for New Teams
When no velocity history exists, use default capacity of 20 points. Reasonable starting point for initial sprint planning.

## Test Coverage

All 15 tests passing:

**SprintPlanner Tests (9)**
- ✓ Planning triggers when horizon < 2 sprints
- ✓ Planning skips when horizon sufficient
- ✓ plan_next_sprint creates sprint plan
- ✓ Planning updates SimulationState
- ✓ Sprint dates start Wednesday
- ✓ Velocity affects capacity
- ✓ record_sprint_completion tracks velocity
- ✓ Fallback prioritization works
- ✓ Multiple items selected within capacity

**SimulationState Integration Tests (6)**
- ✓ needs_sprint_planning detects empty horizon
- ✓ needs_sprint_planning detects sufficient horizon
- ✓ VelocityTracker round-trips through state
- ✓ PlanningHorizon round-trips through state
- ✓ Empty horizon creates default
- ✓ Empty velocity creates default

## Integration Points

### With Phase 2 (Reconciliation)
- No direct integration yet
- Future: Pre-execution validation before scheduling actions

### With Phase 3 Components
- **03-04 (ScenarioScheduler)**: Converts day-based scripts to calendar timestamps
- **03-05 (VirtualClock)**: Provides simulation time for sprint date calculation
- **03-06 (Capacity/Velocity)**: Calculates capacity and selects items
- **03-07 (Scheduler)**: Schedules generated actions

### Next Steps (Phase 3 Orchestration)
- Integrate SprintPlanner into main orchestrator
- Trigger planning at start of each tick
- Handle sprint activation and completion
- Connect to PM agent for planning actions

## Deviations from Plan

None - plan executed exactly as written.

## Commits

1. **acbbd1b**: feat(03-08): add planning_horizon and velocity_tracker to SimulationState
2. **862e6ac**: config(03-08): add sprint planning and scheduler configuration
3. **b14320a**: feat(03-08): create SprintPlanner orchestrator for sprint planning
4. **80d0470**: test(03-08): add sprint planning flow integration tests

## Files Changed

**Created (2 files, 664 lines)**
- `src/planning/sprint_planner.py`: 369 lines
- `tests/test_sprint_planning_flow.py`: 295 lines

**Modified (3 files)**
- `src/state/models.py`: +35 lines (planning fields and methods)
- `config/settings.yaml`: +12 lines (sprint and scheduler config)
- `src/planning/__init__.py`: +2 lines (export SprintPlanner)

## Next Phase Readiness

**Ready for Phase 3 Completion:**
- ✓ Sprint planning flow complete
- ✓ State integration complete
- ✓ Configuration in place
- ✓ Tests passing

**Remaining for Phase 3:**
- Plan 03-01: Orchestrator integration with SprintPlanner
- Plan 03-03: Scenario script loading

**Foundation for Phase 4:**
- Sprint planning provides realistic sprint lifecycle
- Planning horizon ensures continuous 2-3 sprint lookahead
- Velocity tracking enables adaptive capacity planning
- Wednesday starts align with real-world sprint cadence

## Lessons Learned

1. **Pydantic v2 Serialization**: `model_dump(mode='json')` required for datetime serialization
2. **Conditional Imports**: BacklogPrioritizer has litellm dependency, handle gracefully with try/except
3. **State Persistence**: Serializing complex objects (PlanningHorizon, VelocityTracker) as dicts enables JSON persistence
4. **Test Environments**: Anaconda Python has Pydantic v1, system Python has v2 - tests pass in v2
5. **Graceful Degradation**: Fallback prioritization ensures system works without LLM

## Performance Characteristics

**Sprint Planning Operation:**
- Backlog fetch: O(n) Jira API call
- LLM prioritization: ~5-10s (cached for 24 hours)
- Capacity calculation: O(k) where k = sprint history size
- Item selection: O(n) where n = backlog size
- Action scheduling: O(m) where m = selected items

**State Updates:**
- Planning horizon: O(1) serialization
- Velocity tracker: O(1) serialization
- needs_sprint_planning(): O(n) where n = planned sprints (typically 2-3)

**Typical Planning Time:**
- With LLM: 5-10 seconds
- Without LLM (fallback): <1 second

---

**Status:** ✅ Complete - All tasks executed, tests passing, ready for orchestrator integration
