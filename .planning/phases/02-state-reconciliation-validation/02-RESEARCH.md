# Phase 2: State Reconciliation & Validation - Research

**Researched:** 2026-01-28
**Domain:** State validation, idempotency, optimistic locking, reconciliation engines, circuit breakers
**Confidence:** HIGH

## Summary

Phase 2 implements a reconciliation engine that validates Jira state before every action and adapts gracefully when reality diverges from the simulation plan. The system must handle concurrent modifications (user manually changes ticket status), stale scenarios (ticket moved out of sprint), and network failures (Jira API unavailable) without cascading failures.

The codebase already has basic sync capability (`sync_state_with_jira()` in `src/state/simulation_state.py`) that creates scenarios for untracked tickets, but lacks pre-execution validation, conflict detection, idempotency guarantees, and graceful degradation.

**Primary recommendation:** Implement pre-execution validators using Jira's `updated` timestamp for optimistic locking, add execution IDs (UUIDs) to prevent duplicate actions, create a reconciliation engine with adaptation strategies (cancel/recalculate/reschedule), and use circuit breaker patterns for graceful degradation on API failures.

## Standard Stack

The established libraries/tools for reconciliation and validation:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | 2.6.1+ (already used) | Data validation with computed fields | Already in stack, handles validation and serialization |
| pybreaker | 1.1.0+ | Circuit breaker pattern implementation | Industry-standard Python circuit breaker, battle-tested |
| uuid | stdlib | Execution ID generation | Built-in, cryptographically sound UUIDs for idempotency keys |
| pendulum | 3.1.0+ (Phase 1) | Timestamp parsing and comparison | Already migrated in Phase 1 for timezone-aware operations |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tenacity | 8.2.3+ | Retry logic with exponential backoff | Complement circuit breaker for transient failures |
| redis-py | 5.0.0+ (optional) | Distributed execution ID tracking | If scaling beyond single-instance (future phase) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pybreaker | aiobreaker | Async-first, but adds complexity; pybreaker works with sync Jira client |
| uuid stdlib | nanoid | Shorter IDs but non-standard; UUID is universally recognized |
| Custom validators | Pydantic validators | Hand-rolled validation is error-prone; Pydantic is well-tested |
| In-memory ID tracking | Redis/database | Stateless vs stateful; in-memory works for single-instance deployment |

**Installation:**
```bash
pip install pybreaker>=1.1.0 tenacity>=8.2.3
# Already have: pydantic>=2.6.1, pendulum>=3.1.0
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── reconciliation/          # NEW: Reconciliation module
│   ├── __init__.py
│   ├── validators.py        # Pre-execution validators
│   ├── reconciler.py        # Reconciliation engine
│   ├── execution_tracker.py # Idempotency tracking
│   └── adapters.py          # Adaptation strategies
├── services/
│   └── jira_client.py       # Add circuit breaker wrapper
└── orchestrator/
    └── orchestrator.py      # Inject validators before execution
```

### Pattern 1: Pre-Execution Validation (Precondition Checks)
**What:** Before executing an action on a ticket, validate that Jira state matches expected state (status, assignee, sprint membership).

**When to use:** Before every action that modifies Jira state (transitions, comments, work logs).

**Example:**
```python
# src/reconciliation/validators.py
from dataclasses import dataclass
from typing import Optional
import pendulum
from src.services.jira_client import JiraClient

@dataclass
class ValidationResult:
    """Result of pre-execution validation."""
    valid: bool
    reason: Optional[str] = None
    actual_state: Optional[dict] = None
    expected_state: Optional[dict] = None

class PreExecutionValidator:
    """Validates Jira state before action execution."""

    def __init__(self, jira_client: JiraClient):
        self.jira = jira_client

    def validate_status(
        self,
        ticket_key: str,
        expected_status: str,
        updated_since: Optional[pendulum.DateTime] = None
    ) -> ValidationResult:
        """Validate ticket is in expected status and hasn't changed since last seen.

        Args:
            ticket_key: Jira ticket key (e.g., "ESCRUM-123")
            expected_status: Expected status name (e.g., "In Progress")
            updated_since: Optional timestamp - fail if ticket updated after this

        Returns:
            ValidationResult with valid=True if checks pass
        """
        try:
            issue = self.jira.get_issue(ticket_key)
            actual_status = issue.fields.status.name

            # Check status match
            if actual_status != expected_status:
                return ValidationResult(
                    valid=False,
                    reason=f"Status changed: expected '{expected_status}', got '{actual_status}'",
                    actual_state={"status": actual_status},
                    expected_state={"status": expected_status}
                )

            # Check optimistic locking if timestamp provided
            if updated_since:
                # Jira returns updated in format "yyyy-MM-dd'T'HH:mm:ss.SSSZ"
                issue_updated = pendulum.parse(issue.fields.updated)
                if issue_updated > updated_since:
                    return ValidationResult(
                        valid=False,
                        reason=f"Ticket modified after last sync (updated: {issue_updated.isoformat()})",
                        actual_state={"updated": issue_updated.isoformat()},
                        expected_state={"updated_before": updated_since.isoformat()}
                    )

            return ValidationResult(valid=True)

        except Exception as e:
            return ValidationResult(
                valid=False,
                reason=f"Jira API error: {str(e)}"
            )

    def validate_sprint_membership(
        self,
        ticket_key: str,
        expected_in_active_sprint: bool = True
    ) -> ValidationResult:
        """Validate ticket is in active sprint (or not, if expected_in_active_sprint=False)."""
        try:
            in_sprint = self.jira.is_issue_in_active_sprint(ticket_key)

            if in_sprint != expected_in_active_sprint:
                return ValidationResult(
                    valid=False,
                    reason=f"Sprint membership changed: expected in_sprint={expected_in_active_sprint}, got {in_sprint}",
                    actual_state={"in_active_sprint": in_sprint},
                    expected_state={"in_active_sprint": expected_in_active_sprint}
                )

            return ValidationResult(valid=True)

        except Exception as e:
            return ValidationResult(
                valid=False,
                reason=f"Jira API error: {str(e)}"
            )
```

