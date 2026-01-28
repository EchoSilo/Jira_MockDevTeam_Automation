# Phase 3: Event Scheduler & Queue System - Research

**Researched:** 2026-01-28
**Domain:** Event scheduling, priority queues, sprint planning automation, calendar-based execution
**Confidence:** HIGH

## Summary

Phase 3 transforms the simulation from immediate action execution to scheduled event queues with real calendar timestamps. Actions are scheduled to specific times within 30-minute execution windows, and the system maintains a 2-3 sprint planning horizon. This phase builds on Phase 2's reconciliation infrastructure by adding temporal scheduling, priority queues for action sorting, and automated sprint planning using velocity-based capacity calculations.

The codebase currently has orchestrator-driven immediate execution (`orchestrator.py`) and scenario scripts without timestamps (`ActiveScenario.action_script`). Phase 3 adds: (1) scheduled action models with timestamps and execution windows, (2) priority queue using Python's heapq for "what's due now?" queries, (3) virtual clock advancement by tick_duration_hours, (4) weekend skipping for business hours realism, (5) PM agent sprint planning triggered when planning horizon drops below 2 sprints, and (6) velocity tracking from last 3 sprints for capacity-based backlog selection.

**Primary recommendation:** Use Python's stdlib heapq for priority queue (O(log n) operations, no dependencies), persist scheduled actions to SQLite via simple ScheduledAction table (not APScheduler's heavy job store), leverage Pendulum for business day calculations and weekend skipping, implement PlanningHorizon model tracking 2-3 future SprintPlan objects, and enhance PM agent with LLM-based backlog prioritization using historical velocity for capacity planning.

## Standard Stack

The established libraries/tools for event scheduling and queue systems:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| heapq | stdlib | Priority queue operations (min-heap) | Built-in, O(log n) push/pop, battle-tested |
| pendulum | 3.1.0+ (Phase 1) | Business day calculations, weekend skipping | Already in stack, handles DST and timezone-safe date math |
| pydantic | 2.6.1+ (Phase 1) | ScheduledAction, SprintPlan models | Already in stack, validation and serialization |
| sqlite3 | stdlib | Scheduled action persistence | Built-in, sufficient for single-instance deployment |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-networkdays | 0.1+ | Business day calculations with holidays | If holiday calendars needed (Phase 3 skips weekends only) |
| APScheduler | 3.11+ | Advanced scheduling with cron/intervals | If moving beyond tick-based execution (future phase) |
| persist-queue | 0.8+ | SQLite-backed persistent queue | If scaling beyond single-instance (Phase 4-5) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| heapq (stdlib) | queue.PriorityQueue | PriorityQueue is thread-safe but heapq is sufficient for single-threaded tick executor |
| SQLite table | APScheduler SQLAlchemyJobStore | APScheduler job store adds overhead; custom table gives full control for action model |
| Manual business day logic | pandas.bdate_range | Pandas is heavy dependency; Pendulum + weekday() is lightweight |
| Simple velocity average | AI-powered backlog prioritization | LLM can prioritize by business value, but velocity calculation is deterministic |

**Installation:**
```bash
# All core libraries already installed or stdlib
# Optional for advanced features:
pip install python-networkdays>=0.1  # Only if holiday support needed
pip install APScheduler>=3.11  # Only if moving to continuous scheduler (Phase 4-5)
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── scheduling/              # NEW: Event scheduling module
│   ├── __init__.py
│   ├── models.py            # ScheduledAction, SprintPlan, PlanningHorizon
│   ├── priority_queue.py    # Heap-based priority queue
│   ├── scheduler.py         # Schedule persistence and queries
│   ├── clock.py             # Virtual clock (simulation_time advancement)
│   └── business_hours.py    # Weekend skipping, business hours logic
├── planning/                # NEW: Sprint planning module
│   ├── __init__.py
│   ├── velocity_tracker.py  # Sprint velocity history and averages
│   ├── backlog_prioritizer.py  # PM agent backlog ranking (LLM)
│   ├── capacity_planner.py  # Capacity-based sprint selection
│   └── scenario_scheduler.py  # Convert scenario scripts to scheduled actions
├── orchestrator/
│   └── tick_executor.py     # NEW: Replaces time-advancement in orchestrator
└── state/
    └── models.py            # Add planning_horizon, action_queue to SimulationState
```

### Pattern 1: Scheduled Action Model with Execution Window
**What:** Each action has scheduled_time, execution window (default 30 minutes), preconditions, and status tracking.

**When to use:** All planned actions (transitions, comments, work logs) that need calendar timestamps.

