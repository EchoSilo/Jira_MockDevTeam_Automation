# Phase 5: Performance Optimization & Dynamic Tuning - Research

**Researched:** 2026-01-28
**Domain:** Python asyncio, performance optimization, feedback control systems
**Confidence:** HIGH

## Summary

Phase 5 introduces asynchronous action execution with strict timeout enforcement and dynamic chaos probability adjustment based on sprint completion feedback. The primary technical challenges are: (1) bridging synchronous TickExecutor to async orchestrator methods, (2) enforcing per-action timeouts with fallback to other actions, and (3) implementing a feedback loop that adjusts chaos probabilities without destabilizing the simulation.

The standard approach uses Python 3.11+ `asyncio.timeout()` context managers for timeout enforcement, `asyncio.gather()` for concurrent execution with `return_exceptions=True` to prevent cascade failures, and exponential moving average (EMA) for dynamic probability adjustment to ensure smooth, gradual changes.

**Primary recommendation:** Use `asyncio.timeout()` with `asyncio.gather(return_exceptions=True)` for independent action execution. Implement feedback loop with EMA smoothing (alpha=0.2) to adjust chaos probabilities based on rolling 3-sprint completion rate average.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| asyncio | stdlib (3.11+) | Async execution, timeouts, task management | Built-in, modern timeout context managers, official Python async framework |
| pendulum | 2.1+ | Time calculations, interval tracking | Already in use, timezone-aware datetime handling |
| pydantic | 2.0+ | Data validation for feedback metrics | Already in use, validates configuration safely |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pybreaker | 1.0+ | Circuit breaker per ticket | Already in use (Phase 2), prevents retry storms |
| logging | stdlib | Heartbeat monitoring, timeout alerts | Built-in, sufficient for alert generation |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| asyncio.timeout() | asyncio.wait_for() | wait_for() is older pattern, timeout() is cleaner (Python 3.11+) |
| EMA smoothing | PID controller | PID is overkill for single-variable feedback; EMA is simpler and sufficient |
| Built-in logging | External APM (Datadog, Prometheus) | External APM adds dependency; built-in logging meets requirements |

**Installation:**
```bash
# All dependencies already installed from previous phases
pip install pybreaker pendulum pydantic
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── orchestrator/
│   ├── tick_executor.py          # Existing: sync execution wrapper
│   └── async_executor.py         # NEW: async action executor with timeouts
├── chaos/
│   ├── dynamic_tuner.py          # NEW: feedback loop for chaos adjustment
│   └── models.py                 # Existing: ChaosConfig (extend with dynamic fields)
├── planning/
│   └── velocity_tracker.py       # Existing: tracks completion rates
└── monitoring/
    └── heartbeat.py              # NEW: tick gap monitoring
```

### Pattern 1: Async Action Execution with Timeout
**What:** Execute multiple independent actions concurrently with per-action timeouts
**When to use:** When actions are independent and can execute in parallel
**Example:**
```python
# Source: https://docs.python.org/3/library/asyncio-task.html
import asyncio

async def execute_actions_with_timeout(actions: list, max_time: float):
    """Execute actions concurrently with global timeout."""
    async with asyncio.timeout(max_time):
        # return_exceptions=True prevents cascade failures
        results = await asyncio.gather(
            *[execute_single_action(a) for a in actions],
            return_exceptions=True
        )

    # Filter out timeout exceptions, process successful results
    successful = [r for r in results if not isinstance(r, Exception)]
    failed = [r for r in results if isinstance(r, Exception)]
    return successful, failed

async def execute_single_action(action: dict) -> dict:
    """Execute single action with per-action timeout."""
    async with asyncio.timeout(10.0):  # 10s per action
        # Actual execution logic here
        await some_crew_execution(action)
```

