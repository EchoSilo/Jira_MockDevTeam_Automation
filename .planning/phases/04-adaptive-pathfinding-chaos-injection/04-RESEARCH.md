# Phase 4: Adaptive Pathfinding & Chaos Injection - Research

**Researched:** 2026-01-28
**Domain:** Chaos engineering, adaptive planning, workflow pathfinding, event-driven disruption injection
**Confidence:** HIGH

## Summary

Phase 4 injects realistic random disruptions (outages, bugs, absences, blockers) into scheduled scenarios and adapts workflow paths when Jira state diverges from expectations. The system must: (1) roll dice each tick against configurable event probabilities, (2) inject new actions into the schedule when chaos events trigger, (3) modify or skip existing scheduled actions when external changes occur, (4) recalculate workflow transitions using BFS pathfinding when ticket status diverges, and (5) track scenario confidence (script_fidelity) to detect when reality has diverged too far from the plan.

The codebase already has: ReconciliationEngine with SKIP/CANCEL/RECALCULATE strategies (Phase 2), WorkflowPathfinder with BFS-based status transition computation, ScheduledAction model with ADAPTED status, and SprintScenario with event tracking. Phase 4 extends this with: RandomEventGenerator rolling probabilities, ScenarioAdapter modifying active scenarios by inserting/rescheduling actions, workflow adaptation using pathfinder.recalculate_remaining_script(), and confidence scoring based on executed vs adapted event ratios.

**Primary recommendation:** Use Python's random.choices() with weights for event type selection, create per-event-type probability config in settings.yaml (not preset chaos levels), leverage existing WorkflowPathfinder.recalculate_remaining_script() for adaptive pathfinding, implement ScenarioAdapter that INSERTS new ScheduledActions and marks existing ones as ADAPTED, track script_fidelity as (executed_events / total_events) and trigger "accept reality" mode when below 0.7 threshold. No external libraries needed - stdlib random + existing Phase 3 scheduler infrastructure is sufficient.

## Standard Stack

The established libraries/tools for chaos injection and adaptive planning:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| random | stdlib | Weighted event selection with random.choices() | Built-in, sufficient for probability distributions |
| heapq | stdlib (Phase 3) | Insert chaos actions into priority queue | Already in stack, O(log n) insertion |
| pendulum | 3.1.0+ (Phase 1) | Calculate chaos event timestamps | Already in stack, business hours integration |
| pydantic | 2.6.1+ (Phase 1) | RandomEvent, ChaosConfig models | Already in stack, validation |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| numpy.random | 1.26+ | Vectorized probability sampling | If batching hundreds of events per tick (unlikely) |
| networkx | 3.6+ | Advanced graph algorithms (Dijkstra, A*) | If workflow has weighted transitions or cycles (Phase 4 uses simple BFS) |
| python-statemachine | 2.5+ | State machine with callbacks | If adding complex state machine logic (overkill for Phase 4) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| random.choices (stdlib) | numpy.random.choice | NumPy faster for large batches but adds dependency; random.choices sufficient for 1-6 event rolls per tick |
| BFS pathfinding | Dijkstra or A* | Dijkstra/A* handle weighted graphs but Jira workflows are unweighted; BFS is O(V+E) and simpler |
| Manual probability rolling | Chaos Mesh / Chaos Toolkit | These are production chaos platforms; simulation needs simple dice rolling not distributed fault injection |
| Script confidence tracking | Machine learning prediction | ML overkill; simple ratio (executed/total) is interpretable and sufficient |

**Installation:**
```bash
# All core libraries already installed or stdlib
# Optional for advanced features:
pip install networkx>=3.6  # Only if switching to Dijkstra/A* (not recommended for Phase 4)
pip install numpy>=1.26    # Only if batching large event selections (not needed)
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── chaos/                   # NEW: Chaos injection module
│   ├── __init__.py
│   ├── event_generator.py   # RandomEventGenerator with probability rolling
│   ├── event_catalog.py     # Event templates by archetype
│   ├── scenario_adapter.py  # ScenarioAdapter modifying active scenarios
│   └── models.py            # RandomEvent, ChaosConfig
├── scheduling/              # EXISTING (Phase 3)
│   ├── scheduler.py         # schedule_action() for chaos event injection
│   └── models.py            # ScheduledAction with ADAPTED status
├── orchestrator/
│   └── pathfinder.py        # EXISTING: recalculate_remaining_script()
└── reconciliation/          # EXISTING (Phase 2)
    └── reconciler.py        # RECALCULATE strategy triggers adaptation
```