**Example:**
```python
# src/scheduling/models.py
from dataclasses import dataclass
from typing import Optional
import pendulum
from enum import Enum

class ActionStatus(str, Enum):
    """Status of a scheduled action."""
    PENDING = "pending"          # Not yet due
    READY = "ready"              # Within execution window
    COMPLETED = "completed"      # Successfully executed
    SKIPPED = "skipped"          # Overdue or invalid
    ADAPTED = "adapted"          # Reconciliation changed plan

@dataclass(order=True)
class ScheduledAction:
    """A scheduled action with execution window and preconditions.

    Uses @dataclass(order=True) to enable heap comparisons by scheduled_time.
    """
    # Comparison key (first field determines heap order)
    scheduled_time: pendulum.DateTime

    # Action details (excluded from comparison via field())
    action_id: str = field(compare=False, default_factory=lambda: str(uuid.uuid4())[:8])
    action_type: str = field(compare=False)
    agent_id: str = field(compare=False)
    ticket_key: str = field(compare=False)
    scenario_id: Optional[str] = field(compare=False, default=None)

    # Execution window (default 30 minutes)
    window_minutes: int = field(compare=False, default=30)

    # Preconditions for reconciliation
    expected_status: Optional[str] = field(compare=False, default=None)
    expected_assignee: Optional[str] = field(compare=False, default=None)

    # Status tracking
    status: ActionStatus = field(compare=False, default=ActionStatus.PENDING)
    executed_at: Optional[pendulum.DateTime] = field(compare=False, default=None)
    result: Optional[dict] = field(compare=False, default=None)

    # Parameters for execution
    params: dict = field(compare=False, default_factory=dict)

    def is_due(self, current_time: pendulum.DateTime) -> bool:
        """Check if action is within execution window."""
        window_end = self.scheduled_time + pendulum.duration(minutes=self.window_minutes)
        return self.scheduled_time <= current_time <= window_end

    def is_overdue(self, current_time: pendulum.DateTime) -> bool:
        """Check if action is past execution window."""
        window_end = self.scheduled_time + pendulum.duration(minutes=self.window_minutes)
        return current_time > window_end

    def mark_completed(self, result: dict) -> None:
        """Mark action as completed."""
        self.status = ActionStatus.COMPLETED
        self.executed_at = pendulum.now("UTC")
        self.result = result

    def mark_skipped(self, reason: str) -> None:
        """Mark action as skipped (overdue or invalid)."""
        self.status = ActionStatus.SKIPPED
        self.result = {"reason": reason}
```

### Pattern 2: Priority Queue with Heap Operations
**What:** Maintain scheduled actions in min-heap sorted by scheduled_time for O(log n) insertion and O(1) peek.

**When to use:** Action queue that needs frequent "what's due now?" queries and dynamic insertion.

**Example:**
```python
# src/scheduling/priority_queue.py
import heapq
from typing import List, Optional
import pendulum

class ActionPriorityQueue:
    """Priority queue for scheduled actions using heapq.

    Actions are ordered by scheduled_time (earliest first).
    """

    def __init__(self):
        self._heap: List[ScheduledAction] = []

    def push(self, action: ScheduledAction) -> None:
        """Add action to queue (O(log n))."""
        heapq.heappush(self._heap, action)

    def peek(self) -> Optional[ScheduledAction]:
        """View next action without removing (O(1))."""
        return self._heap[0] if self._heap else None

    def pop(self) -> Optional[ScheduledAction]:
        """Remove and return next action (O(log n))."""
        return heapq.heappop(self._heap) if self._heap else None

    def get_due_actions(
        self,
        current_time: pendulum.DateTime,
        max_actions: int = 10
    ) -> List[ScheduledAction]:
        """Get all actions due at current_time (within execution window).

        Returns up to max_actions due actions, leaving them in queue.
        """
        due_actions = []
        for action in self._heap:
            # Heap is sorted by scheduled_time, so we can break early
            if action.scheduled_time > current_time:
                break
            if action.is_due(current_time) and action.status == ActionStatus.PENDING:
                due_actions.append(action)
                if len(due_actions) >= max_actions:
                    break
        return due_actions

    def remove_action(self, action_id: str) -> Optional[ScheduledAction]:
        """Remove action by ID (O(n) search, O(n) rebuild).

        Use sparingly - heapq doesn't support efficient arbitrary removal.
        """
        for i, action in enumerate(self._heap):
            if action.action_id == action_id:
                removed = self._heap.pop(i)
                heapq.heapify(self._heap)  # Rebuild heap after removal
                return removed
        return None

    def size(self) -> int:
        """Get queue size."""
        return len(self._heap)

    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return len(self._heap) == 0
```

### Pattern 3: Virtual Clock with Tick-Based Advancement
**What:** Simulation time advances by tick_duration_hours each tick, not wall-clock time.

**When to use:** All time calculations in scheduling (convert scenario days to absolute timestamps).