### Pattern 2: Sync-to-Async Bridge (asyncio.run)
**What:** Bridge synchronous TickExecutor to async orchestrator methods
**When to use:** When sync code needs to call async code without maintaining event loop
**Example:**
```python
# Source: https://death.andgravity.com/asyncio-bridge
import asyncio

# Sync context (TickExecutor)
def action_executor(action_dict: dict, state) -> dict:
    """Sync wrapper for async execution."""
    # asyncio.run creates transient event loop
    return asyncio.run(orchestrator._execute_action(action_dict, state))

# Note: Can't use asyncio.run if already in async context
# Check if event loop exists before calling
try:
    loop = asyncio.get_running_loop()
    # Already in async context - use await
except RuntimeError:
    # No loop - safe to use asyncio.run()
    result = asyncio.run(async_function())
```

### Pattern 3: Exponential Moving Average (EMA) Feedback Loop
**What:** Smooth adjustment of chaos probabilities based on completion rates
**When to use:** When gradual, non-oscillating adjustment is needed
**Example:**
```python
# Source: https://dayanand-shah.medium.com/exponential-moving-average-and-implementation-with-python-1890d1b880e6
class DynamicTuner:
    def __init__(self, alpha: float = 0.2):
        """
        Args:
            alpha: Smoothing factor (0-1). Lower = more smoothing.
                   0.2 means 20% new data, 80% previous EMA.
        """
        self.alpha = alpha
        self.current_multiplier = 1.0  # Start at 100% of base probabilities

    def adjust_probabilities(self, completion_rate: float, target_rate: float = 0.7):
        """Adjust chaos probability multiplier based on completion rate."""
        # Calculate adjustment factor
        if completion_rate < target_rate:
            # Too much chaos - reduce probabilities
            adjustment = -0.2  # Reduce by 20%
        else:
            # System healthy - can increase chaos slightly
            adjustment = 0.05  # Increase by 5%

        # Apply EMA smoothing
        target_multiplier = self.current_multiplier * (1 + adjustment)
        self.current_multiplier = (
            self.alpha * target_multiplier +
            (1 - self.alpha) * self.current_multiplier
        )

        # Clamp to reasonable bounds (0.2x to 2.0x)
        self.current_multiplier = max(0.2, min(2.0, self.current_multiplier))

        return self.current_multiplier
```

### Pattern 4: Heartbeat Monitoring
**What:** Detect when tick gaps exceed expected interval
**When to use:** Monitor scheduled task execution for anomalies
**Example:**
```python
# Source: https://medium.com/@a.mousavi/understanding-the-heartbeat-pattern-in-distributed-systems-5d2264bbfda6
import logging
import pendulum

class HeartbeatMonitor:
    def __init__(self, expected_interval_minutes: int = 45):
        self.expected_interval = expected_interval_minutes
        self.threshold_multiplier = 1.5  # Alert at 1.5x expected
        self.last_tick_time = None

    def record_tick(self, current_time: pendulum.DateTime):
        """Record tick occurrence and check for gaps."""
        if self.last_tick_time is None:
            self.last_tick_time = current_time
            return

        gap_minutes = (current_time - self.last_tick_time).total_minutes()
        threshold_minutes = self.expected_interval * self.threshold_multiplier

        if gap_minutes > threshold_minutes:
            logging.warning(
                f"Tick gap exceeded threshold: {gap_minutes:.1f} min "
                f"(expected {self.expected_interval} min, "
                f"threshold {threshold_minutes:.1f} min)"
            )

        self.last_tick_time = current_time
```

### Anti-Patterns to Avoid
- **Calling asyncio.run() inside async context:** Creates nested event loops, raises RuntimeError. Use await directly if already in async context.
- **Using asyncio.gather() without return_exceptions=True:** One task failure cancels all tasks. Use `return_exceptions=True` for independent actions.
- **Aggressive feedback adjustments:** Large, immediate changes cause oscillation. Use EMA smoothing for gradual adjustment.
- **Timeout on CPU-bound code:** `asyncio.timeout()` only checks when coroutine is suspended. CPU-bound loops ignore timeouts. Run blocking code in executor.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Circuit breaker per ticket | Custom retry logic with counters | ResilientJiraClient (Phase 2) | Already implemented, handles failure tracking, open/closed state, half-open retry |
| Async timeout enforcement | Manual timeout tracking with time.time() | asyncio.timeout() (stdlib) | Context manager handles cancellation, exception propagation, cleanup |
| Completion rate tracking | Custom sprint metrics calculator | VelocityTracker (Phase 3) | Already tracks committed vs completed points, provides rolling averages |
| EMA calculation | Custom weighted average | pandas.ewm() or simple formula | Proven formula, handles initialization edge cases |