### Pattern 2: Idempotency via Execution IDs
**What:** Generate a unique execution ID for each planned action and track which have been executed to prevent duplicate API calls.

**When to use:** Every action execution, especially when retries are involved.

**Example:**
```python
# src/reconciliation/execution_tracker.py
import uuid
from typing import Optional, Set
from dataclasses import dataclass
from datetime import timedelta
import pendulum

@dataclass
class ExecutionRecord:
    """Record of an executed action."""
    execution_id: str
    action_type: str
    ticket_key: str
    executed_at: pendulum.DateTime
    result: str  # "success" | "failure" | "skipped"

class ExecutionTracker:
    """Tracks executed actions via execution IDs for idempotency."""

    def __init__(self, cleanup_age_hours: int = 48):
        self._executed: dict[str, ExecutionRecord] = {}
        self._cleanup_age = timedelta(hours=cleanup_age_hours)

    def generate_execution_id(
        self,
        action_type: str,
        ticket_key: str,
        agent_id: str
    ) -> str:
        """Generate deterministic execution ID from action parameters.

        This enables duplicate detection even if simulator restarts.
        Format: {action_type}:{ticket_key}:{agent_id}:{uuid}
        """
        unique_id = str(uuid.uuid4())[:8]
        return f"{action_type}:{ticket_key}:{agent_id}:{unique_id}"

    def is_executed(self, execution_id: str) -> bool:
        """Check if execution ID has already been executed."""
        return execution_id in self._executed

    def record_execution(
        self,
        execution_id: str,
        action_type: str,
        ticket_key: str,
        result: str
    ) -> None:
        """Record that an execution ID has been executed."""
        self._executed[execution_id] = ExecutionRecord(
            execution_id=execution_id,
            action_type=action_type,
            ticket_key=ticket_key,
            executed_at=pendulum.now("UTC"),
            result=result
        )

        # Cleanup old executions
        self._cleanup_old_executions()

    def _cleanup_old_executions(self) -> None:
        """Remove execution records older than cleanup_age."""
        cutoff = pendulum.now("UTC") - self._cleanup_age
        self._executed = {
            eid: record
            for eid, record in self._executed.items()
            if record.executed_at > cutoff
        }
```

### Pattern 3: Reconciliation Engine with Adaptation Strategies
**What:** When validation detects divergence, the reconciler provides strategies to adapt the simulation plan.

**When to use:** After validation failure, before deciding whether to proceed, cancel, or reschedule.