**Example:**
```python
# src/scheduling/clock.py
import pendulum
from typing import Protocol

class SimulationClock(Protocol):
    """Protocol for simulation time (real or virtual)."""

    def now(self) -> pendulum.DateTime:
        """Get current simulation time."""
        ...

    def advance(self, hours: float) -> pendulum.DateTime:
        """Advance simulation time by hours (virtual clock only)."""
        ...

class VirtualClock:
    """Virtual clock that advances by tick_duration_hours each tick.

    Used for scheduling: simulation_time determines when actions are due.
    """

    def __init__(self, start_time: pendulum.DateTime, tick_duration_hours: float = 0.75):
        self._simulation_time = start_time
        self.tick_duration_hours = tick_duration_hours

    def now(self) -> pendulum.DateTime:
        """Get current simulation time."""
        return self._simulation_time

    def advance(self, hours: Optional[float] = None) -> pendulum.DateTime:
        """Advance simulation time by hours (default: tick_duration_hours).

        Returns new simulation time.
        """
        hours = hours or self.tick_duration_hours
        self._simulation_time = self._simulation_time.add(hours=hours)
        return self._simulation_time

    def set_time(self, time: pendulum.DateTime) -> None:
        """Set simulation time directly (for initialization/reset)."""
        self._simulation_time = time

# Usage in orchestrator
class TickExecutor:
    def __init__(self, virtual_clock: VirtualClock, scheduler: Scheduler):
        self.clock = virtual_clock
        self.scheduler = scheduler

    def execute_tick(self) -> dict:
        """Execute one simulation tick."""
        # 1. Get current simulation time
        current_time = self.clock.now()

        # 2. Query scheduler for due actions
        due_actions = self.scheduler.get_due_actions(current_time)

        # 3. Execute actions (with reconciliation from Phase 2)
        results = []
        for action in due_actions:
            result = self._execute_action(action)
            results.append(result)

        # 4. Advance simulation time
        next_time = self.clock.advance()

        return {
            "current_time": current_time.isoformat(),
            "next_time": next_time.isoformat(),
            "actions_executed": len(results),
            "results": results
        }
```

### Pattern 4: Weekend Skipping for Business Hours
**What:** When scheduling actions, skip Saturday/Sunday and respect business hours (9am-5pm).

**When to use:** Converting scenario script days (1-7) to absolute timestamps.

**Example:**
```python
# src/scheduling/business_hours.py
import pendulum

class BusinessHoursScheduler:
    """Schedule actions during business hours, skipping weekends."""

    def __init__(
        self,
        work_start_hour: int = 9,
        work_end_hour: int = 17,
        timezone: str = "America/New_York"
    ):
        self.work_start_hour = work_start_hour
        self.work_end_hour = work_end_hour
        self.timezone = timezone

    def is_business_day(self, dt: pendulum.DateTime) -> bool:
        """Check if date is a business day (Monday-Friday)."""
        # Pendulum: 1=Monday, 7=Sunday (ISO 8601)
        return dt.day_of_week <= 5

    def is_business_hours(self, dt: pendulum.DateTime) -> bool:
        """Check if time is within business hours."""
        return (
            self.is_business_day(dt) and
            self.work_start_hour <= dt.hour < self.work_end_hour
        )

    def next_business_day(self, dt: pendulum.DateTime) -> pendulum.DateTime:
        """Get next business day at work_start_hour.

        If dt is Friday 5pm, returns Monday 9am.
        """
        # Move to next day at work start hour
        next_day = dt.add(days=1).at(self.work_start_hour, 0, 0)

        # Skip weekends
        while not self.is_business_day(next_day):
            next_day = next_day.add(days=1)

        return next_day

    def schedule_action(
        self,
        base_time: pendulum.DateTime,
        hours_from_now: float
    ) -> pendulum.DateTime:
        """Schedule action hours_from_now in the future, skipping weekends.

        Example: If base_time is Friday 4pm and hours_from_now=2,
        returns Monday 9am (skips weekend).
        """
        target_time = base_time.add(hours=hours_from_now)

        # If target falls on weekend, move to Monday morning
        if not self.is_business_day(target_time):
            target_time = self.next_business_day(target_time)

        # If outside business hours, move to next business period
        if target_time.hour < self.work_start_hour:
            target_time = target_time.at(self.work_start_hour, 0, 0)
        elif target_time.hour >= self.work_end_hour:
            target_time = self.next_business_day(target_time)

        return target_time

# Usage example
scheduler = BusinessHoursScheduler()
friday_4pm = pendulum.parse("2026-01-30T16:00:00", tz="America/New_York")  # Friday 4pm
monday_9am = scheduler.schedule_action(friday_4pm, hours_from_now=2)
print(monday_9am)  # 2026-02-02 09:00:00-05:00 (Monday 9am)
```

### Pattern 5: Sprint Planning Horizon with Velocity Tracking
**What:** Maintain 2-3 future sprint plans, trigger PM agent planning when horizon drops below 2.

**When to use:** Sprint planning automation, capacity-based backlog selection.

