# Simulation Time Architecture

This document outlines the architectural changes required to decouple **Simulation Time** from **Real Time**. This allows the simulation to run sprints faster than real-time (e.g., a 2-week sprint in 1 hour) or slower, controlled entirely by the `Orchestrator`.

## 1. Core Concept

Currently, the system uses `datetime.utcnow()` (or `datetime.now()`) for:
1.  Calculating sprint progress (`SprintState`).
2.  Determining ticket phase durations (`ActiveScenario`).
3.  Recording action timestamps.

We will introduce a `simulation_time` field in `SimulationState` that acts as the "virtual clock". All time-dependent logic must use this virtual clock instead of the system clock.

## 2. Data Model Changes

### 2.1 SimulationState (`src/state/models.py`, `src/state/simulation_state.py`)

Add the following fields to `SimulationState`:

```python
class SimulationState(BaseModel):
    # ... existing fields ...
    
    # Virtual Clock
    simulation_time: datetime = Field(default_factory=datetime.utcnow)
    tick_duration_hours: float = 4.0  # How much time advances per tick
    
    # ...
```

### 2.2 SprintState (`src/state/models.py`)

Update `_compute_derived_values` to accept the current `simulation_time`.

```python
    def _compute_derived_values(self, current_time: datetime) -> None:
        # ...
        # Calculate days since sprint started using virtual time
        days_elapsed = (current_time.date() - start_date.date()).days + 1
        # ...
```

### 2.3 ActiveScenario (`src/state/models.py`)

Update all time-based methods to accept `current_time`.

*   `create_normal_flow(..., current_time: datetime)`: Use `current_time` for `started` and `phase_started`.
*   `advance_to_phase(..., current_time: datetime)`: Use `current_time` for timestamps.
*   `is_phase_ready_to_advance(current_time: datetime)`: Compare against `current_time`.
*   `is_overdue(current_time: datetime)`: Compare against `current_time`.

## 3. Orchestrator Logic (`src/orchestrator/orchestrator.py`)

The `Orchestrator` is responsible for advancing time.

### 3.1 Time Advancement

In `run_tick`, before executing any logic:

1.  **Advance Time**:
    ```python
    # Advance time by tick duration
    state.simulation_time += timedelta(hours=state.tick_duration_hours)
    
    # Ensure we don't drift too far if Jira has "real" dates? 
    # Decision: The simulation drives the clock. If Jira says sprint started Monday, 
    # and simulation time is Wednesday, we differ by 2 days. 
    # We should ALIGN simulation time to Jira time when a sprint starts?
    # Better: Initialize simulation_time to datetime.utcnow() on first run, 
    # then let it drift ahead.
    ```

2.  **Pass Time to Components**:
    *   Pass `state.simulation_time` to `SprintState.inject_jira_sprint`.
    *   Pass `state.simulation_time` to `analyzer.analyze(..., current_time=state.simulation_time)`.
    *   Pass `state.simulation_time` to `planner.plan(..., current_time=state.simulation_time)`.
    *   Pass `state.simulation_time` to all crews (via `run` method or context).

## 4. Jira Integration Strategy

Jira operates in real-time. When we create sprints or issues in Jira, we have two choices:

1.  **Use Real Dates**: Jira sees "today" as today.
2.  **Use Virtual Dates**: We try to force Jira dates.

**Decision**: We will **Use Real Dates** for Jira API calls to avoid validation errors (Jira hates future dates sometimes).
*   **Reading from Jira**: When we read `start_date` from Jira, we treat it as the anchor.
    *   If `simulation_time` drifts significantly from real time, `SprintState` calculation `(simulation_time - jira_start_date)` works perfectly to simulate "being in the future".
    *   Example:
        *   Real Time: Jan 24
        *   Jira Sprint Start: Jan 24
        *   Simulation Time: Jan 30 (Advanced by 6 days of ticks)
        *   Sprint Day Calculation: Jan 30 - Jan 24 = Day 6.
    *   **This allows us to simulate a full sprint in a few minutes without mocking Jira's clock.**

## 5. Implementation Plan

### Step 1: Update Models
1.  Modify `SimulationState` to include `simulation_time`.
2.  Update `SprintState` to use `current_time` argument.
3.  Update `ActiveScenario` to use `current_time` argument.

### Step 2: Update Orchestrator
1.  In `run_tick`, advance `simulation_time`.
2.  Inject `simulation_time` into `SprintState.inject_jira_sprint`.

### Step 3: Update Crews
1.  Update `TicketLifecycleCrew` to pass `simulation_time` to `ActiveScenario` checks.
2.  Update `SprintPlanningCrew` to generally be aware of virtual time (though mostly relies on Jira).

### Step 4: Backward Compatibility
1.  In `load_state`, if `simulation_time` is missing, default to `datetime.utcnow()`.

## 6. Migration Guide

Existing `state.json` files will lack `simulation_time`. The `load_state` function handles this automatically by defaulting to `now()`.

```python
# src/state/simulation_state.py

def load_state(...):
    # ...
    if not state.simulation_time:
        state.simulation_time = datetime.utcnow()
    # ...
```