**Key insight:** Phase 2 already solved circuit breaker (ResilientJiraClient), Phase 3 already solved velocity tracking (VelocityTracker). Reuse these instead of duplicating. asyncio.timeout() was added in Python 3.11 specifically to avoid hand-rolling timeout logic.

## Common Pitfalls

### Pitfall 1: Cascade Failures from Single Timeout
**What goes wrong:** One slow action causes all actions in gather() to fail when timeout expires.
**Why it happens:** Without `return_exceptions=True`, asyncio.gather raises first exception and cancels all tasks.
**How to avoid:** Always use `asyncio.gather(..., return_exceptions=True)` for independent actions. Filter results afterward to separate successful from failed.
**Warning signs:** Logs show multiple actions marked "skipped" with same timestamp when only one action actually timed out.

### Pitfall 2: asyncio.run() Inside Async Context
**What goes wrong:** `RuntimeError: asyncio.run() cannot be called from a running event loop`
**Why it happens:** TickExecutor is sync, but if called from async context (tests, future refactor), asyncio.run() fails.
**How to avoid:** Check for running loop before using asyncio.run():
```python
try:
    asyncio.get_running_loop()
    # Already in async - use await
    result = await async_function()
except RuntimeError:
    # No loop - safe to use asyncio.run
    result = asyncio.run(async_function())
```
**Warning signs:** Tests fail with RuntimeError but production works. Tests often run in async context (pytest-asyncio).

### Pitfall 3: Timeout Doesn't Cancel CPU-Bound Code
**What goes wrong:** Action times out but keeps running, consuming resources.
**Why it happens:** asyncio timeouts only check when coroutine awaits. Pure computation ignores timeouts.
**How to avoid:**
1. Ensure LLM calls and Jira API calls use await (they do - both are async)
2. Don't add CPU-intensive loops in action execution
3. If needed, run CPU work in executor: `await loop.run_in_executor(None, cpu_bound_func)`
**Warning signs:** Timeout logs appear but CPU usage stays high. Action marked "timed out" but Jira shows it completed later.

### Pitfall 4: Feedback Loop Oscillation
**What goes wrong:** Chaos probabilities swing wildly between high and low, causing unstable simulation.
**Why it happens:** Too aggressive adjustment (e.g., 50% reduction/increase) without smoothing causes overcorrection.
**How to avoid:**
1. Use EMA smoothing (alpha=0.2 or lower)
2. Cap adjustments (max -20% reduction, max +5% increase per sprint)
3. Clamp multiplier to reasonable bounds (0.2x to 2.0x)
4. Use rolling 3-sprint average, not single sprint
**Warning signs:** Chaos event frequency oscillates dramatically sprint-to-sprint. Completion rates swing from 40% to 90% and back.

### Pitfall 5: Circuit Breaker Open = Action Lost Forever
**What goes wrong:** When circuit breaker is open, action gets marked "skipped" and never retried.
**Why it happens:** TickExecutor marks circuit breaker failures as skipped with no retry mechanism.
**How to avoid:** Don't mark as skipped when circuit breaker is open. Return without marking, so action stays in "pending" state and retries next tick. Only implemented in current code - verify this behavior is preserved.
**Warning signs:** Actions accumulate in "pending" state with no execution. Logs show repeated circuit_breaker_open messages for same action.

### Pitfall 6: Heartbeat False Positives
**What goes wrong:** Alerts fire for normal weekend gaps or planned downtime.
**Why it happens:** Static threshold (1.5x interval) doesn't account for schedule (M-F, 9-5).
**How to avoid:**
1. Check business hours before alerting (weekend gaps are expected)
2. Use 1.5x for weekday checks, skip alerting on weekends
3. Log all gaps but only alert on unexpected ones
**Warning signs:** Alerts every Monday morning for "67-hour gap" (Friday 5pm to Monday 9am).