**Example:**
```python
# src/scheduling/models.py (continued)
from pydantic import BaseModel, Field
from typing import List, Optional

class SprintPlan(BaseModel):
    """A planned sprint with committed items and scenario."""
    sprint_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    sprint_number: int
    start_date: pendulum.DateTime
    end_date: pendulum.DateTime

    # Committed items from backlog
    committed_items: List[str] = Field(default_factory=list)  # ticket_keys
    committed_points: int = 0

    # Scenario script for this sprint
    scenario_id: Optional[str] = None

    # Planning metadata
    status: str = "planned"  # planned | active | completed
    planned_at: pendulum.DateTime = Field(default_factory=lambda: pendulum.now("UTC"))
    velocity_estimate: Optional[int] = None  # Team velocity when planned

class PlanningHorizon(BaseModel):
    """Maintains 2-3 future sprint plans."""
    future_sprints: List[SprintPlan] = Field(default_factory=list)

    def get_sprint_count(self) -> int:
        """Get number of planned future sprints."""
        return len([s for s in self.future_sprints if s.status == "planned"])

    def needs_planning(self, min_sprints: int = 2) -> bool:
        """Check if we need to plan more sprints."""
        return self.get_sprint_count() < min_sprints

    def get_next_sprint_number(self, current_sprint: int) -> int:
        """Calculate next sprint number to plan."""
        if not self.future_sprints:
            return current_sprint + 1
        max_planned = max(s.sprint_number for s in self.future_sprints)
        return max_planned + 1

    def add_sprint_plan(self, plan: SprintPlan) -> None:
        """Add a new sprint plan to horizon."""
        self.future_sprints.append(plan)

    def activate_sprint(self, sprint_number: int) -> Optional[SprintPlan]:
        """Mark sprint as active and return it."""
        for sprint in self.future_sprints:
            if sprint.sprint_number == sprint_number:
                sprint.status = "active"
                return sprint
        return None

    def cleanup_old_sprints(self) -> int:
        """Remove completed sprints older than 30 days."""
        cutoff = pendulum.now("UTC").subtract(days=30)
        original_count = len(self.future_sprints)
        self.future_sprints = [
            s for s in self.future_sprints
            if s.status != "completed" or s.end_date > cutoff
        ]
        return original_count - len(self.future_sprints)

# src/planning/velocity_tracker.py
class VelocityTracker(BaseModel):
    """Track sprint velocity for capacity planning."""
    sprint_history: List[dict] = Field(default_factory=list)
    # Each dict: {"sprint_number": int, "committed": int, "completed": int}

    def record_sprint(self, sprint_number: int, committed: int, completed: int) -> None:
        """Record sprint results."""
        self.sprint_history.append({
            "sprint_number": sprint_number,
            "committed": committed,
            "completed": completed,
            "completion_rate": completed / committed if committed > 0 else 0.0
        })

    def get_average_velocity(self, last_n_sprints: int = 3) -> int:
        """Calculate average velocity from last N sprints."""
        if not self.sprint_history:
            return 0

        recent = self.sprint_history[-last_n_sprints:]
        total_completed = sum(s["completed"] for s in recent)
        return total_completed // len(recent) if recent else 0

    def get_capacity_recommendation(self, last_n_sprints: int = 3) -> int:
        """Get recommended capacity for next sprint (75-85% of avg velocity).

        Conservative estimate accounts for unknowns and technical debt.
        """
        avg_velocity = self.get_average_velocity(last_n_sprints)
        return int(avg_velocity * 0.8)  # 80% of historical average
```

### Pattern 6: Scenario Script to Scheduled Actions Conversion
**What:** Convert scenario script days (1-7) to absolute calendar timestamps using sprint start date.

**When to use:** When PM agent creates sprint plan and needs to schedule all actions.

**Example:**
```python
# src/planning/scenario_scheduler.py
class ScenarioScheduler:
    """Convert scenario scripts to scheduled actions with calendar timestamps."""

    def __init__(self, business_hours: BusinessHoursScheduler):
        self.business_hours = business_hours

    def convert_scenario_to_actions(
        self,
        scenario_script: List[dict],
        sprint_start_date: pendulum.DateTime,
        ticket_key: str,
        scenario_id: str
    ) -> List[ScheduledAction]:
        """Convert scenario script (day 1-7) to scheduled actions.

        Args:
            scenario_script: List of actions with "day" field (1-7)
            sprint_start_date: Sprint start date (Wednesday)
            ticket_key: Jira ticket key
            scenario_id: Scenario ID for grouping

        Returns:
            List of ScheduledAction with absolute timestamps
        """
        scheduled_actions = []

        for script_action in scenario_script:
            day_offset = script_action["day"] - 1  # Convert 1-indexed to 0-indexed
            action_type = script_action["type"]
            agent_id = script_action.get("agent_id")

            # Calculate base time (sprint_start + days)
            base_time = sprint_start_date.add(days=day_offset)

            # Distribute actions throughout business hours (9am-5pm)
            # Add random hours to spread actions naturally
            random_hour_offset = random.uniform(0, 8)  # 8-hour workday
            scheduled_time = self.business_hours.schedule_action(
                base_time.at(9, 0, 0),  # Start at 9am
                hours_from_now=random_hour_offset
            )

            # Create scheduled action
            action = ScheduledAction(
                scheduled_time=scheduled_time,
                action_type=action_type,
                agent_id=agent_id,
                ticket_key=ticket_key,
                scenario_id=scenario_id,
                expected_status=script_action.get("expected_status"),
                params=script_action.get("params", {})
            )

            scheduled_actions.append(action)

        return scheduled_actions
```