### Pattern 1: Chaos Event Generation with Weighted Probability

**What:** Roll dice each tick against per-event-type probabilities, select event using weighted random choice.

**When to use:** At start of each tick, before executing scheduled actions.

**Example:**
```python
# src/chaos/event_generator.py
import random
from typing import Optional
from .models import RandomEvent, EventType

class RandomEventGenerator:
    """Generates random chaos events based on configurable probabilities."""

    def __init__(self, chaos_config: dict):
        """Initialize with event probabilities from settings.yaml.

        Args:
            chaos_config: Dict with event_type -> probability (0.0-1.0)
                Example: {"outage": 0.05, "urgent_bug": 0.10, "absence": 0.03}
        """
        self.event_probabilities = chaos_config.get("event_probabilities", {})

    def roll_for_event(self) -> Optional[RandomEvent]:
        """Roll dice to see if any event occurs this tick.

        Returns:
            RandomEvent if triggered, None otherwise
        """
        # Collect enabled event types with non-zero probability
        event_types = []
        probabilities = []

        for event_type, prob in self.event_probabilities.items():
            if prob > 0:
                event_types.append(event_type)
                probabilities.append(prob)

        if not event_types:
            return None

        # Normalize probabilities to sum to 1.0
        total_prob = sum(probabilities)
        normalized_probs = [p / total_prob for p in probabilities]

        # Roll dice for whether ANY event occurs (10% base chance)
        if random.random() > 0.10:
            return None

        # Select which event type using weighted choice
        selected_type = random.choices(event_types, weights=normalized_probs, k=1)[0]

        # Create the event
        return self._create_event(selected_type)

    def _create_event(self, event_type: str) -> RandomEvent:
        """Create RandomEvent instance with details."""
        # Implementation generates event with affected tickets, severity, etc.
        pass
```