## Code Examples

Verified patterns from official sources:

### Async Execution with Timeout (Python 3.11+)
```python
# Source: https://docs.python.org/3/library/asyncio-task.html
import asyncio

async def execute_actions_async(
    actions: list[dict],
    action_executor_async: Callable,
    max_total_time: float = 45.0,
    max_action_time: float = 10.0
) -> tuple[list, list]:
    """
    Execute multiple actions concurrently with timeouts.

    Args:
        actions: List of action dicts
        action_executor_async: Async function to execute single action
        max_total_time: Total timeout for all actions (45s)
        max_action_time: Per-action timeout (10s)

    Returns:
        (successful_results, failed_results)
    """
    async def execute_with_action_timeout(action: dict):
        """Wrap single action with its own timeout."""
        try:
            async with asyncio.timeout(max_action_time):
                return await action_executor_async(action)
        except asyncio.TimeoutError:
            return {"error": "action_timeout", "action": action}

    # Apply global timeout to entire batch
    try:
        async with asyncio.timeout(max_total_time):
            # return_exceptions=True prevents cascade failures
            results = await asyncio.gather(
                *[execute_with_action_timeout(a) for a in actions],
                return_exceptions=True
            )
    except asyncio.TimeoutError:
        # Global timeout expired - some actions may not have started
        return [], [{"error": "global_timeout"}]

    # Separate successful from failed
    successful = [r for r in results if not isinstance(r, Exception) and not r.get("error")]
    failed = [r for r in results if isinstance(r, Exception) or r.get("error")]

    return successful, failed
```

### EMA-Based Dynamic Tuner
```python
# Source: https://dayanand-shah.medium.com/exponential-moving-average-and-implementation-with-python-1890d1b880e6
from pydantic import BaseModel, Field

class DynamicChaostuner(BaseModel):
    """Adjust chaos probabilities based on sprint completion rates."""

    alpha: float = Field(default=0.2, ge=0.0, le=1.0)
    target_completion_rate: float = Field(default=0.7, ge=0.0, le=1.0)
    min_multiplier: float = Field(default=0.2, ge=0.1, le=1.0)
    max_multiplier: float = Field(default=2.0, ge=1.0, le=5.0)
    current_multiplier: float = Field(default=1.0)

    def adjust(self, completion_rate: float) -> float:
        """
        Adjust chaos probability multiplier based on completion rate.

        Args:
            completion_rate: Sprint completion rate (0.0-1.0)

        Returns:
            New multiplier for chaos probabilities
        """
        # Determine adjustment direction
        if completion_rate < self.target_completion_rate:
            # Too much chaos - reduce probabilities by 20%
            adjustment_factor = -0.2
        elif completion_rate > 0.85:
            # System very healthy - can increase chaos slightly
            adjustment_factor = 0.05
        else:
            # In acceptable range - no change
            adjustment_factor = 0.0

        # Calculate target multiplier
        target_multiplier = self.current_multiplier * (1 + adjustment_factor)

        # Apply EMA smoothing
        # alpha=0.2: 20% new value, 80% previous value
        self.current_multiplier = (
            self.alpha * target_multiplier +
            (1 - self.alpha) * self.current_multiplier
        )

        # Clamp to bounds
        self.current_multiplier = max(
            self.min_multiplier,
            min(self.max_multiplier, self.current_multiplier)
        )

        return self.current_multiplier

    def get_adjusted_probabilities(self, base_probabilities: dict[str, float]) -> dict[str, float]:
        """Apply current multiplier to base probabilities."""
        return {
            event_type: prob * self.current_multiplier
            for event_type, prob in base_probabilities.items()
        }
```