### Anti-Patterns to Avoid
- **Storing actions only in memory:** Persist to SQLite so simulator restart doesn't lose schedule.
- **Scheduling actions on exact times (10:00:00):** Add randomness (10:13:27) for realistic activity patterns.
- **Ignoring execution window:** Actions should have 30-minute window, not exact timestamp match.
- **Calendar day math without business hours:** Use business_hours_scheduler to skip weekends.
- **Rebuilding heap frequently:** heapq doesn't support efficient arbitrary removal; use sparingly.
- **Planning sprints without velocity data:** Use last 3 sprints average, not arbitrary capacity guesses.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Priority queue | Custom sorted list | heapq stdlib | Heapq has O(log n) operations; manual sorting is O(n log n) |
| Business day calculations | Loop checking weekday() | pendulum + is_business_day() | DST transitions, timezone handling, holiday support (future) |
| Heap-based job persistence | Custom binary file format | SQLite table with priority index | SQLite handles concurrency, corruption recovery, indexing |
| Sprint velocity calculation | Manual average | VelocityTracker with last_n_sprints | Handles edge cases (empty history, single sprint, completion rate) |
| Action deduplication | Check list membership | Set of action_ids | O(1) lookup vs O(n) list search |
| Execution window check | Manual timestamp comparison | action.is_due(current_time) | Encapsulates window logic, handles edge cases (timezone, DST) |

**Key insight:** Event scheduling is deceptively complex because real calendars have edge cases:
- Weekends and holidays
- DST transitions (2am becomes 3am, or 2am happens twice)
- Timezone arithmetic (adding 24 hours != adding 1 day in DST zones)
- Execution windows (30-minute range, not exact timestamp)
- Overdue actions (past window_end, should skip not retry forever)
- Heap maintenance (arbitrary removal requires O(n) rebuild)

## Common Pitfalls

### Pitfall 1: Scheduling Actions on Exact Timestamps Without Randomness
**What goes wrong:** All actions scheduled for "Monday 9am" execute at exactly 09:00:00, creating unrealistic burst patterns in Jira activity logs.

**Why it happens:** Scenario scripts specify "day 1" and conversion naively maps to sprint_start + 0 days at 9am.

**How to avoid:**
```python
# BAD (all actions at exactly 9am)
scheduled_time = sprint_start_date.add(days=day_offset).at(9, 0, 0)

# GOOD (distributed throughout business hours)
base_time = sprint_start_date.add(days=day_offset).at(9, 0, 0)
random_offset_hours = random.uniform(0, 8)  # 9am-5pm
scheduled_time = business_hours.schedule_action(base_time, random_offset_hours)
```

**Warning signs:**
- Jira activity logs show all actions at :00:00 timestamps
- Analytics tools report "bursts" of activity at round hours
- Lack of realistic spread in action timing

### Pitfall 2: Execution Window Too Narrow (Actions Frequently Marked Overdue)
**What goes wrong:** Actions have 5-minute execution window, but tick cadence is 45 minutes. Actions frequently marked as overdue/skipped even though system is functioning correctly.

**Why it happens:** Execution window shorter than tick interval means many actions "expire" before they're checked.

**How to avoid:**
```python
# BAD (5-minute window with 45-minute ticks)
action.window_minutes = 5

# GOOD (30-minute window gives buffer)
action.window_minutes = 30  # Covers tick interval + margin

# Even better: dynamic window based on tick cadence
tick_duration = 45  # minutes
action.window_minutes = tick_duration + 15  # Tick + 15min margin
```

**Warning signs:**
- High skip rate in execution metrics
- Logs show "action overdue" for recently scheduled items
- Actions skipped despite no Jira state divergence

### Pitfall 3: Weekend Actions Not Skipped (Unrealistic Saturday/Sunday Activity)
**What goes wrong:** Sprint scenario schedules actions for "day 6" (Saturday) and they execute, creating unrealistic weekend activity in Jira.

**Why it happens:** Scenario script days (1-7) include weekend days, and scheduler doesn't skip them.

**How to avoid:**
```python
# BAD (schedules on actual day 6, which might be Saturday)
scheduled_time = sprint_start_date.add(days=day_offset)

# GOOD (skip weekends when scheduling)
base_time = sprint_start_date.add(days=day_offset)
if not business_hours.is_business_day(base_time):
    base_time = business_hours.next_business_day(base_time)
scheduled_time = base_time.at(9, 0, 0)
```

**Warning signs:**
- Jira shows activity on Saturdays/Sundays
- Analytics report weekend work patterns
- Logs show scheduled_time with day_of_week=6 or 7

### Pitfall 4: Planning Horizon Only Checks Count, Not Date Range
**What goes wrong:** System has 2 future sprints planned but both end in 3 days. Horizon check passes (count=2) but system runs out of work soon.

**Why it happens:** `needs_planning()` only counts sprints, doesn't check if they're far enough in future.

**How to avoid:**
```python
# BAD (only checks count)
def needs_planning(self) -> bool:
    return len(self.future_sprints) < 2

# GOOD (checks count AND date range)
def needs_planning(self, min_sprints: int = 2, min_days_ahead: int = 14) -> bool:
    planned = [s for s in self.future_sprints if s.status == "planned"]
    if len(planned) < min_sprints:
        return True

    # Check if farthest sprint is far enough in future
    if planned:
        farthest_end = max(s.end_date for s in planned)
        days_until_end = (farthest_end - pendulum.now("UTC")).days
        return days_until_end < min_days_ahead

    return True
```

**Warning signs:**
- Sudden work starvation after recent sprint planning
- Future sprints all clustered close to current date
- PM agent not triggered despite low horizon

