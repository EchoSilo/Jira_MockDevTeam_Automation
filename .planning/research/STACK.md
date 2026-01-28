# Stack Research

**Domain:** Real-time event scheduling, action queues, and external system reconciliation
**Researched:** 2026-01-27
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **APScheduler** | 4.x | Event scheduling with execution windows and job persistence | Industry standard for Python job scheduling. Supports cron-style, interval, and date-based triggers. Works perfectly with FastAPI's lifespan manager and cron-triggered execution model. Offers in-memory or persistent storage (SQLAlchemy, Redis, MongoDB) for scheduled actions. |
| **Pendulum** | 3.x | Timezone-aware datetime handling, business hours, sprint cadence | Modern datetime library that's backward-compatible with Python's datetime but adds powerful timezone handling, DST-safe operations, and intuitive API. Automatically timezone-aware (defaults to UTC). Significantly more reliable than Arrow for timezone edge cases. |
| **workalendar** | 18.x | Business day calculations with holiday support | Comprehensive calendar library supporting worldwide holidays. Calculates working days, checks if dates are working days, and handles custom work weeks. Essential for sprint planning and realistic activity patterns. |
| **Pydantic** | 2.x | State validation and idempotency tracking | Already in your stack. Use for modeling scheduled actions, execution state, and reconciliation results. Built-in validation ensures state integrity before/after Jira sync. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **python-bizdays** | 1.0+ | Business day arithmetic for sprint calculations | Use alongside workalendar for sprint day counting, velocity calculations, and realistic team activity patterns (M-F, 9-5). |
| **httpx** | 0.27+ | Async HTTP client for Jira API calls | Already in your stack. Use for non-blocking Jira reconciliation checks. Supports retries and timeouts for resilient API interactions. |
| **tenacity** | 9.x | Retry logic with exponential backoff | Use for Jira API calls during reconciliation. Handles transient failures gracefully with configurable retry strategies and circuit breaking. |
| **chaos_lambda** | 0.4+ (adapted) | Random event injection for chaos testing | Lightweight library with simple decorators for latency/exception injection. Adapt patterns for your simulation (doesn't require AWS Lambda). |
| **python-cqrs** | 1.x | Action queue and event sourcing patterns | Use if you implement command/query separation for scheduled actions. Provides abstractions for commands, events, and sagas (distributed transactions with compensation). |
| **SQLAlchemy** | 2.x | Persistent job store for APScheduler | Use if you need scheduled actions to survive app restarts. APScheduler has native SQLAlchemy integration. Store pending actions in `scheduled_actions` table. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| **pytest-asyncio** | Testing async scheduling logic | Already familiar pattern. Test scheduled action execution, reconciliation, and failure scenarios. |
| **pytest-freezegun** | Time-travel testing | Mock wall-clock time to test sprint transitions, business hours, and scheduled action execution windows. |
| **pytest-mock** | Mock Jira API for reconciliation tests | Test state reconciliation logic without hitting real Jira API. Verify precondition checks and adaptation strategies. |

## Installation

```bash
# Core scheduling and time handling
pip install apscheduler==4.0.0a5  # v4 is production-ready as of 2026
pip install pendulum==3.0.0
pip install workalendar==18.1.0
pip install python-bizdays==1.0.10

# State reconciliation and resilience
pip install tenacity==9.0.0

# Optional: Event sourcing/CQRS (if needed)
pip install python-cqrs==1.0.0

# Optional: Persistent job store (if needed)
pip install sqlalchemy==2.0.25
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| **APScheduler** | Celery Beat | Use Celery if you need distributed workers across multiple machines. For your cron-triggered model (n8n calls FastAPI every 15-45 min), APScheduler is simpler and sufficient. Celery adds complexity (Redis/RabbitMQ broker, worker processes) you don't need. |
| **Pendulum** | Arrow | Never. Arrow has known timezone/DST bugs. Pendulum is more reliable and feature-rich. |
| **Pendulum** | python-dateutil | Use dateutil if you only need RFC parsing. Pendulum is better for timezone operations and business logic (which you need). |
| **workalendar** | pandas.bdate_range | Use pandas if you're already doing heavy data analysis. For sprint/business day logic, workalendar is lighter and more focused. |
| **python-cqrs** | Custom queue | Build custom if you need very specific event sourcing patterns. python-cqrs provides good abstractions for 80% of use cases. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **Arrow** | Known timezone/DST handling bugs. Community recommends against it as of 2025. | **Pendulum** (more reliable, better API) |
| **schedule** library | Blocking scheduler, doesn't integrate well with async FastAPI. Not designed for production. | **APScheduler** (production-ready, async support) |
| **Celery** (for this use case) | Overkill for single-process, cron-triggered execution. Requires broker (Redis/RabbitMQ) and worker processes. Adds operational complexity. | **APScheduler** (simpler, fits your architecture) |
| **Event Store DB** | Full event sourcing database. Heavyweight for your needs. | **SQLAlchemy** with APScheduler's job store (lighter, integrated) |

## Stack Patterns by Variant

**If you need actions to survive app restarts (Docker container restart):**
- Use APScheduler with SQLAlchemy job store
- Store pending actions in `data/scheduled_actions.db` (persisted volume)
- On startup, APScheduler automatically resumes scheduled jobs
- Use idempotency keys (Jira issue key + action type + timestamp) to prevent duplicate execution

**If cron triggers are frequent enough (every 15-45 min) and missing a tick is acceptable:**
- Use in-memory APScheduler (MemoryJobStore)
- Store only high-level scenario state in `data/state.json`
- Each tick recalculates what needs to happen "soon" (next 2-4 hours)
- Simpler, no database needed

**If you need complex scenario orchestration (multi-step workflows with dependencies):**
- Use python-cqrs for command/event separation
- Model each scenario phase as a command (e.g., `StartCodeReview`, `MergeAfterApproval`)
- Store commands in queue, APScheduler executes them at scheduled times
- Event sourcing provides audit trail of all state changes

## Architecture Patterns for Your Use Case

### Pattern 1: Scheduled Action Queue (Recommended)

```python
# Each tick (triggered by n8n):
# 1. Reconcile: Check Jira state for all active scenarios
# 2. Schedule: Plan next actions with execution windows
# 3. Execute: Run actions whose execution window is "now"
# 4. Persist: Save scheduled actions (if using persistent store)

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import pendulum

scheduler = AsyncIOScheduler()

# Schedule action with execution window
def schedule_action(action: str, ticket_key: str, execute_at: pendulum.DateTime):
    """Schedule an action to execute at a specific time."""
    scheduler.add_job(
        func=execute_action,
        trigger='date',
        run_date=execute_at.in_timezone('UTC'),
        args=[action, ticket_key],
        id=f"{ticket_key}_{action}_{execute_at.timestamp()}",
        replace_existing=False,
        misfire_grace_time=3600,  # Allow 1 hour grace period
    )

# Reconcile before execution
async def execute_action(action: str, ticket_key: str):
    """Execute action after checking preconditions in Jira."""
    # 1. Fetch current state from Jira
    issue = jira_client.get_issue(ticket_key)

    # 2. Check preconditions (state reconciliation)
    if not check_preconditions(action, issue):
        logger.info(f"Preconditions not met for {action} on {ticket_key}, adapting...")
        adapt_scenario(ticket_key, issue)
        return

    # 3. Execute action (idempotent)
    result = await perform_action(action, ticket_key)

    # 4. Schedule next action in workflow
    next_action = determine_next_action(ticket_key, result)
    if next_action:
        execute_time = calculate_execution_time(next_action)
        schedule_action(next_action, ticket_key, execute_time)
```

### Pattern 2: Business Hours Enforcement

```python
import pendulum
from workalendar.usa import California

# Initialize calendar with business hours
calendar = California()

def get_next_business_time(target_time: pendulum.DateTime) -> pendulum.DateTime:
    """Ensure action executes during business hours (M-F, 9-5)."""
    # Move to next business day if weekend/holiday
    date = target_time.date()
    while not calendar.is_working_day(date):
        date = date.add(days=1)

    # Clamp to business hours (9 AM - 5 PM)
    dt = pendulum.instance(datetime.combine(date, time(9, 0)))
    if target_time.hour < 9:
        return dt.set(hour=9, minute=0)
    elif target_time.hour >= 17:
        return dt.add(days=1).set(hour=9, minute=0)
    else:
        return target_time
```

### Pattern 3: Chaos Engineering Integration

```python
import random
from functools import wraps

def chaos_injection(failure_rate: float = 0.1):
    """Decorator to randomly inject failures into actions."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Inject random delays (simulates slow Jira API)
            if random.random() < 0.2:
                delay = random.uniform(1, 5)
                logger.info(f"[CHAOS] Injecting {delay:.1f}s latency")
                await asyncio.sleep(delay)

            # Inject random failures (simulates API errors)
            if random.random() < failure_rate:
                logger.warning(f"[CHAOS] Injecting failure for {func.__name__}")
                raise Exception("Chaos-injected failure")

            return await func(*args, **kwargs)
        return wrapper
    return decorator

# Apply to Jira client methods
@chaos_injection(failure_rate=0.05)
async def transition_issue(ticket_key: str, status: str):
    # ... actual Jira API call
    pass
```

### Pattern 4: Idempotency Keys for State Reconciliation

```python
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ScheduledAction(BaseModel):
    """Model for a scheduled action with idempotency tracking."""
    idempotency_key: str  # f"{ticket_key}_{action_type}_{scheduled_time}"
    ticket_key: str
    action_type: str
    scheduled_time: datetime
    executed: bool = False
    execution_result: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

def generate_idempotency_key(ticket_key: str, action_type: str, scheduled_time: datetime) -> str:
    """Generate unique idempotency key for action."""
    timestamp = int(scheduled_time.timestamp())
    return f"{ticket_key}_{action_type}_{timestamp}"

async def execute_with_idempotency(action: ScheduledAction):
    """Execute action with idempotency guarantee."""
    # Check if already executed
    if action.executed:
        logger.info(f"Action {action.idempotency_key} already executed, skipping")
        return action.execution_result

    try:
        # Execute action
        result = await perform_action(action.ticket_key, action.action_type)

        # Mark as executed
        action.executed = True
        action.execution_result = result
        save_action_state(action)

        return result
    except Exception as e:
        # Retry logic
        if action.retry_count < action.max_retries:
            action.retry_count += 1
            # Reschedule with exponential backoff
            delay = 2 ** action.retry_count * 60  # 2, 4, 8 minutes
            reschedule_action(action, delay_seconds=delay)
        else:
            logger.error(f"Action {action.idempotency_key} failed after {action.max_retries} retries")
            action.executed = True  # Mark as executed to prevent infinite retries
            action.execution_result = f"FAILED: {str(e)}"
            save_action_state(action)
```

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| APScheduler 4.x | FastAPI 0.109+ | Use AsyncIOScheduler with FastAPI's lifespan manager. BackgroundScheduler also works for simpler cases. |
| Pendulum 3.x | Python 3.8+ | Drop-in replacement for datetime. Returns Pendulum instances that are also valid datetime objects. |
| workalendar 18.x | Pendulum 3.x | Works seamlessly together. workalendar returns standard datetime.date, easily converted to Pendulum. |
| python-bizdays 1.x | Pendulum 3.x | Independent libraries but complementary. Use workalendar for holidays, bizdays for day arithmetic. |
| APScheduler 4.x | SQLAlchemy 2.x | Native integration. Use SQLAlchemyJobStore for persistent scheduling. |
| tenacity 9.x | httpx 0.27+ | Tenacity decorators work with both sync and async functions. Perfect for wrapping httpx calls. |

## Cron-Triggered Execution Model Considerations

Your architecture (n8n triggers `/trigger` endpoint every 15-45 min) has specific implications:

### ✅ Advantages
- **Simple deployment**: No long-running processes, just FastAPI handling HTTP requests
- **Fault tolerance**: Failed tick doesn't corrupt future ticks
- **Kubernetes-friendly**: Container can restart anytime without losing scheduler state (if using persistent store)
- **Easy debugging**: Each tick is a discrete unit of work with clear start/end

### ⚠️ Constraints
- **No sub-minute precision**: Can't schedule actions more precisely than your cron interval
- **Tick jitter**: Execution time varies by ±30 seconds depending on cron trigger
- **Stateless by default**: Must persist scheduled actions to survive restarts

### 🎯 Recommended Approach

1. **Store scheduled actions in state** (data/state.json or SQLite)
2. **Each tick reads scheduled actions** and executes those whose window is "now"
3. **Use execution windows** (not exact times): "execute between 9:00-9:45 AM"
4. **Reconcile before each execution**: Check Jira state, adapt if preconditions violated
5. **Generate 2-3 sprints ahead**: Always have actions scheduled for next 2-4 weeks
6. **Use chaos injection**: Randomly delay/fail actions to test resilience

Example execution window logic:
```python
def should_execute_now(action: ScheduledAction, current_time: pendulum.DateTime) -> bool:
    """Check if action should execute in current tick."""
    window_start = action.scheduled_time.subtract(minutes=15)
    window_end = action.scheduled_time.add(minutes=30)
    return window_start <= current_time <= window_end
```

## Sprint Planning Integration

### Sprint Calendar Math with Business Days

```python
import pendulum
from workalendar.usa import California
from python_bizdays import Calendar

# Initialize calendars
us_calendar = California()
holidays = [pendulum.parse(str(date)) for date in us_calendar.holidays(2026)]

# Create business days calendar
cal = Calendar(
    holidays=[h.to_date_string() for h in holidays],
    weekdays=['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
)

def calculate_sprint_end(sprint_start: pendulum.DateTime, sprint_length_days: int = 10) -> pendulum.DateTime:
    """Calculate sprint end date using business days."""
    start_date = sprint_start.date()
    end_date = cal.offset(start_date, sprint_length_days)
    return pendulum.instance(datetime.combine(end_date, time(17, 0)))

def get_sprint_day(sprint_start: pendulum.DateTime, current_time: pendulum.DateTime) -> int:
    """Get current day number within sprint (1-indexed, business days only)."""
    start_date = sprint_start.date()
    current_date = current_time.date()
    return cal.bizdays(start_date, current_date) + 1
```

## Sources

### Event Scheduling
- [Python Job Scheduling: Methods and Overview in 2026](https://research.aimultiple.com/python-job-scheduling/)
- [APScheduler GitHub Repository](https://github.com/agronholm/apscheduler)
- [Job Scheduling With Flask, Python APScheduler, Cron And RunMyJobs](https://www.redwood.com/article/job-scheduling-with-flask/)
- [Implementing Background Job Scheduling in FastAPI with APScheduler](https://rajansahu713.medium.com/implementing-background-job-scheduling-in-fastapi-with-apscheduler-6f5fdabf3186)

### State Reconciliation & Idempotency
- [Implementing Idempotency Keys in REST APIs](https://zuplo.com/learning-center/implementing-idempotency-keys-in-rest-apis-a-complete-guide)
- [Idempotency-Key Patterns for Exactly-Once API Execution](https://devtechtools.org/en/blog/idempotency-key-patterns-for-exactly-once-api-execution)
- [Idempotency, state management, and recovery](https://abhinavmanc.medium.com/idempotency-state-management-and-recovery-5b0de78fd857)

### Time & Business Day Handling
- [Python datetimes with Arrow or Pendulum](https://medium.com/@marcnealer/python-datetimes-with-arrow-or-pendulum-6ec7495a9112)
- [Pendulum - Python datetimes made easy](https://pendulum.eustace.io/)
- [workalendar PyPI](https://pypi.org/project/workalendar/)
- [python-bizdays Documentation](https://wilsonfreitas.github.io/python-bizdays/)

### Chaos Engineering
- [awesome-chaos-engineering](https://github.com/dastergon/awesome-chaos-engineering)
- [AWS Lambda Chaos Injection Library](https://github.com/adhorn/aws-lambda-chaos-injection)
- [Chaos Toolkit](https://chaostoolkit.org/)

### Event Sourcing & CQRS
- [python-cqrs PyPI](https://pypi.org/project/python-cqrs/)
- [Python Event Sourcing Library](https://github.com/pyeventsourcing/eventsourcing)
- [Event Sourcing & CQRS with FastAPI and Celery](https://dev.to/markoulis/how-i-learned-to-stop-worrying-and-love-raw-events-event-sourcing-cqrs-with-fastapi-and-celery-477e)

---
*Stack research for: Real-time event scheduling, action queues, and Jira reconciliation*
*Researched: 2026-01-27*