**Example:**
```python
# src/reconciliation/reconciler.py
from enum import Enum
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class AdaptationStrategy(str, Enum):
    """Strategies for adapting when state diverges."""
    CANCEL = "cancel"           # Cancel action, mark scenario as invalidated
    RECALCULATE = "recalculate" # Recompute action plan from current Jira state
    RESCHEDULE = "reschedule"   # Retry action later (transient failure)
    PROCEED = "proceed"         # Minor divergence, safe to proceed
    SKIP = "skip"              # Skip action but continue scenario

@dataclass
class ReconciliationResult:
    """Result of reconciliation decision."""
    strategy: AdaptationStrategy
    reason: str
    tombstone_reason: Optional[str] = None  # Why scenario was invalidated
    new_plan: Optional[list] = None         # Recalculated action plan

class ReconciliationEngine:
    """Decides how to adapt when Jira state diverges from plan."""

    def reconcile_status_mismatch(
        self,
        ticket_key: str,
        expected_status: str,
        actual_status: str,
        action_type: str
    ) -> ReconciliationResult:
        """Decide how to handle status mismatch.

        Adaptation logic:
        - If user moved ticket forward: SKIP (they did our work)
        - If user moved ticket backward: RECALCULATE (recalc from current state)
        - If ticket completed externally: CANCEL (scenario done)
        """
        # Terminal statuses - scenario is complete
        terminal_statuses = {"Done", "Closed", "Resolved"}
        if actual_status in terminal_statuses:
            return ReconciliationResult(
                strategy=AdaptationStrategy.CANCEL,
                reason=f"Ticket moved to terminal status '{actual_status}' externally",
                tombstone_reason=f"User completed ticket manually ({actual_status})"
            )

        # Status progression map
        status_order = {
            "To Do": 0,
            "In Progress": 1,
            "Code Review": 2,
            "In Review": 2,
            "Ready for QA": 3,
            "Testing": 3,
            "Done": 4
        }

        expected_rank = status_order.get(expected_status, -1)
        actual_rank = status_order.get(actual_status, -1)

        if actual_rank > expected_rank:
            # Ticket progressed ahead - skip our action
            return ReconciliationResult(
                strategy=AdaptationStrategy.SKIP,
                reason=f"Ticket already progressed to '{actual_status}' externally"
            )
        elif actual_rank < expected_rank:
            # Ticket regressed - recalculate from current state
            return ReconciliationResult(
                strategy=AdaptationStrategy.RECALCULATE,
                reason=f"Ticket regressed to '{actual_status}', recalculating plan"
            )
        else:
            # Unknown statuses - proceed cautiously
            return ReconciliationResult(
                strategy=AdaptationStrategy.PROCEED,
                reason=f"Unknown status progression, attempting action"
            )

    def reconcile_sprint_mismatch(
        self,
        ticket_key: str,
        expected_in_sprint: bool,
        actual_in_sprint: bool
    ) -> ReconciliationResult:
        """Decide how to handle sprint membership mismatch."""
        if expected_in_sprint and not actual_in_sprint:
            return ReconciliationResult(
                strategy=AdaptationStrategy.CANCEL,
                reason=f"Ticket removed from active sprint externally",
                tombstone_reason="Removed from sprint by user"
            )
        elif not expected_in_sprint and actual_in_sprint:
            return ReconciliationResult(
                strategy=AdaptationStrategy.PROCEED,
                reason="Ticket added to sprint externally, proceeding"
            )
        else:
            return ReconciliationResult(
                strategy=AdaptationStrategy.PROCEED,
                reason="Sprint membership matches"
            )

    def reconcile_api_failure(
        self,
        error: Exception,
        retry_count: int = 0
    ) -> ReconciliationResult:
        """Decide how to handle Jira API failure."""
        # Transient errors - reschedule for retry
        transient_errors = ["timeout", "503", "429", "connection"]
        error_str = str(error).lower()

        if any(err in error_str for err in transient_errors):
            if retry_count < 3:
                return ReconciliationResult(
                    strategy=AdaptationStrategy.RESCHEDULE,
                    reason=f"Transient error ({error}), will retry"
                )

        # Not found - cancel scenario
        if "404" in error_str or "not found" in error_str:
            return ReconciliationResult(
                strategy=AdaptationStrategy.CANCEL,
                reason=f"Ticket not found in Jira",
                tombstone_reason="Ticket deleted from Jira"
            )

        # Other errors - skip action but continue
        return ReconciliationResult(
            strategy=AdaptationStrategy.SKIP,
            reason=f"Jira API error ({error}), skipping action"
        )
```

### Pattern 4: Circuit Breaker for Jira Client
**What:** Wrap Jira API calls with circuit breaker to prevent cascade failures when Jira is down.

**When to use:** Around all external API calls (Jira client methods).

**Example:**
```python
# src/services/jira_client.py (enhanced)
from pybreaker import CircuitBreaker, CircuitBreakerListener
import logging

logger = logging.getLogger(__name__)

class LoggingCircuitBreakerListener(CircuitBreakerListener):
    """Log circuit breaker state changes."""

    def state_change(self, cb, old_state, new_state):
        logger.warning(f"Circuit breaker '{cb.name}' changed from {old_state.name} to {new_state.name}")

    def failure(self, cb, exc):
        logger.debug(f"Circuit breaker '{cb.name}' recorded failure: {exc}")

    def success(self, cb):
        logger.debug(f"Circuit breaker '{cb.name}' recorded success")

# Global circuit breaker for Jira API
# fail_max: 5 failures opens circuit
# timeout_duration: 60s before trying again (half-open)
jira_breaker = CircuitBreaker(
    fail_max=5,
    timeout_duration=60,
    name="jira_api",
    listeners=[LoggingCircuitBreakerListener()]
)

class ResilientJiraClient:
    """Wrapper around JiraClient with circuit breaker."""

    def __init__(self, jira_client: JiraClient):
        self._client = jira_client

    @jira_breaker
    def get_issue(self, issue_key: str):
        """Get issue with circuit breaker protection."""
        return self._client.get_issue(issue_key)

    @jira_breaker
    def transition_issue(self, issue_key: str, transition_name: str):
        """Transition issue with circuit breaker protection."""
        return self._client.transition_issue(issue_key, transition_name)

    def get_breaker_state(self) -> str:
        """Get current circuit breaker state for monitoring."""
        return jira_breaker.current_state.name  # "closed", "open", "half_open"
```