### Pitfall 5: Velocity Calculation Includes Incomplete Sprints
**What goes wrong:** Current sprint (in progress) is included in velocity calculation, distorting capacity estimate because sprint isn't complete yet.

**Why it happens:** `sprint_history` includes all sprints, not just completed ones.

**How to avoid:**
```python
# BAD (includes in-progress sprint)
def get_average_velocity(self, last_n_sprints: int = 3) -> int:
    recent = self.sprint_history[-last_n_sprints:]
    return sum(s["completed"] for s in recent) // len(recent)

# GOOD (only completed sprints)
def get_average_velocity(self, last_n_sprints: int = 3) -> int:
    completed_sprints = [
        s for s in self.sprint_history
        if s.get("status") == "completed"
    ]
    recent = completed_sprints[-last_n_sprints:]
    if not recent:
        return 0  # Default for new teams
    return sum(s["completed"] for s in recent) // len(recent)
```

**Warning signs:**
- Velocity spikes/drops mid-sprint
- Capacity recommendations change during sprint
- Tests fail because current sprint data affects results

### Pitfall 6: Heap Arbitrary Removal Performance (Frequent Cancellations Cause Slowdown)
**What goes wrong:** Reconciliation frequently cancels actions (removes from heap), and each removal triggers O(n) heapify. With 1000+ actions, tick execution slows significantly.

**Why it happens:** heapq doesn't support efficient arbitrary removal; `remove_action()` pops item and rebuilds heap.

**How to avoid:**
```python
# BAD (remove from heap frequently)
def cancel_action(self, action_id: str):
    self.queue.remove_action(action_id)  # O(n) search + O(n) rebuild

# GOOD (mark as skipped, let pop() filter them out)
def cancel_action(self, action_id: str):
    for action in self.queue._heap:
        if action.action_id == action_id:
            action.status = ActionStatus.SKIPPED
            break

# In get_due_actions, skip canceled actions
def get_due_actions(self, current_time):
    due_actions = []
    for action in self._heap:
        if action.status == ActionStatus.PENDING and action.is_due(current_time):
            due_actions.append(action)
    return due_actions
```

**Warning signs:**
- Tick execution time increases with queue size
- Profiling shows heapify() taking significant time
- Cancellation-heavy scenarios (many divergences) slow down system

## Code Examples

Verified patterns from research:

### Heapq Priority Queue (2026 Best Practice)
```python
# Source: https://medium.com/@prathik.codes/pythons-heapq-a-guide-to-efficient-priority-queues-140b890c48a6
# Source: https://docs.python.org/3/library/heapq.html
import heapq
from dataclasses import dataclass, field
from typing import Any

@dataclass(order=True)
class PrioritizedAction:
    """Wrapper for non-comparable objects in heapq.

    The priority field is compared first (determines heap order).
    The item field is excluded from comparison.
    """
    priority: int
    item: Any = field(compare=False)

# Example: priority queue with custom objects
queue = []
heapq.heappush(queue, PrioritizedAction(priority=1, item={"action": "transition"}))
heapq.heappush(queue, PrioritizedAction(priority=3, item={"action": "comment"}))
heapq.heappush(queue, PrioritizedAction(priority=2, item={"action": "log_work"}))

# Pop returns lowest priority first
next_item = heapq.heappop(queue)  # priority=1
```

### Pendulum Business Day Calculations (2026)
```python
# Source: https://pendulum.eustace.io/docs/
# Source: https://pynative.com/python-get-business-days/
import pendulum

def is_business_day(dt: pendulum.DateTime) -> bool:
    """Check if date is Monday-Friday."""
    # Pendulum uses ISO 8601: 1=Monday, 7=Sunday
    return dt.day_of_week <= 5

def next_business_day(dt: pendulum.DateTime) -> pendulum.DateTime:
    """Get next business day (skip weekends)."""
    next_day = dt.add(days=1)
    while not is_business_day(next_day):
        next_day = next_day.add(days=1)
    return next_day

# Example: Friday -> Monday
friday = pendulum.parse("2026-01-30", tz="America/New_York")  # Friday
monday = next_business_day(friday)
print(monday.format("dddd, MMMM D"))  # Monday, February 2
```

### Velocity-Based Capacity Planning (2026 Automation)
```python
# Source: https://monday.com/blog/rnd/agile-velocity/
# Source: https://www.scrum.org/forum/scrum-forum/85515/sprint-historical-velocity-planning-and-capacity-calculation
class CapacityPlanner:
    """Calculate sprint capacity from historical velocity."""

    def __init__(self, velocity_tracker: VelocityTracker):
        self.velocity = velocity_tracker

    def calculate_capacity(
        self,
        last_n_sprints: int = 3,
        buffer_percentage: float = 0.8
    ) -> int:
        """Calculate sprint capacity as 75-85% of average velocity.

        Conservative buffer accounts for:
        - Technical debt (15-25% of capacity recommended)
        - Unknowns and estimation errors
        - Team availability variations
        """
        avg_velocity = self.velocity.get_average_velocity(last_n_sprints)
        return int(avg_velocity * buffer_percentage)

    def select_backlog_items(
        self,
        backlog: List[dict],  # [{"key": "PROJ-123", "points": 5}, ...]
        capacity: int
    ) -> List[str]:
        """Select backlog items that fit within capacity.

        Returns list of ticket keys that sum to <= capacity points.
        """
        selected = []
        total_points = 0

        # Assume backlog is already prioritized by PM agent (LLM)
        for item in backlog:
            item_points = item.get("points", 0)
            if total_points + item_points <= capacity:
                selected.append(item["key"])
                total_points += item_points

        return selected
```