### Heartbeat Monitor with Business Hours Check
```python
# Source: https://medium.com/@a.mousavi/understanding-the-heartbeat-pattern-in-distributed-systems-5d2264bbfda6
import logging
import pendulum
from typing import Optional

logger = logging.getLogger(__name__)

class HeartbeatMonitor:
    """Monitor tick intervals and alert on gaps."""

    def __init__(
        self,
        expected_interval_minutes: int = 45,
        threshold_multiplier: float = 1.5,
        business_hours: tuple[int, int] = (9, 17),
        business_days: list[int] = [1, 2, 3, 4, 5]  # Mon-Fri
    ):
        self.expected_interval = expected_interval_minutes
        self.threshold_multiplier = threshold_multiplier
        self.business_hours = business_hours
        self.business_days = business_days
        self.last_tick_time: Optional[pendulum.DateTime] = None

    def record_tick(self, current_time: pendulum.DateTime) -> Optional[dict]:
        """
        Record tick and check for anomalous gaps.

        Returns:
            Alert dict if gap exceeded threshold, None otherwise
        """
        if self.last_tick_time is None:
            self.last_tick_time = current_time
            return None

        gap_minutes = (current_time - self.last_tick_time).total_minutes()
        threshold_minutes = self.expected_interval * self.threshold_multiplier

        alert = None
        if gap_minutes > threshold_minutes:
            # Check if gap spans weekend or off-hours
            if self._is_expected_gap(self.last_tick_time, current_time):
                logger.info(
                    f"Expected gap (off-hours): {gap_minutes:.1f} min "
                    f"({self.last_tick_time} to {current_time})"
                )
            else:
                # Unexpected gap during business hours
                logger.warning(
                    f"HEARTBEAT ALERT: Tick gap exceeded threshold: {gap_minutes:.1f} min "
                    f"(expected {self.expected_interval} min, threshold {threshold_minutes:.1f} min)"
                )
                alert = {
                    "type": "heartbeat_gap",
                    "gap_minutes": gap_minutes,
                    "threshold_minutes": threshold_minutes,
                    "last_tick": self.last_tick_time.isoformat(),
                    "current_tick": current_time.isoformat(),
                }

        self.last_tick_time = current_time
        return alert

    def _is_expected_gap(self, start: pendulum.DateTime, end: pendulum.DateTime) -> bool:
        """Check if gap is expected (crosses weekend or off-hours)."""
        # If gap spans different days, check for weekend
        if start.day_of_week not in self.business_days or end.day_of_week not in self.business_days:
            return True

        # If gap spans different days and crosses end-of-day
        if start.date() != end.date():
            start_hour, end_hour = self.business_hours
            if start.hour >= end_hour or end.hour < start_hour:
                return True

        return False
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| asyncio.wait_for(gather(...)) | asyncio.timeout() context manager | Python 3.11 (Oct 2022) | Cleaner syntax, automatic cleanup, better exception handling |
| Manual timeout tracking | asyncio.timeout_at() | Python 3.11 (Oct 2022) | Absolute deadline timeouts, no drift accumulation |
| TaskGroup (Python 3.11+) | asyncio.gather() for our use case | Python 3.11 (Oct 2022) | TaskGroup better for dependent tasks; gather better for independent actions with return_exceptions=True |
| PID controllers for feedback | EMA smoothing for simple cases | Ongoing | PID overkill for single-variable adjustment; EMA simpler and sufficient |

**Deprecated/outdated:**
- `asyncio.wait_for(asyncio.gather(...))`: Still works but `asyncio.timeout()` is cleaner (Python 3.11+)
- `loop = asyncio.get_event_loop()`: Deprecated in favor of `asyncio.get_running_loop()` or `asyncio.run()`
- Nested `try/except` for timeout handling: `asyncio.timeout()` context manager handles this automatically

## Open Questions

Things that couldn't be fully resolved:

1. **Should timeout budgets be per-action-type or uniform?**
   - What we know: Requirements specify 10s per action uniformly
   - What's unclear: Some actions (LLM story generation) may legitimately need more time than others (simple transitions)
   - Recommendation: Start with uniform 10s, add per-action-type budgets in future if needed. Monitor timeout frequency by action type.

2. **Should chaos adjustment happen every sprint or every tick?**
   - What we know: Requirements say "based on sprint completion feedback"
   - What's unclear: Adjustment frequency - end of sprint only, or gradual during sprint?
   - Recommendation: Adjust at sprint end only (every ~7 days). Avoids mid-sprint disruption, allows full sprint cycle to complete before measuring impact.

3. **How to handle partial tick execution (some actions succeed, some timeout)?**
   - What we know: `return_exceptions=True` allows filtering successful vs failed
   - What's unclear: Should we retry timed-out actions next tick, or mark them skipped?
   - Recommendation: Mark as skipped (don't retry). Retry logic would require tracking attempt count, risk retry storms. Better to accept some actions fail and continue.

4. **Should heartbeat monitor send external alerts (email, Slack) or just log?**
   - What we know: Requirements specify "heartbeat monitoring alerts if tick gap exceeds 1.5x"
   - What's unclear: Alert destination - logs only, or external notification?
   - Recommendation: Start with logging only. External alerting requires configuration (email, Slack webhook) not in requirements. Logs sufficient for MVP.

## Sources

### Primary (HIGH confidence)
- [Python 3.14.2 asyncio Documentation](https://docs.python.org/3/library/asyncio-task.html) - Official Python asyncio patterns
- [Super Fast Python - Asyncio Timeout Best Practices](https://superfastpython.com/asyncio-timeout-best-practices/) - Modern timeout patterns
- [Hynek Schlawack - Waiting in asyncio](https://hynek.me/articles/waiting-in-asyncio/) - Authoritative asyncio guide
- [death and gravity - Running async from sync](https://death.andgravity.com/asyncio-bridge) - asyncio.run patterns

### Secondary (MEDIUM confidence)
- [PyBreaker GitHub](https://github.com/danielfm/pybreaker) - Circuit breaker patterns (verified with existing codebase)
- [Medium - Understanding Heartbeat Pattern](https://medium.com/@a.mousavi/understanding-the-heartbeat-pattern-in-distributed-systems-5d2264bbfda6) - Distributed systems monitoring
- [Medium - EMA Implementation](https://dayanand-shah.medium.com/exponential-moving-average-and-implementation-with-python-1890d1b880e6) - EMA formula and patterns
- [FastAPI Timeout Patterns](https://sentry.io/answers/make-long-running-tasks-time-out-in-fastapi/) - Async endpoint timeout enforcement

### Tertiary (LOW confidence)
- [LiveTune Framework](https://arxiv.org/html/2311.17279v2) - Academic research on dynamic parameter tuning (interesting but not directly applicable)
- [Simple-PID PyPI](https://pypi.org/project/simple-pid/) - PID controllers (mentioned for comparison, not recommended for this use case)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - asyncio is stdlib, patterns well-documented, existing code uses pendulum/pydantic
- Architecture: HIGH - Official Python docs, multiple authoritative sources agree on patterns
- Pitfalls: MEDIUM - Based on WebSearch verification + asyncio best practices, not all tested in this codebase yet
- EMA/Feedback loop: MEDIUM - Pattern proven in other domains (trading, ML), not specifically for chaos injection
- Heartbeat monitoring: MEDIUM - Pattern well-established in distributed systems, implementation straightforward

**Research date:** 2026-01-28
**Valid until:** 2026-02-27 (30 days - stable domain, Python 3.11+ patterns unlikely to change)

## Key Takeaways for Planning

1. **Async execution is straightforward:** Python 3.11+ `asyncio.timeout()` + `asyncio.gather(return_exceptions=True)` handles concurrent execution with timeouts. Don't overthink it.

2. **Reuse existing infrastructure:** ResilientJiraClient (circuit breaker), VelocityTracker (completion rates) already exist. Don't rebuild.

3. **EMA smoothing prevents oscillation:** Use alpha=0.2 for gradual adjustment. Cap changes (-20% max reduction, +5% max increase). Clamp multiplier (0.2x to 2.0x).

4. **asyncio.run() bridge is simple:** Check for running loop first to avoid RuntimeError. Use in TickExecutor callback to bridge sync to async.

5. **Heartbeat monitoring needs business hours logic:** 1.5x threshold works, but skip weekend gaps to avoid false positives.

6. **Independent actions need return_exceptions=True:** Critical for preventing cascade failures. One timeout shouldn't kill all actions.