### Pattern 5: Scenario Staleness Detection
**What:** Detect scenarios that haven't been validated for N ticks and auto-remove them as stale.

**When to use:** At end of each tick, cleanup phase.

**Example:**
```python
# src/state/models.py (enhanced ActiveScenario)
from pydantic import BaseModel, Field

class ActiveScenario(BaseModel):
    # ... existing fields ...

    last_validated: pendulum.DateTime = Field(
        default_factory=lambda: pendulum.now("UTC")
    )
    validation_tick_count: int = 0  # Ticks since last successful validation

    def mark_validated(self) -> None:
        """Mark scenario as validated this tick."""
        self.last_validated = pendulum.now("UTC")
        self.validation_tick_count = 0

    def increment_validation_miss(self) -> None:
        """Record that validation was skipped/failed this tick."""
        self.validation_tick_count += 1

    def is_stale(self, staleness_threshold: int = 4) -> bool:
        """Check if scenario hasn't been validated for too many ticks."""
        return self.validation_tick_count >= staleness_threshold

# In orchestrator cleanup
def cleanup_stale_scenarios(state: SimulationState, staleness_threshold: int = 4) -> int:
    """Remove scenarios that haven't been validated in N ticks."""
    stale_ids = []

    for scenario_id, scenario in state.active_scenarios.items():
        if scenario.is_stale(staleness_threshold):
            stale_ids.append(scenario_id)
            logger.warning(
                f"Removing stale scenario {scenario.ticket_key} "
                f"(unvalidated for {scenario.validation_tick_count} ticks)"
            )

    for scenario_id in stale_ids:
        state.complete_scenario(scenario_id)
        # Log tombstone reason
        state.record_action(
            agent_id="system",
            agent_name="System",
            action_type="scenario_invalidated",
            scenario_id=scenario_id,
            details=f"Stale scenario (unvalidated for {staleness_threshold}+ ticks)"
        )

    return len(stale_ids)
```

### Anti-Patterns to Avoid
- **Validation without adaptation:** Don't just detect divergence—provide strategies to adapt.
- **Synchronous validation blocking execution:** Validate before action, not after starting it.
- **Retrying without exponential backoff:** Use tenacity or circuit breaker to avoid thundering herd.
- **Global circuit breaker state pollution:** Use separate breakers for different API groups (read vs write).
- **Storing execution IDs forever:** Cleanup old IDs after 48 hours to prevent memory leak.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Circuit breaker pattern | Custom failure counter | pybreaker | Edge cases: half-open state, timeout management, thread safety |
| Retry with backoff | Custom sleep loop | tenacity | Handles jitter, max attempts, retry conditions, async support |
| Execution ID generation | Sequential IDs | uuid.uuid4() | UUIDs are globally unique, cryptographically sound, collision-resistant |
| Timestamp comparison | String comparison | pendulum.parse() + comparison | Timezone handling, DST transitions, ISO 8601 variants |
| State machine validation | Manual if/else chains | Pydantic validators | Declarative, composable, automatic error messages |

**Key insight:** Reconciliation is a distributed systems problem disguised as a simple "check before acting" task. The edge cases that make it hard:
- Race conditions (user changes ticket between validation and execution)
- Cascading failures (Jira down → all actions fail → scenario state inconsistent)
- Partial failures (transition succeeds but comment fails)
- Non-idempotent operations (commenting twice, logging work twice)
- Time-based divergence (scenario plan assumes 2-day cycle, reality takes 5 days)

## Common Pitfalls

### Pitfall 1: Validating Status but Not Timestamp (Missing Optimistic Locking)
**What goes wrong:** User changes ticket status from "In Progress" to "Code Review" and back to "In Progress" between validation and execution. Validator sees "In Progress" and proceeds, but actual state has diverged.

**Why it happens:** Status-only validation misses the temporal dimension—the ticket has changed even if status matches.