### SQLite Action Queue Persistence
```python
# Source: https://github.com/litements/litequeue
# Source: https://docs.python.org/3/library/sqlite3.html
import sqlite3
import json
import pendulum

class ScheduledActionStore:
    """Persist scheduled actions to SQLite."""

    def __init__(self, db_path: str = "data/scheduler.db"):
        self.db_path = db_path
        self._create_table()

    def _create_table(self):
        """Create scheduled_actions table if not exists."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_actions (
                action_id TEXT PRIMARY KEY,
                scheduled_time TEXT NOT NULL,
                action_type TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                ticket_key TEXT NOT NULL,
                scenario_id TEXT,
                status TEXT DEFAULT 'pending',
                params TEXT,  -- JSON
                created_at TEXT NOT NULL,
                executed_at TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_scheduled_time
            ON scheduled_actions(scheduled_time)
        """)
        conn.commit()
        conn.close()

    def save_action(self, action: ScheduledAction):
        """Persist action to database."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO scheduled_actions
            (action_id, scheduled_time, action_type, agent_id, ticket_key,
             scenario_id, status, params, created_at, executed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            action.action_id,
            action.scheduled_time.isoformat(),
            action.action_type,
            action.agent_id,
            action.ticket_key,
            action.scenario_id,
            action.status.value,
            json.dumps(action.params),
            pendulum.now("UTC").isoformat(),
            action.executed_at.isoformat() if action.executed_at else None
        ))
        conn.commit()
        conn.close()

    def load_pending_actions(self) -> List[ScheduledAction]:
        """Load all pending actions from database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            SELECT * FROM scheduled_actions
            WHERE status = 'pending'
            ORDER BY scheduled_time ASC
        """)

        actions = []
        for row in cursor.fetchall():
            action = ScheduledAction(
                action_id=row[0],
                scheduled_time=pendulum.parse(row[1]),
                action_type=row[2],
                agent_id=row[3],
                ticket_key=row[4],
                scenario_id=row[5],
                status=ActionStatus(row[6]),
                params=json.loads(row[7]) if row[7] else {},
            )
            actions.append(action)

        conn.close()
        return actions
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Immediate execution | Scheduled actions with timestamps | 2020+ event-driven architectures | Enables realistic activity patterns and time-based analytics |
| Manual sprint planning | AI-powered backlog prioritization + velocity-based capacity | 2025-2026 agile automation | Reduces PM overhead, improves predictability |
| Fixed sprint schedules | Dynamic planning horizon (2-3 sprints) | 2022+ lean planning | Reduces upfront planning waste, adapts to velocity changes |
| APScheduler for all scheduling | heapq + SQLite for action queues | 2024+ lightweight alternatives | Lower overhead, full control over queue behavior |
| Calendar day math | Business day libraries (Pendulum, python-networkdays) | 2015+ datetime improvements | Handles DST, timezones, holidays correctly |
| Manual overdue handling | Execution window with auto-skip | 2020+ resilient systems | Prevents infinite retries, graceful degradation |

**Deprecated/outdated:**
- **APScheduler for simple tick-based systems:** APScheduler is powerful but heavyweight; heapq + SQLite is simpler for tick-driven execution.
- **Storing only next sprint:** Modern agile recommends 2-3 sprint lookahead to smooth planning and reduce last-minute scrambles.
- **Equal velocity for all teams:** 2026 best practices differentiate team velocity, seniority-adjusted capacity, and technical debt allocation.
- **Hardcoded sprint duration:** Modern tools support flexible sprint lengths (1-4 weeks), configured not coded.

## Open Questions

Things that couldn't be fully resolved:

1. **Should scheduled actions persist across simulator restarts?**
   - What we know: SQLite persistence enables restart recovery, but adds file I/O overhead
   - What's unclear: Whether Docker restarts are common enough to warrant persistence cost
   - Recommendation: Persist to SQLite (adds <10ms per action), simplifies recovery, enables debugging

2. **What's the optimal tick_duration_hours (0.75h vs 1h vs variable)?**
   - What we know: 45 minutes (0.75h) matches current n8n cron schedule
   - What's unclear: Whether fixed cadence or variable intervals create more realistic patterns
   - Recommendation: Start with 0.75h (matches current), monitor action distribution, adjust if clustering observed

3. **Should PM agent use LLM for every backlog prioritization or cache results?**
   - What we know: LLM prioritization is expensive (Sonnet tokens), provides business value insights
   - What's unclear: Whether re-prioritizing every tick adds value or just cost
   - Recommendation: Cache prioritization for 24 hours or until backlog changes significantly (>20% new items)

4. **How to handle sprint transitions mid-tick (active sprint ends during execution)?**
   - What we know: Sprint end date might occur during tick execution window
   - What's unclear: Whether to complete in-progress actions or force sprint boundary
   - Recommendation: Complete in-progress actions, transition to new sprint at next tick (aligns with Jira behavior)

5. **Should execution window be configurable per action type (transition vs comment)?**
   - What we know: Transitions are time-sensitive, comments less so
   - What's unclear: Whether complexity of per-type windows justifies marginal realism gain
   - Recommendation: Single 30-minute window initially, add per-type if analytics show clustering issues

6. **How to handle holidays in business day calculations?**
   - What we know: python-networkdays supports holiday calendars, Pendulum doesn't
   - What's unclear: Whether US holidays (Thanksgiving, Christmas) are important for realism
   - Recommendation: Skip holidays in Phase 3 (weekends only), add holiday support in Phase 4 if requested

## Sources

### Primary (HIGH confidence)
- [Python's heapq: A Guide to Efficient Priority Queues (2026)](https://medium.com/@prathik.codes/pythons-heapq-a-guide-to-efficient-priority-queues-140b890c48a6) - Heap operations and best practices
- [heapq — Heap queue algorithm (Python stdlib)](https://docs.python.org/3/library/heapq.html) - Official documentation
- [APScheduler User Guide](https://apscheduler.readthedocs.io/en/3.x/userguide.html) - Job persistence and scheduling
- [Pendulum Documentation](https://pendulum.eustace.io/docs/) - Business day calculations and timezone handling
- [Python Job Scheduling: Methods and Overview in 2026](https://research.aimultiple.com/python-job-scheduling/) - Current state of scheduling libraries
- [What is agile velocity? Definition, formula and best practices for 2025](https://monday.com/blog/rnd/agile-velocity/) - Velocity calculation and capacity planning

### Secondary (MEDIUM confidence)
- [litequeue - Queue built on SQLite](https://github.com/litements/litequeue) - SQLite-backed persistent queue
- [persist-queue - Thread-safe disk persistent queue](https://github.com/peter-wangxu/persist-queue) - Alternative persistence approach
- [Sprint Planning: The Complete Guide for 2025 (AI)](https://monday.com/blog/rnd/sprint-planning/) - AI-powered sprint planning trends
- [Building a strategic product backlog in 2026](https://monday.com/blog/rnd/product-backlog/) - Backlog prioritization automation
- [python-networkdays PyPI](https://pypi.org/project/python-networkdays/) - Business day calculations with holidays
- [How to Use a Priority Queue in Python](https://www.digitalocean.com/community/tutorials/priority-queue-python) - Queue.PriorityQueue vs heapq comparison

### Tertiary (LOW confidence)
- [APScheduler SQLAlchemyJobStore](https://apscheduler.readthedocs.io/en/3.x/modules/jobstores/sqlalchemy.html) - Job store persistence
- [Capacity-Driven Sprint Planning](https://www.mountaingoatsoftware.com/blog/capacity-driven-sprint-planning) - Sprint capacity best practices
- [Automated Sprint Planning and Predicted Sprints (Zenhub)](https://www.zenhub.com/blog-posts/introducing-predictive-sprints-and-automated-sprints) - Automation examples

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - heapq and Pendulum are stdlib/Phase 1, SQLite is proven for persistence
- Architecture: HIGH - Priority queues and business day calculations are well-established patterns
- Sprint planning: MEDIUM - Velocity tracking is standard agile, but LLM-based prioritization is emerging (2025-2026)
- Execution windows: MEDIUM - Pattern is sound, but 30-minute default is estimate (not industry standard)

**Research date:** 2026-01-28
**Valid until:** 60 days (scheduling patterns stable, but sprint planning automation evolving rapidly in 2026)

**Key architectural decisions:**
- Use heapq (not APScheduler) for lightweight tick-based scheduling
- Persist to SQLite (not APScheduler job store) for full control and simplicity
- Separate VirtualClock from RealClock (dependency injection for testing)
- Business hours scheduler encapsulates weekend skipping logic
- Planning horizon triggers PM agent when < 2 future sprints
- Velocity tracker uses last 3 sprints for capacity calculation
- 30-minute execution window balances flexibility with precision

**Phase 2 integration points:**
- PreExecutionValidator checks preconditions (expected_status) before executing scheduled actions
- ReconciliationEngine provides adaptation strategies (SKIP/CANCEL/RESCHEDULE) for overdue actions
- ExecutionTracker prevents duplicate execution via action_id
- ResilientJiraClient protects against cascade failures during action execution
- Staleness detection could apply to PlanningHorizon (remove stale sprint plans)

**Next steps for planner:**
1. Create `src/scheduling/` module with ScheduledAction, PlanningHorizon, ActionPriorityQueue models
2. Implement VirtualClock and BusinessHoursScheduler
3. Add `planning_horizon` and `action_queue` fields to SimulationState
4. Create TickExecutor to replace orchestrator's immediate execution
5. Build ScenarioScheduler to convert scripts (day 1-7) to calendar timestamps
6. Implement VelocityTracker and CapacityPlanner for PM agent
7. Add sprint planning flow: fetch backlog -> prioritize (LLM) -> select (capacity) -> generate scenario -> schedule actions
8. Write tests for weekend skipping, execution window, overdue handling, velocity calculation