**Source:** [Python weighted random choices](https://pynative.com/python-weighted-random-choices-with-probability/)

### Pattern 2: Scenario Adaptation via Action Insertion/Modification

**What:** When chaos event occurs, insert new ScheduledActions into queue and mark conflicting actions as ADAPTED.

**When to use:** After RandomEvent generated, modify affected scenarios' scheduled actions.

**Example:**
```python
# src/chaos/scenario_adapter.py
from src.scheduling.scheduler import Scheduler
from src.scheduling.models import ScheduledAction, ActionStatus
from .models import RandomEvent
import pendulum

class ScenarioAdapter:
    """Modifies active scenarios when random events occur."""

    def __init__(self, scheduler: Scheduler):
        self.scheduler = scheduler

    def adapt_to_event(self, event: RandomEvent, affected_tickets: list[str]) -> dict:
        """Adapt scheduled actions in response to random event.

        Args:
            event: The chaos event that occurred
            affected_tickets: Ticket keys affected by this event

        Returns:
            Adaptation result with inserted/modified action counts
        """
        inserted_actions = []
        adapted_actions = []

        if event.event_type == "urgent_bug":
            # Insert bug fix actions, postpone other work
            for ticket_key in affected_tickets:
                # Mark existing actions as adapted (postponed)
                existing = self._get_pending_actions_for_ticket(ticket_key)
                for action in existing:
                    self.scheduler.mark_action_adapted(
                        action.action_id,
                        reason=f"Postponed due to urgent bug {event.event_id}"
                    )
                    adapted_actions.append(action.action_id)

                # Insert urgent bug fix action
                bug_action = ScheduledAction(
                    scheduled_time=pendulum.now("UTC").add(hours=1),
                    action_type="fix_urgent_bug",
                    agent_id=self._select_available_agent("developer"),
                    ticket_key=ticket_key,
                    scenario_id=event.event_id,
                    params={"event": event.event_type, "severity": event.severity},
                )
                self.scheduler.schedule_action(bug_action)
                inserted_actions.append(bug_action.action_id)

        elif event.event_type == "team_member_absence":
            # Reassign scheduled actions to other agents
            absent_agent = event.details.get("agent_id")
            replacement_agent = self._select_replacement_agent(absent_agent)

            pending_actions = self._get_pending_actions_for_agent(absent_agent)
            for action in pending_actions:
                # Mark original as adapted
                self.scheduler.mark_action_adapted(
                    action.action_id,
                    reason=f"Reassigned due to {absent_agent} absence"
                )
                adapted_actions.append(action.action_id)

                # Schedule replacement action
                replacement = ScheduledAction(
                    scheduled_time=action.scheduled_time,
                    action_type=action.action_type,
                    agent_id=replacement_agent,
                    ticket_key=action.ticket_key,
                    scenario_id=action.scenario_id,
                    params=action.params,
                )
                self.scheduler.schedule_action(replacement)
                inserted_actions.append(replacement.action_id)

        elif event.event_type == "production_outage":
            # Insert emergency response actions, pause non-critical work
            for ticket_key in affected_tickets:
                # Pause non-critical actions (mark as adapted with delay)
                pending = self._get_pending_actions_for_ticket(ticket_key)
                for action in pending:
                    if not self._is_critical_action(action):
                        self.scheduler.mark_action_adapted(
                            action.action_id,
                            reason="Paused during production outage"
                        )
                        adapted_actions.append(action.action_id)

                # Insert outage response action
                response_action = ScheduledAction(
                    scheduled_time=pendulum.now("UTC").add(minutes=15),
                    action_type="emergency_response",
                    agent_id=self._select_available_agent("tech_lead"),
                    ticket_key=ticket_key,
                    scenario_id=event.event_id,
                    params={"event": "outage", "severity": event.severity},
                )
                self.scheduler.schedule_action(response_action)
                inserted_actions.append(response_action.action_id)

        return {
            "event_id": event.event_id,
            "inserted_actions": len(inserted_actions),
            "adapted_actions": len(adapted_actions),
        }
```

**Source:** [Workflow adaptation patterns](https://medium.com/@Deep-concept/top-ai-agentic-workflow-patterns-that-will-lead-in-2026-0e4755fdc6f6)

### Pattern 3: Adaptive Pathfinding with BFS Workflow Recalculation

**What:** When reconciliation detects status divergence, use existing WorkflowPathfinder to recalculate remaining transitions.

**When to use:** When ReconciliationEngine returns RECALCULATE strategy.

**Example:**
```python
# Integration in TickExecutor
from src.reconciliation.reconciler import ReconciliationEngine, AdaptationStrategy
from src.orchestrator.pathfinder import WorkflowPathfinder

class TickExecutor:
    def __init__(self, scheduler, reconciler, pathfinder):
        self.scheduler = scheduler
        self.reconciler = reconciler
        self.pathfinder = pathfinder

    def execute_action(self, action: ScheduledAction) -> dict:
        """Execute action with adaptive pathfinding on divergence."""

        # Reconciliation check
        actual_status = self._get_jira_status(action.ticket_key)
        result = self.reconciler.reconcile_status_mismatch(
            ticket_key=action.ticket_key,
            expected_status=action.expected_status,
            actual_status=actual_status,
            action_type=action.action_type,
        )

        if result.strategy == AdaptationStrategy.RECALCULATE:
            # Status diverged - recalculate remaining path
            remaining_path = self.pathfinder.recalculate_remaining_script(
                current_status=actual_status,
                target_status="Done",
            )

            # Mark current action as adapted
            self.scheduler.mark_action_adapted(
                action.action_id,
                reason=result.reason
            )

            # Insert new actions for recalculated path
            for i, path_action in enumerate(remaining_path):
                new_action = ScheduledAction(
                    scheduled_time=pendulum.now("UTC").add(hours=i + 1),
                    action_type=path_action["type"],
                    agent_id=self._select_agent_for_role(path_action["role"]),
                    ticket_key=action.ticket_key,
                    scenario_id=action.scenario_id,
                    params={"adapted": True, "reason": "status_divergence"},
                )
                self.scheduler.schedule_action(new_action)

            return {
                "status": "adapted",
                "reason": result.reason,
                "new_actions": len(remaining_path),
            }

        elif result.strategy == AdaptationStrategy.SKIP:
            self.scheduler.mark_action_skipped(action.action_id, result.reason)
            return {"status": "skipped", "reason": result.reason}

        elif result.strategy == AdaptationStrategy.CANCEL:
            self.scheduler.mark_action_skipped(action.action_id, result.reason)
            # Scenario tombstoned - cancel remaining actions
            self._cancel_scenario_actions(action.scenario_id, result.tombstone_reason)
            return {"status": "cancelled", "reason": result.tombstone_reason}

        else:  # PROCEED
            # Execute action normally
            return self._execute_jira_action(action)
```

**Source:** Existing codebase - `src/orchestrator/pathfinder.py` lines 349-359

### Pattern 4: Scenario Confidence Score (Script Fidelity)

**What:** Track ratio of executed vs adapted events to measure how much scenario diverged from plan.

**When to use:** After each event execution, update confidence score; trigger "accept reality" if below threshold.

**Example:**
```python
# Extension to SprintScenario model
from src.scenarios.sprint_scenario import SprintScenario

class ScenarioConfidenceTracker:
    """Tracks scenario fidelity (how closely execution matched script)."""

    def calculate_confidence(self, scenario: SprintScenario) -> float:
        """Calculate script_fidelity score (0.0 - 1.0).

        Formula: executed_as_planned / total_events

        Returns:
            Confidence score where 1.0 = perfect script adherence
        """
        total_events = len([e for day in scenario.script for e in day.events])

        if total_events == 0:
            return 1.0

        # Count events that executed as planned (not adapted)
        executed_as_planned = 0
        for event_id in scenario.events_executed:
            event = self._find_event(scenario, event_id)
            if event and not event.execution_result.get("adapted", False):
                executed_as_planned += 1

        return executed_as_planned / total_events

    def should_accept_reality(
        self,
        scenario: SprintScenario,
        threshold: float = 0.7
    ) -> bool:
        """Determine if scenario has diverged too far from script.

        Args:
            scenario: The scenario to check
            threshold: Confidence threshold (default 0.7 = 70%)

        Returns:
            True if confidence below threshold (abandon script mode)
        """
        confidence = self.calculate_confidence(scenario)

        if confidence < threshold:
            # Count external overrides (status changes we didn't make)
            external_overrides = sum(
                1 for event_id in scenario.events_executed
                if self._was_external_override(scenario, event_id)
            )

            # Abandon script if 3+ external changes
            if external_overrides >= 3:
                return True

        return False

    def _find_event(self, scenario: SprintScenario, event_id: str):
        """Find event by ID in scenario script."""
        for day in scenario.script:
            for event in day.events:
                if event.event_id == event_id:
                    return event
        return None

    def _was_external_override(self, scenario: SprintScenario, event_id: str) -> bool:
        """Check if event execution was due to external Jira change."""
        event = self._find_event(scenario, event_id)
        if not event or not event.execution_result:
            return False
        return event.execution_result.get("external_override", False)
```

**Source:** [Reconciliation confidence score concept](https://docs.cloud.google.com/enterprise-knowledge-graph/docs/confidence-score) (analogous metric from Google EKG)

### Anti-Patterns to Avoid

- **Rolling probabilities per-action instead of per-tick:** Don't check chaos probability for every scheduled action - this creates execution overhead. Roll once per tick to decide if chaos event occurs.

- **Deleting adapted actions from schedule:** Don't delete ScheduledActions when adapting - mark them as ADAPTED status for observability. Deletion loses audit trail.

- **Synchronous adaptation blocking tick execution:** Don't let ScenarioAdapter block the tick - insert new actions into queue and continue. Adaptation should be O(1) operation.

- **Hardcoded chaos event templates:** Don't hardcode event details in generator - use event_catalog.yaml config with templates by scenario archetype.

- **Recalculating entire scenario script on single divergence:** Don't regenerate full scenario when one ticket diverges - only recalculate remaining path for that specific ticket.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Graph shortest path | Custom BFS with visited set tracking | stdlib collections.deque + existing pathfinder | WorkflowPathfinder already implements BFS (lines 86-122), proven correct |
| Weighted random selection | Manual cumulative distribution + bisect | random.choices() with weights parameter | Stdlib handles edge cases (weights sum, zero weights, empty population) |
| Business day math for chaos timing | Manual weekday() checks + loops | pendulum.add(days=1) + scheduler.next_business_day() | Phase 1 solved this with Pendulum; reuse existing business_hours module |
| Action queue insertion | Manual heap maintenance | heapq.heappush() on scheduler.queue | O(log n) proven implementation, Phase 3 infrastructure exists |
| Scenario confidence calculation | Complex ML prediction model | Simple ratio: executed_as_planned / total_events | Interpretable metric, no training data needed, sufficient for threshold detection |

**Key insight:** Phase 4 is 90% orchestration of existing Phase 2-3 infrastructure (reconciler, pathfinder, scheduler). The new code is: (1) dice rolling with random.choices, (2) ScenarioAdapter inserting actions via scheduler.schedule_action(), (3) confidence tracker doing arithmetic on scenario.events_executed. Don't rebuild what Phases 2-3 already provide.

## Common Pitfalls

### Pitfall 1: Probability Configuration Complexity

**What goes wrong:** Preset chaos levels (low/medium/high) are inflexible; users want fine-grained control (e.g., 5% outage but 20% blocker).

**Why it happens:** Copying chaos engineering tools like Chaos Mesh which target production systems, not simulations.

**How to avoid:**
- Use per-event-type probabilities in settings.yaml: `event_probabilities: {outage: 0.05, urgent_bug: 0.10}`
- Let users set any probability 0.0-1.0 for each event type
- Don't validate that probabilities "make sense" - let experimentation happen

**Warning signs:** Config file has `chaos_level: medium` instead of granular probabilities per event type.

**Source:** [Chaos engineering best practices](https://steadybit.com/blog/chaos-experiments/) - production chaos tools use scenarios, simulations need probabilities

### Pitfall 2: Action Insertion Without Business Hours Validation

**What goes wrong:** Chaos events inject actions scheduled at 2am on Sunday, breaking business hours constraint.

**Why it happens:** Forgetting to route chaos action timestamps through BusinessHoursScheduler.

**How to avoid:**
- ScenarioAdapter must call scheduler.schedule_action() which uses business_hours internally
- Never directly create ScheduledAction with pendulum.now() - use scheduler.next_available_time()
- Test: Inject 100 chaos events, verify all scheduled_time values are M-F 9am-5pm

**Warning signs:** Scheduled actions with weekday=6 (Sunday) or hour=22 in SQLite persistence.

**Source:** Phase 3 built BusinessHoursScheduler exactly for this - reuse it.

### Pitfall 3: Cascading Adaptations

**What goes wrong:** Adapting one action triggers re-adaptation of dependent actions in infinite loop.

**Why it happens:** ScenarioAdapter doesn't check if action already has ADAPTED status before modifying.

**How to avoid:**
- Only adapt actions with status=PENDING
- Add adaptation_depth field to ScheduledAction, limit to 2 re-adaptations max
- Test: Inject chaos event affecting 10 linked tickets, verify adaptation terminates

**Warning signs:** ScheduledActionStore grows unbounded during chaos event handling.

**Source:** [Rescheduling and replanning patterns](https://link.springer.com/article/10.1007/s00170-020-05850-5) - production rescheduling limits recursion depth

### Pitfall 4: BFS Pathfinding in Cyclic Workflows

**What goes wrong:** Jira workflow has cycle (Done -> Reopened -> In Progress), BFS finds wrong path.

**Why it happens:** WorkflowPathfinder assumes acyclic workflow graph.

**How to avoid:**
- BFS already handles cycles via visited set (pathfinder.py line 108)
- If workflow has cycles, BFS finds shortest path correctly
- Only problem: if multiple equal-length paths exist, BFS picks first found (non-deterministic)

**Warning signs:** recalculate_remaining_script() returns different paths for same input across runs.

**Source:** Existing code review - WorkflowPathfinder uses visited set, so cycles are safe. No action needed.

### Pitfall 5: Confidence Score False Negatives

**What goes wrong:** Scenario marked as diverged even when external changes helped (user moved ticket to Done early).

**Why it happens:** Confidence score treats all adaptations as failures, not distinguishing helpful vs harmful.

**How to avoid:**
- Track positive vs negative adaptations separately
- Skip to terminal status (Done) is positive adaptation - don't count against confidence
- Only count negative adaptations (status regression, removal from sprint)

**Warning signs:** script_fidelity drops below 0.7 even when all tickets completed successfully.

**Source:** Design decision needed - document in PLAN.md whether early completion counts as divergence.

## Code Examples

Verified patterns from existing codebase and research:

### Chaos Event Dice Rolling (Per-Tick)

```python
# src/chaos/event_generator.py - roll_for_event()
import random
from typing import Optional
from .models import RandomEvent

def roll_for_event(self, event_probabilities: dict) -> Optional[RandomEvent]:
    """Roll dice once per tick to generate chaos event.

    Args:
        event_probabilities: Dict of event_type -> probability (0.0-1.0)
            Example: {"outage": 0.05, "urgent_bug": 0.10, "absence": 0.03}

    Returns:
        RandomEvent if triggered, None otherwise
    """
    # Filter to enabled events (non-zero probability)
    enabled_events = {k: v for k, v in event_probabilities.items() if v > 0}

    if not enabled_events:
        return None

    # Weighted random choice - stdlib random.choices handles normalization
    event_types = list(enabled_events.keys())
    weights = list(enabled_events.values())

    # 10% chance ANY event occurs this tick
    if random.random() > 0.10:
        return None

    # Select which event type occurs
    selected_type = random.choices(event_types, weights=weights, k=1)[0]

    return self._create_event(selected_type)
```

**Source:** [Python stdlib random.choices documentation](https://docs.python.org/3/library/random.html)

### Action Insertion via Scheduler (Reuses Phase 3)

```python
# src/chaos/scenario_adapter.py - adapt_to_event()
from src.scheduling.scheduler import Scheduler
from src.scheduling.models import ScheduledAction
import pendulum

def insert_bug_fix_action(
    self,
    scheduler: Scheduler,
    ticket_key: str,
    event_id: str,
) -> ScheduledAction:
    """Insert urgent bug fix action, leveraging Phase 3 scheduler."""

    # Let scheduler handle business hours validation
    bug_fix = ScheduledAction(
        scheduled_time=pendulum.now("UTC").add(hours=2),  # Rough estimate
        action_type="fix_urgent_bug",
        agent_id=self._select_available_agent("developer"),
        ticket_key=ticket_key,
        scenario_id=event_id,
        params={"urgency": "high", "event_type": "urgent_bug"},
    )

    # Scheduler validates business hours, persists to SQLite, pushes to heap
    scheduler.schedule_action(bug_fix)

    return bug_fix
```

**Source:** Existing codebase - `src/scheduling/scheduler.py` lines 42-46

### Workflow Path Recalculation (Reuses Phase 2 Pathfinder)

```python
# Integration in reconciliation flow
from src.orchestrator.pathfinder import WorkflowPathfinder

def recalculate_workflow_on_divergence(
    pathfinder: WorkflowPathfinder,
    ticket_key: str,
    actual_status: str,
) -> list[dict]:
    """Recalculate remaining workflow when status diverges."""

    # Use existing pathfinder BFS algorithm
    remaining_actions = pathfinder.recalculate_remaining_script(
        current_status=actual_status,
        target_status="Done",
    )

    # Returns list of action dicts with type, target_status, role
    # Example: [
    #   {"type": "progress_to_review", "target_status": "Code Review", "role": "developer"},
    #   {"type": "complete_review", "target_status": "Testing", "role": "tech_lead"},
    #   {"type": "qa_approve", "target_status": "Done", "role": "qa"},
    # ]

    return remaining_actions
```

**Source:** Existing codebase - `src/orchestrator/pathfinder.py` lines 349-359

### Confidence Score Calculation

```python
# src/chaos/confidence_tracker.py
from src.scenarios.sprint_scenario import SprintScenario

def calculate_script_fidelity(scenario: SprintScenario) -> float:
    """Calculate how closely execution matched original script.

    Returns:
        Float 0.0-1.0 where 1.0 = perfect adherence, 0.7 = threshold
    """
    total_events = sum(len(day.events) for day in scenario.script)

    if total_events == 0:
        return 1.0

    # Count events executed as originally planned (not adapted)
    executed_as_planned = 0
    for event_id in scenario.events_executed:
        event = scenario._find_event_by_id(event_id)
        if event and not event.execution_result.get("adapted", False):
            executed_as_planned += 1

    return executed_as_planned / total_events


def should_accept_reality(scenario: SprintScenario, threshold: float = 0.7) -> bool:
    """Check if scenario diverged too far - trigger accept reality mode."""
    fidelity = calculate_script_fidelity(scenario)

    # Count external overrides (user manual changes in Jira)
    external_changes = sum(
        1 for event_id in scenario.events_executed
        if scenario._find_event_by_id(event_id).execution_result.get("external_override")
    )

    # Abandon script if fidelity low AND multiple external changes
    return fidelity < threshold and external_changes >= 3
```

**Source:** [Confidence score patterns from Google EKG](https://docs.cloud.google.com/enterprise-knowledge-graph/docs/confidence-score)

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Preset chaos levels (low/med/high) | Per-event-type probabilities | 2024+ chaos tools | Users want granular control, not presets |
| Dijkstra for workflow pathfinding | BFS for unweighted graphs | Always (YAGNI) | Jira workflows unweighted; BFS is O(V+E) vs Dijkstra O(V²) |
| Delete adapted actions | Mark ADAPTED status for audit | 2025+ observability trends | Preserves adaptation history for debugging |
| Synchronous event injection | Async action insertion via queue | 2024+ (async patterns) | Non-blocking chaos injection, tick continues |
| Fixed scenario scripts | Dynamic confidence-based adaptation | 2026 (this system) | Accept reality when divergence too high |

**Deprecated/outdated:**
- **APScheduler for chaos injection:** Heavy framework for what's just dice rolling + queue insertion
- **NetworkX for simple BFS:** Adds dependency when stdlib collections.deque sufficient
- **Chaos Mesh concepts in simulation:** Production fault injection ≠ simulation event generation

## Open Questions

Things that couldn't be fully resolved during research:

1. **Event Catalog Structure**
   - What we know: Chaos events should be weighted by scenario archetype (more blockers in blocker_heavy sprint)
   - What's unclear: Should event_catalog.yaml map archetype -> event weights, or use dynamic LLM selection?
   - Recommendation: Start with static archetype -> event weights mapping, add LLM selection in Phase 5 if needed

2. **Confidence Score Positive vs Negative Adaptations**
   - What we know: Not all adaptations are failures (user completing ticket early is good)
   - What's unclear: Should early completion count against script_fidelity?
   - Recommendation: Document decision in PLAN.md - suggest treating terminal status transitions as positive adaptations

3. **Team Member Absence Duration**
   - What we know: Absence event should reassign actions to other agents
   - What's unclear: How long does absence last? Single tick or multi-day?
   - Recommendation: Add duration_ticks field to RandomEvent model, default to 2-4 ticks

4. **Chaos Event Conflicts**
   - What we know: Multiple chaos events could affect same ticket simultaneously
   - What's unclear: Priority/resolution when outage + urgent_bug both triggered for same ticket
   - Recommendation: Event severity field breaks ties (critical > high > medium > low)

## Sources

### Primary (HIGH confidence)

- **Existing Codebase**
  - `src/orchestrator/pathfinder.py` - BFS pathfinding implementation (lines 86-122, 349-359)
  - `src/reconciliation/reconciler.py` - ReconciliationEngine with RECALCULATE strategy
  - `src/scheduling/scheduler.py` - Phase 3 action queue and persistence (lines 42-46)
  - `src/scenarios/sprint_scenario.py` - SprintScenario with event tracking

- **Python Standard Library**
  - [random.choices() documentation](https://docs.python.org/3/library/random.html) - Weighted random selection
  - [collections.deque](https://docs.python.org/3/library/collections.html#collections.deque) - BFS queue implementation
  - [heapq](https://docs.python.org/3/library/heapq.html) - Priority queue operations

- **NetworkX Documentation**
  - [NetworkX Shortest Paths](https://networkx.org/documentation/stable/reference/algorithms/shortest_paths.html) - Graph algorithms reference
  - [BFS vs Dijkstra comparison](https://networkx.guide/algorithms/graph-traversals/bfs/)

### Secondary (MEDIUM confidence)

- **Chaos Engineering Best Practices**
  - [Chaos Engineering Types, Experiments, and Best Practices](https://steadybit.com/blog/chaos-experiments/) - Event types and patterns
  - [Top Chaos Experiments Every DevOps Engineer Should Know](https://medium.com/@ismailkovvuru/top-chaos-experiments-every-devops-engineer-should-know-c4f8a72c3f3f) - Common scenarios

- **Workflow Adaptation Patterns**
  - [Machine learning and optimization for production rescheduling](https://link.springer.com/article/10.1007/s00170-020-05850-5) - Rescheduling algorithms
  - [Top AI Agentic Workflow Patterns That Will Lead in 2026](https://medium.com/@Deep-concept/top-ai-agentic-workflow-patterns-that-will-lead-in-2026-0e4755fdc6f6) - Adaptive workflow patterns

- **Weighted Random Selection**
  - [Python weighted random choices with probability](https://pynative.com/python-weighted-random-choices-with-probability/) - Implementation patterns
  - [How to get weighted random choice in Python](https://www.geeksforgeeks.org/python/how-to-get-weighted-random-choice-in-python/) - Usage examples

### Tertiary (LOW confidence - informational only)

- **Confidence Scoring Concept**
  - [Google Enterprise Knowledge Graph - Reconciliation Confidence Score](https://docs.cloud.google.com/enterprise-knowledge-graph/docs/confidence-score) - Analogous metric (different domain)

- **Jira Workflow Transitions**
  - [Jira Cloud REST API - Workflow Transitions](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-workflow-transition-properties/) - API reference (deprecation warning: June 1, 2026)
  - [Get Entire Workflow with Transition Names](https://community.atlassian.com/t5/Jira-questions/Get-Entire-Workflow-with-Transition-Names/qaq-p/1320494) - Community discussion

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - stdlib random.choices + Phase 3 scheduler infrastructure sufficient
- Architecture: HIGH - Reuses 90% of Phase 2-3 patterns (reconciler, pathfinder, scheduler)
- Pitfalls: MEDIUM - Business hours validation and cascading adaptations need testing

**Research date:** 2026-01-28
**Valid until:** 2026-03-01 (30 days - stable patterns, stdlib not changing)

**Key Dependencies:**
- Phase 2: ReconciliationEngine with RECALCULATE/SKIP/CANCEL strategies
- Phase 3: Scheduler, ScheduledAction model, BusinessHoursScheduler
- Existing: WorkflowPathfinder with BFS, SprintScenario with event tracking

**Research Note:** The Jira workflow transitions API has deprecation warning (June 1, 2026), but this affects fetching workflow schema, not individual ticket transitions. The simulator uses per-ticket available transitions (GET /issue/{key}/transitions), which remains supported. No migration risk for Phase 4.