**How to avoid:**
```python
# BAD (status-only validation)
actual_status = jira.get_issue(ticket_key).fields.status.name
if actual_status != expected_status:
    return ValidationResult(valid=False)

# GOOD (optimistic locking with timestamp)
issue = jira.get_issue(ticket_key)
actual_status = issue.fields.status.name
issue_updated = pendulum.parse(issue.fields.updated)

if actual_status != expected_status:
    return ValidationResult(valid=False, reason="Status mismatch")

if issue_updated > last_sync_time:
    return ValidationResult(valid=False, reason="Ticket modified since last sync")
```

**Warning signs:**
- Actions execute on tickets user has modified
- Logs show "correct status" but unexpected results
- Race condition failures in test environments

### Pitfall 2: Circuit Breaker Opens, All Actions Fail, Scenarios Invalidated
**What goes wrong:** Jira has brief outage (5 failures), circuit breaker opens, all subsequent actions fail with "circuit open" error, orchestrator marks all scenarios as stale/invalid.

**Why it happens:** Circuit breaker prevents API calls, but reconciler treats "circuit open" same as "ticket not found."

**How to avoid:**
```python
# BAD (treat circuit open as hard failure)
try:
    issue = jira.get_issue(ticket_key)
except Exception as e:
    return ReconciliationResult(
        strategy=AdaptationStrategy.CANCEL,
        reason=f"Failed to fetch issue: {e}"
    )

# GOOD (distinguish circuit open from other failures)
from pybreaker import CircuitBreakerError

try:
    issue = jira.get_issue(ticket_key)
except CircuitBreakerError:
    return ReconciliationResult(
        strategy=AdaptationStrategy.RESCHEDULE,
        reason="Jira circuit breaker open, will retry when Jira recovers"
    )
except Exception as e:
    # Real API error, handle accordingly
    return reconcile_api_failure(e)
```

**Warning signs:**
- All scenarios invalidated after brief Jira outage
- Logs show "circuit open" mixed with "scenario cancelled"
- State empties during downtime, doesn't recover

### Pitfall 3: Execution IDs Generated After Execution (No Duplicate Protection)
**What goes wrong:** Action executes (Jira transition succeeds), then execution ID is generated and stored. On retry, new ID is generated, action executes again, creating duplicate work logs/comments.

**Why it happens:** Execution ID created too late in the flow.

**How to avoid:**
```python
# BAD (ID generated after execution)
def execute_action(action_type, ticket_key, agent_id):
    # Execute first
    jira.transition_issue(ticket_key, "In Progress")
    jira.add_comment(ticket_key, "Started work")

    # Then track (TOO LATE)
    execution_id = tracker.generate_execution_id(action_type, ticket_key, agent_id)
    tracker.record_execution(execution_id, "success")

# GOOD (ID generated before execution, checked first)
def execute_action(action_type, ticket_key, agent_id):
    # Generate ID first
    execution_id = tracker.generate_execution_id(action_type, ticket_key, agent_id)

    # Check if already executed
    if tracker.is_executed(execution_id):
        logger.info(f"Skipping duplicate execution: {execution_id}")
        return {"status": "skipped", "reason": "already_executed"}

    # Execute
    jira.transition_issue(ticket_key, "In Progress")
    jira.add_comment(ticket_key, "Started work")

    # Record success
    tracker.record_execution(execution_id, action_type, ticket_key, "success")
```

**Warning signs:**
- Duplicate comments on same ticket
- Work logged twice for same action
- Tests fail with "already transitioned" errors

### Pitfall 4: Staleness Detection Based on Time, Not Tick Count
**What goes wrong:** Scenario marked stale after 2 hours of no validation, but simulator only runs 3 times during business hours (M-F 9-5). Scenario is still active but marked stale due to wall-clock time gap.

**Why it happens:** Time-based staleness doesn't account for business hours scheduling.

**How to avoid:**
```python
# BAD (time-based staleness)
STALENESS_THRESHOLD = timedelta(hours=2)

def is_stale(scenario):
    return (pendulum.now("UTC") - scenario.last_validated) > STALENESS_THRESHOLD

# GOOD (tick-based staleness)
STALENESS_TICK_THRESHOLD = 4  # 4 ticks without validation

def is_stale(scenario):
    return scenario.validation_tick_count >= STALENESS_TICK_THRESHOLD

# Increment on each tick if validation skipped/failed
scenario.increment_validation_miss()
```

**Warning signs:**
- Scenarios invalidated over weekends
- Active scenarios disappear after long business hours gaps
- Tests with frozen time don't trigger staleness (opposite problem)

### Pitfall 5: Tombstone Reasons Not Logged, Unclear Why Scenarios Cancelled
**What goes wrong:** Scenario is cancelled due to divergence, but no record exists of *why*. Logs show "scenario removed" but not "user completed ticket manually" vs "ticket deleted from Jira" vs "moved out of sprint."

**Why it happens:** Reconciliation logic makes decision but doesn't record reasoning.

**How to avoid:**
```python
# BAD (cancel without explanation)
if actual_status == "Done":
    state.complete_scenario(scenario_id)

# GOOD (record tombstone reason)
if actual_status == "Done":
    state.complete_scenario(scenario_id)
    state.record_action(
        agent_id="system",
        agent_name="System",
        action_type="scenario_cancelled",
        scenario_id=scenario_id,
        ticket_key=ticket_key,
        details=f"Tombstone: User completed ticket manually (status: {actual_status})"
    )
    logger.info(f"Cancelled scenario {ticket_key}: user completed manually")
```

**Warning signs:**
- Unable to debug why scenarios disappear
- Logs show high cancellation rate but no patterns
- QA asks "why did this scenario stop tracking?"

## Code Examples

Verified patterns from research:

### Idempotency Key Pattern (2026 Best Practice)
```python
# Source: https://devtechtools.org/en/blog/idempotency-key-patterns-for-exactly-once-api-execution
# Source: https://blog.algomaster.io/p/idempotency-in-distributed-systems
import uuid
from datetime import timedelta
import pendulum

class IdempotentActionExecutor:
    """Execute actions with idempotency guarantees."""

    def __init__(self, jira_client, execution_tracker):
        self.jira = jira_client
        self.tracker = execution_tracker

    def execute_transition(
        self,
        ticket_key: str,
        target_status: str,
        agent_id: str
    ) -> dict:
        """Execute status transition with idempotency.

        Returns:
            dict with keys: status ("executed" | "skipped"), execution_id, reason
        """
        # Generate deterministic execution ID
        action_type = f"transition_to_{target_status.lower().replace(' ', '_')}"
        execution_id = self.tracker.generate_execution_id(
            action_type=action_type,
            ticket_key=ticket_key,
            agent_id=agent_id
        )

        # Check if already executed
        if self.tracker.is_executed(execution_id):
            return {
                "status": "skipped",
                "execution_id": execution_id,
                "reason": "Already executed (idempotency)"
            }

        # Execute action
        try:
            success = self.jira.transition_issue(ticket_key, target_status)
            result = "success" if success else "failure"
        except Exception as e:
            result = "failure"
            raise
        finally:
            # Record execution even if failed (prevents retry loops)
            self.tracker.record_execution(
                execution_id=execution_id,
                action_type=action_type,
                ticket_key=ticket_key,
                result=result
            )

        return {
            "status": "executed",
            "execution_id": execution_id,
            "result": result
        }
```

### Optimistic Locking with Jira Updated Field
```python
# Source: https://docs.atlassian.com/software/jira/docs/api/
# Jira updated field format: "yyyy-MM-dd'T'HH:mm:ss.SSSZ"
import pendulum

class OptimisticLockingValidator:
    """Validate using Jira's updated timestamp."""

    def __init__(self, jira_client):
        self.jira = jira_client

    def validate_with_timestamp(
        self,
        ticket_key: str,
        expected_status: str,
        last_known_updated: str  # ISO 8601 timestamp from previous fetch
    ) -> ValidationResult:
        """Validate ticket hasn't changed since last_known_updated.

        This is optimistic locking: we assume no conflict, but verify
        before writing by comparing timestamps.
        """
        issue = self.jira.get_issue(ticket_key)

        # Parse Jira's updated timestamp
        # Format: "2026-01-28T10:30:45.123+0000"
        current_updated = pendulum.parse(issue.fields.updated)
        last_known = pendulum.parse(last_known_updated)

        # Check if modified since last read
        if current_updated > last_known:
            return ValidationResult(
                valid=False,
                reason=(
                    f"Optimistic lock failed: ticket modified at {current_updated.isoformat()} "
                    f"(last known: {last_known.isoformat()})"
                ),
                actual_state={
                    "updated": current_updated.isoformat(),
                    "status": issue.fields.status.name
                },
                expected_state={
                    "updated_before": last_known.isoformat(),
                    "status": expected_status
                }
            )

        # Also check status still matches
        if issue.fields.status.name != expected_status:
            return ValidationResult(
                valid=False,
                reason=f"Status changed from '{expected_status}' to '{issue.fields.status.name}'",
                actual_state={"status": issue.fields.status.name},
                expected_state={"status": expected_status}
            )

        return ValidationResult(valid=True)
```

### Circuit Breaker with Fallback
```python
# Source: https://github.com/danielfm/pybreaker
# Source: https://medium.com/@fahimad/resilient-apis-retry-logic-circuit-breakers-and-fallback-mechanisms-cfd37f523f43
from pybreaker import CircuitBreaker

# Create circuit breaker with custom thresholds
jira_read_breaker = CircuitBreaker(
    fail_max=5,           # Open after 5 failures
    timeout_duration=60,  # Try again after 60s
    name="jira_reads"
)

jira_write_breaker = CircuitBreaker(
    fail_max=3,           # More sensitive for writes
    timeout_duration=120, # Longer recovery time
    name="jira_writes"
)

class ResilientJiraClient:
    """Jira client with circuit breakers and fallbacks."""

    def __init__(self, jira_client, cache=None):
        self._client = jira_client
        self._cache = cache or {}  # Simple in-memory cache

    @jira_read_breaker
    def get_issue_with_fallback(self, ticket_key: str):
        """Get issue with circuit breaker and cache fallback."""
        issue = self._client.get_issue(ticket_key)

        # Cache successful read
        self._cache[ticket_key] = {
            "issue": issue,
            "cached_at": pendulum.now("UTC")
        }

        return issue

    def get_issue_fallback(self, ticket_key: str):
        """Fallback when circuit is open - return cached data."""
        if jira_read_breaker.current_state.name == "open":
            logger.warning(f"Circuit open, using cached data for {ticket_key}")
            cached = self._cache.get(ticket_key)
            if cached:
                age = (pendulum.now("UTC") - cached["cached_at"]).seconds
                logger.info(f"Returning cached issue (age: {age}s)")
                return cached["issue"]
            else:
                raise Exception(f"Circuit open and no cached data for {ticket_key}")
        else:
            return self.get_issue_with_fallback(ticket_key)
```

### Graceful Degradation on Precondition Failure
```python
# Source: https://www.codereliant.io/p/circuit-breaker-pattern
def execute_action_with_validation(action, validator, reconciler):
    """Execute action with pre-validation and graceful degradation."""

    # 1. Validate preconditions
    validation = validator.validate_status(
        ticket_key=action.ticket_key,
        expected_status=action.expected_status
    )

    if not validation.valid:
        # 2. Reconcile divergence
        reconciliation = reconciler.reconcile_status_mismatch(
            ticket_key=action.ticket_key,
            expected_status=action.expected_status,
            actual_status=validation.actual_state.get("status"),
            action_type=action.action_type
        )

        # 3. Adapt based on strategy
        if reconciliation.strategy == AdaptationStrategy.CANCEL:
            logger.warning(
                f"Cancelling action on {action.ticket_key}: {reconciliation.reason}"
            )
            return {
                "status": "cancelled",
                "reason": reconciliation.reason,
                "tombstone": reconciliation.tombstone_reason
            }

        elif reconciliation.strategy == AdaptationStrategy.SKIP:
            logger.info(
                f"Skipping action on {action.ticket_key}: {reconciliation.reason}"
            )
            return {
                "status": "skipped",
                "reason": reconciliation.reason
            }

        elif reconciliation.strategy == AdaptationStrategy.RECALCULATE:
            logger.info(
                f"Recalculating plan for {action.ticket_key}: {reconciliation.reason}"
            )
            # Recalc logic would go here
            return {
                "status": "recalculated",
                "new_plan": reconciliation.new_plan
            }

        elif reconciliation.strategy == AdaptationStrategy.PROCEED:
            logger.info(
                f"Proceeding despite divergence: {reconciliation.reason}"
            )
            # Fall through to execution

    # 4. Execute action
    try:
        result = action.execute()
        return {"status": "executed", "result": result}
    except Exception as e:
        # 5. Graceful error handling
        logger.error(f"Action execution failed: {e}")
        return {"status": "failed", "error": str(e)}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No pre-validation | Pre-execution validators | 2020s distributed systems best practice | Prevents acting on stale state |
| Optimistic execution | Optimistic locking with timestamps | 2015+ database patterns | Detects concurrent modifications |
| Retry until success | Circuit breaker pattern | 2014+ (Release It! book) | Prevents cascade failures |
| Sequential IDs | UUID execution IDs | 2010+ distributed systems | Enables idempotency across restarts |
| Manual retry loops | Exponential backoff (tenacity) | 2020+ API client best practice | Avoids thundering herd problem |
| Monolithic validation | Adapter pattern for strategies | 2022+ microservices | Pluggable reconciliation strategies |

**Deprecated/outdated:**
- **Pessimistic locking:** Lock row before reading. Works in databases but not REST APIs (Jira doesn't support locking).
- **Eventual consistency without validation:** Assume Jira state will "eventually" match plan. Too risky for simulator that reads back state.
- **Infinite retries:** Retry forever on failure. Replaced by circuit breaker + max retry limits.
- **Timestamp-only validation (no status check):** Check `updated` field but not status. Misses renames, comment-only changes.

## Open Questions

Things that couldn't be fully resolved:

1. **Should execution IDs persist across simulator restarts?**
   - What we know: In-memory tracker loses IDs on restart, could cause duplicate actions
   - What's unclear: Whether simulator restarts are common enough to warrant persistence
   - Recommendation: Start with in-memory, add persistence to `state.json` if duplicate actions observed

2. **What's the correct staleness threshold (4 ticks, 6 ticks, time-based)?**
   - What we know: 4 ticks = ~3 hours with 45min cadence
   - What's unclear: Whether scenarios should survive overnight (16+ hours between ticks)
   - Recommendation: Use 4-tick threshold, monitor cancellation rate, tune if too aggressive

3. **Should reconciliation strategies be configurable per scenario type?**
   - What we know: Normal flow vs blocker scenarios may need different adaptation logic
   - What's unclear: Whether complexity of per-type strategies outweighs benefit
   - Recommendation: Single strategy engine initially, add polymorphism if patterns emerge

4. **How to handle partial failures (transition succeeds, comment fails)?**
   - What we know: Jira API calls are independent, no transaction support
   - What's unclear: Whether to roll back successful API calls or mark partial success
   - Recommendation: Mark execution as "success" if primary action (transition) succeeds, log warning for secondary failures (comments)

5. **Should circuit breaker state be shared across all actions or per-action-type?**
   - What we know: Read-heavy actions (get_issue) fail differently than writes (transition_issue)
   - What's unclear: Whether fine-grained breakers (per method) prevent helpful fail-fast behavior
   - Recommendation: Two breakers (read, write), monitor for false positives

## Sources

### Primary (HIGH confidence)
- [Idempotency in Distributed Systems](https://blog.algomaster.io/p/idempotency-in-distributed-systems) - Execution ID patterns, 2026
- [Optimistic Locking Guide 2025](https://www.shadecoder.com/topics/optimistic-concurrency-control-a-practical-guide-for-2025) - Timestamp-based conflict detection
- [PyBreaker GitHub](https://github.com/danielfm/pybreaker) - Python circuit breaker implementation
- [Jira REST API Dates Documentation](https://docs.atlassian.com/software/jira/docs/api/7.1.0/com/atlassian/jira/rest/Dates.html) - Timestamp format specification
- [Circuit Breaker Pattern - CodeReliant](https://www.codereliant.io/p/circuit-breaker-pattern) - Graceful degradation patterns

### Secondary (MEDIUM confidence)
- [Idempotency Key Patterns for Exactly-Once API Execution](https://devtechtools.org/en/blog/idempotency-key-patterns-for-exactly-once-api-execution) - Real-world implementation
- [Resilient APIs: Circuit Breakers and Fallback Mechanisms](https://medium.com/@fahimad/resilient-apis-retry-logic-circuit-breakers-and-fallback-mechanisms-cfd37f523f43) - API resilience patterns
- [Understanding Optimistic Locking](https://medium.com/@gaddamnaveen192/understanding-optimistic-locking-a-key-to-handling-data-conflicts-63c086b850d5) - Conflict resolution
- [PyBreaker PyPI](https://pypi.org/project/pybreaker/) - Library documentation

### Tertiary (LOW confidence)
- [Tenacity documentation](https://tenacity.readthedocs.io/) - Retry library (alternative to circuit breaker)
- [Temporal.io Idempotency](https://temporal.io/blog/idempotency-and-durable-execution) - Advanced durable execution (may be overkill)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - PyBreaker is mature, UUID is stdlib, patterns are well-established
- Architecture: HIGH - Pre-execution validation and circuit breakers are proven distributed systems patterns
- Pitfalls: HIGH - Identified by analyzing existing `sync_state_with_jira()` code and researching common reconciliation bugs
- Jira API behavior: MEDIUM - Documented timestamp format, but actual Jira Cloud behavior may vary by instance

**Research date:** 2026-01-28
**Valid until:** 90 days (reconciliation patterns are stable, unlikely to change)

**Key files examined:**
- `src/state/simulation_state.py`: `sync_state_with_jira()` function (lines 227-297)
- `src/services/jira_client.py`: Jira API methods, no existing circuit breaker
- `src/orchestrator/orchestrator.py`: Action execution flow (lines 163-316)
- `src/state/models.py`: ActiveScenario model, no validation tracking fields

**Next steps for planner:**
1. Create `src/reconciliation/` module with validators, reconciler, execution tracker
2. Add `last_validated`, `validation_tick_count` fields to ActiveScenario model
3. Wrap JiraClient with circuit breaker (ResilientJiraClient)
4. Inject PreExecutionValidator into orchestrator before action execution
5. Add staleness detection to end-of-tick cleanup
6. Log tombstone reasons when scenarios are cancelled
7. Add execution ID tracking to prevent duplicate actions
8. Write tests validating reconciliation strategies
