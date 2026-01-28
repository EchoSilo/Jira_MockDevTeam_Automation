# Phase 1: Time Infrastructure & UTC Migration - Research

**Researched:** 2026-01-28
**Domain:** Python datetime handling, timezone-aware UTC, DST transitions, Clock abstraction
**Confidence:** HIGH

## Summary

Phase 1 migrates from mixed datetime usage (naive `datetime.utcnow()` + stored virtual time) to a consistent timezone-aware UTC approach using **Pendulum** for DST-safe calculations and an injectable **Clock abstraction** for deterministic testing.

The codebase currently uses 40+ instances of `datetime.utcnow()` and `datetime.now(timezone.utc)` scattered across models, agents, orchestrators, and services. The state also stores `simulation_time` and `tick_duration_hours` which are being removed in favor of real-time scheduling with n8n.

**Primary recommendation:** Use Pendulum for all datetime operations, inject Clock interface throughout codebase, enforce business hours at API boundary (FastAPI dependency), and remove virtual time state fields.

## Standard Stack

The established libraries/tools for timezone-aware datetime handling in Python:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pendulum | 3.1.0+ | Timezone-aware datetime with DST handling | Drop-in replacement for datetime with superior DST transition handling, explicit UTC defaults, intuitive API |
| zoneinfo | stdlib (3.9+) | IANA timezone database (fallback) | Python's built-in timezone support, used internally by Pendulum |
| pydantic | 2.6.1+ (already used) | Model validation with datetime serialization | Already in stack, handles Pendulum datetime serialization |

**Why Pendulum over alternatives:**
- **datetime + pytz**: Requires manual `.localize()` and `.normalize()` calls, error-prone DST handling
- **arrow**: Similar features but less actively maintained, smaller community
- **dateutil**: Good parser but weaker DST handling than Pendulum

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-dotenv | 1.0.0+ (already used) | Environment config for timezone settings | Already in use for JIRA_URL, etc. |
| pytest-freezegun | 1.6.0+ | Time-mocking for tests (optional) | Alternative to Clock injection for legacy tests |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Pendulum | datetime + zoneinfo | Lose DST transition safeguards, more verbose API |
| Clock injection | freezegun/time-machine | Monkeypatches system clock globally, harder to reason about |
| FastAPI dependency | Middleware | Business hours check happens after routing, less explicit |

**Installation:**
```bash
pip install pendulum>=3.1.0
# Already have: pydantic>=2.6.1, python-dotenv>=1.0.0
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── time/                # NEW: Time infrastructure module
│   ├── __init__.py
│   ├── clock.py         # Clock protocol + implementations
│   └── business_hours.py # Business hours validation
├── services/
│   └── *.py             # Inject clock into services
├── state/
│   └── models.py        # Remove simulation_time, use injected clock
└── main.py              # Business hours dependency
```

### Pattern 1: Clock Abstraction (Dependency Injection)
**What:** Define a Clock protocol that provides `now()` and `today()` methods, with implementations for production (RealClock) and testing (FakeClock).

**When to use:** Everywhere time is needed—models, services, orchestrators. Enables deterministic testing without monkeypatching.

**Example:**
```python
# src/time/clock.py
from datetime import datetime, date
from typing import Protocol
import pendulum

class Clock(Protocol):
    """Time provider interface for dependency injection."""
    def now(self) -> pendulum.DateTime:
        """Get current datetime in UTC (timezone-aware)."""
        ...

    def today(self) -> date:
        """Get current date in UTC."""
        ...

class RealClock:
    """Production clock using system time."""
    def now(self) -> pendulum.DateTime:
        return pendulum.now("UTC")

    def today(self) -> date:
        return pendulum.now("UTC").date()

class FakeClock:
    """Test clock with controllable time."""
    def __init__(self, frozen_time: pendulum.DateTime):
        self._frozen_time = frozen_time

    def now(self) -> pendulum.DateTime:
        return self._frozen_time

    def today(self) -> date:
        return self._frozen_time.date()

    def advance(self, **kwargs) -> None:
        """Advance time by given delta."""
        self._frozen_time = self._frozen_time.add(**kwargs)
```

**Usage in services:**
```python
class Orchestrator:
    def __init__(self, clock: Clock, ...):
        self.clock = clock

    def run_tick(self):
        now = self.clock.now()  # Always timezone-aware UTC
        # ...
```

### Pattern 2: Business Hours Gate (FastAPI Dependency)
**What:** FastAPI dependency function that validates requests occur during business hours (M-F 9-5 in configured timezone).

**When to use:** Applied to `/trigger` endpoint (and any other time-sensitive endpoints).

**Example:**
```python
# src/time/business_hours.py
from datetime import time
from fastapi import HTTPException, Depends
import pendulum

def get_business_hours_config():
    """Load from settings.yaml."""
    return {
        "timezone": "America/New_York",
        "days": [1, 2, 3, 4, 5],  # Monday=1, Friday=5
        "start_hour": 9,
        "end_hour": 17,
    }

def validate_business_hours(
    clock: Clock = Depends(get_clock),
    config: dict = Depends(get_business_hours_config),
):
    """Dependency that rejects requests outside business hours."""
    now = clock.now()
    local_time = now.in_timezone(config["timezone"])

    # Check day of week (Monday=1, Sunday=7)
    if local_time.day_of_week not in config["days"]:
        raise HTTPException(
            status_code=403,
            detail=f"Simulation runs Monday-Friday only. Today is {local_time.format('dddd')}."
        )

    # Check time range
    if not (config["start_hour"] <= local_time.hour < config["end_hour"]):
        raise HTTPException(
            status_code=403,
            detail=f"Simulation runs {config['start_hour']}:00-{config['end_hour']}:00 only. Current time: {local_time.format('HH:mm')} {config['timezone']}."
        )

# Usage in endpoint
@app.post("/trigger", dependencies=[Depends(validate_business_hours)])
async def trigger_simulation():
    # Only runs if validation passes
    ...
```

### Pattern 3: DST Transition Detection
**What:** Log warnings when DST transitions occur to help diagnose timing anomalies.

**When to use:** At start of each tick, compare current DST status to previous.

**Example:**
```python
# src/time/clock.py (extended)
class DSTAwareRealClock(RealClock):
    """Clock that detects and logs DST transitions."""
    def __init__(self, timezone_name: str = "America/New_York"):
        self._tz = timezone_name
        self._last_dst_status: bool | None = None

    def now(self) -> pendulum.DateTime:
        utc_now = pendulum.now("UTC")
        local_now = utc_now.in_timezone(self._tz)

        # Check DST status
        current_dst = local_now.is_dst()
        if self._last_dst_status is not None and current_dst != self._last_dst_status:
            transition_type = "spring forward" if current_dst else "fall back"
            logger.warning(
                f"DST transition detected ({transition_type}) at {local_now.format('YYYY-MM-DD HH:mm:ss ZZ')}"
            )
        self._last_dst_status = current_dst

        return utc_now
```

### Pattern 4: Sprint Calculations with Pendulum
**What:** Use Pendulum's timezone-aware date arithmetic for sprint start/end calculations.

**When to use:** Sprint planning, calculating sprint day from start date.

**Example:**
```python
# Sprint cadence: Wednesday start, Tuesday end, 7 days
def create_sprint(start_date: pendulum.Date, duration_days: int = 7) -> dict:
    """Create sprint with DST-safe date calculations."""
    # Ensure start is a Wednesday
    if start_date.day_of_week != pendulum.WEDNESDAY:
        raise ValueError(f"Sprint must start on Wednesday, got {start_date.format('dddd')}")

    # Calculate end date (7 days later = next Tuesday)
    end_date = start_date.add(days=duration_days - 1)  # 7 days = Wed-Tue

    return {
        "start_date": start_date.to_iso8601_string(),
        "end_date": end_date.to_iso8601_string(),
        "total_days": duration_days,
    }

def calculate_sprint_day(start_date_str: str, current_time: pendulum.DateTime) -> int:
    """Calculate sprint day (1-indexed) from start date."""
    start_date = pendulum.parse(start_date_str)
    current_date = current_time.date()

    # Calculate days elapsed (1-indexed)
    days_elapsed = (current_date - start_date.date()).days + 1

    # Clamp to valid range
    return max(1, min(days_elapsed, 7))
```

### Anti-Patterns to Avoid
- **Naive datetime mixing:** Never mix naive and aware datetimes. Pendulum enforces awareness, but existing `datetime.utcnow()` creates naive datetimes.
- **Direct system clock calls:** `datetime.now()` or `pendulum.now()` in business logic makes testing hard. Always inject Clock.
- **Storing timezone offsets:** Store UTC times only, convert to local at display boundaries.
- **Manual DST handling:** Don't try to detect DST transitions yourself—let Pendulum handle it via `in_timezone()`.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Business hours calculation | Custom day/hour checker | pandas BusinessHour or custom dependency with Pendulum | Edge cases: holidays, leap years, DST transitions on boundary hours |
| Time freezing for tests | Custom mock datetime | Clock abstraction or pytest-freezegun | State management complexity, global monkeypatching issues |
| DST transition detection | Manual `.dst()` checks | Pendulum's automatic normalization + `is_dst()` | Ambiguous times (1:30 AM occurs twice), non-existent times (2:30 AM skipped) |
| Sprint week calculations | Manual date arithmetic with timedelta | Pendulum's `add(weeks=1)` with timezone | DST transitions mid-sprint can cause off-by-hour errors |
| Timezone conversion | Manual offset calculation | Pendulum's `in_timezone()` | Historical timezone changes, political timezone adjustments |

**Key insight:** Datetime handling is deceptively complex. Even experienced developers miss edge cases like:
- DST transitions create non-existent times (2:30 AM on spring forward)
- Ambiguous times exist twice (1:30 AM on fall back)
- Leap seconds aren't handled by standard libraries
- Timezone rules change politically (Russia abolished DST in 2014)

## Common Pitfalls

### Pitfall 1: Naive datetime.utcnow() in Pydantic Models
**What goes wrong:** `Field(default_factory=datetime.utcnow)` creates naive datetimes, which lose timezone information when serialized.

**Why it happens:** Pydantic doesn't enforce timezone awareness on datetime fields by default.

**How to avoid:**
```python
# BAD
created_at: datetime = Field(default_factory=datetime.utcnow)

# GOOD
created_at: pendulum.DateTime = Field(
    default_factory=lambda: pendulum.now("UTC")
)
```

**Warning signs:**
- JSON serialization drops timezone info (`"2026-01-28T10:00:00"` vs `"2026-01-28T10:00:00+00:00"`)
- Comparisons fail: `naive < aware` raises `TypeError`

### Pitfall 2: DST Transitions Break Sprint Day Calculations
**What goes wrong:** Using naive timedelta arithmetic across DST boundaries causes sprint day to be off by 1.

**Why it happens:** DST transitions add/remove an hour, so `(end - start).days` doesn't equal calendar days.

**How to avoid:**
```python
# BAD (naive timedelta)
days_elapsed = (datetime.now() - start_datetime).days

# GOOD (Pendulum date arithmetic)
days_elapsed = (pendulum.now().date() - start_date).days
```

**Warning signs:**
- Sprint day jumps from 3 to 5 overnight
- End-of-sprint logic triggers a day early/late

### Pitfall 3: Business Hours Check Ignores Timezone
**What goes wrong:** Checking `9 <= now.hour < 17` in UTC rejects valid requests during US business hours.

**Why it happens:** Business hours are defined in local time (e.g., America/New_York), but check happens in UTC.

**How to avoid:**
```python
# BAD (UTC hour check)
if not (9 <= datetime.utcnow().hour < 17):
    raise HTTPException(403, "Outside business hours")

# GOOD (convert to local timezone)
local_time = pendulum.now("UTC").in_timezone("America/New_York")
if not (9 <= local_time.hour < 17):
    raise HTTPException(403, "Outside business hours")
```

**Warning signs:**
- Requests rejected during normal business hours in local timezone
- Different behavior in different geographic regions

### Pitfall 4: Mocking Time Globally Causes Test Pollution
**What goes wrong:** Using `@freeze_time` decorator affects all tests, causing flaky failures when tests run in different orders.

**Why it happens:** Monkeypatching is global—affects all imports, even from other tests.

**How to avoid:**
```python
# BAD (global monkeypatch)
from freezegun import freeze_time

@freeze_time("2026-01-28 10:00:00")
def test_business_hours():
    # Affects ALL datetime.now() calls, including in libraries
    ...

# GOOD (injected Clock)
def test_business_hours():
    clock = FakeClock(pendulum.parse("2026-01-28 10:00:00"))
    orchestrator = Orchestrator(clock=clock, ...)
    # Only orchestrator's time is controlled
    ...
```

**Warning signs:**
- Tests pass individually but fail when run together
- Unrelated tests start failing after adding time-mocking
- External libraries (Jira client, LiteLLM) misbehave

### Pitfall 5: Forgetting to Remove Virtual Time State
**What goes wrong:** Leaving `simulation_time` and `tick_duration_hours` in state models causes confusion—are they used or not?

**Why it happens:** State migration is incomplete, code references old fields.

**How to avoid:**
1. Grep for all references: `simulation_time`, `tick_duration_hours`
2. Replace with `clock.now()` injected via constructor
3. Remove fields from `SimulationState` model
4. Add migration logic to ignore old fields when loading state.json

**Warning signs:**
- Code branches on `if state.simulation_time` but always uses real time
- Tests pass but production uses different time source
- Logs show both virtual and real timestamps

## Code Examples

Verified patterns from research:

### Creating Timezone-Aware Datetimes
```python
# Source: https://pendulum.eustace.io/docs/
import pendulum

# UTC (default)
utc_now = pendulum.now("UTC")
print(utc_now.timezone_name)  # "UTC"

# Specific timezone
ny_now = pendulum.now("America/New_York")
print(ny_now.timezone_name)  # "America/New_York"

# From string with timezone
dt = pendulum.parse("2026-01-28T10:00:00-05:00")

# From date parts (UTC default)
dt = pendulum.datetime(2026, 1, 28, 10, 0, 0)
```

### DST-Safe Date Arithmetic
```python
# Source: https://pendulum.eustace.io/docs/
import pendulum

# Spring forward: March 10, 2026 at 2:00 AM -> 3:00 AM
dt = pendulum.datetime(2026, 3, 10, 1, 59, 59, tz="America/New_York")
one_second_later = dt.add(seconds=1)
# Result: 2026-03-10T03:00:00-04:00 (skips 2:00-3:00)

# Fall back: November 3, 2026 at 2:00 AM -> 1:00 AM
dt = pendulum.datetime(2026, 11, 3, 1, 30, tz="America/New_York", dst_rule=pendulum.PRE_TRANSITION)
print(dt.is_dst())  # True (first occurrence of 1:30 AM)

dt2 = pendulum.datetime(2026, 11, 3, 1, 30, tz="America/New_York", dst_rule=pendulum.POST_TRANSITION)
print(dt2.is_dst())  # False (second occurrence of 1:30 AM)
```

### Clock Injection in Tests
```python
# Source: https://github.com/adriamontoto/clock-pattern
import pytest
import pendulum

class TestOrchestrator:
    def test_business_hours_enforcement(self):
        # Freeze time to Tuesday at 10 AM EST
        clock = FakeClock(
            pendulum.parse("2026-01-28 10:00:00", tz="America/New_York")
        )
        orchestrator = Orchestrator(clock=clock)

        # Should succeed (within business hours)
        result = orchestrator.run_tick()
        assert result.success

    def test_outside_business_hours(self):
        # Freeze time to Saturday
        clock = FakeClock(
            pendulum.parse("2026-01-25 10:00:00", tz="America/New_York")
        )
        orchestrator = Orchestrator(clock=clock)

        # Should raise HTTPException
        with pytest.raises(HTTPException, match="Monday-Friday only"):
            orchestrator.run_tick()
```

### Business Hours Validation
```python
# Source: Custom pattern combining FastAPI dependencies + Pendulum
from fastapi import Depends, HTTPException
import pendulum

def validate_business_hours(
    clock: Clock = Depends(get_clock),
    config: dict = Depends(get_business_hours_config)
):
    """FastAPI dependency for business hours enforcement."""
    now = clock.now()  # UTC timezone-aware
    local = now.in_timezone(config["timezone"])

    # Check day of week (1=Monday, 7=Sunday)
    if local.day_of_week not in config["days"]:
        raise HTTPException(
            status_code=403,
            detail=f"Outside business hours: {local.format('dddd')}"
        )

    # Check hour range
    if not (config["start_hour"] <= local.hour < config["end_hour"]):
        raise HTTPException(
            status_code=403,
            detail=f"Outside business hours: {local.format('HH:mm')} {config['timezone']}"
        )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `datetime.utcnow()` (naive) | `pendulum.now("UTC")` (aware) | Pendulum 1.0 (2016) | Eliminates naive/aware mixing bugs |
| pytz `.localize()` + `.normalize()` | Pendulum auto-normalization | Pendulum 2.0 (2019) | Simpler API, fewer DST bugs |
| freezegun for time mocking | Clock abstraction (DI) | 2020s best practice | Explicit dependencies, no global state |
| zoneinfo (stdlib 3.9+) | Pendulum (wraps zoneinfo) | Python 3.9 (2020) | Stdlib is solid, Pendulum adds convenience |
| Virtual time in state | Real-time with n8n scheduling | This refactor (2026) | Aligns simulation with real-world patterns |

**Deprecated/outdated:**
- **pytz**: Still works but requires manual `.localize()` and `.normalize()` on every operation—error-prone. Pendulum wraps it cleanly.
- **arrow**: Similar to Pendulum but less actively maintained. Last major release was 2019.
- **Virtual time simulation**: Works for abstract simulations but creates unrealistic patterns (no weekends, instant feedback loops). Real-time scheduling with n8n is more realistic.

## Open Questions

Things that couldn't be fully resolved:

1. **Should business hours enforcement be per-team or global?**
   - What we know: Settings.yaml has global `schedule.days` and `schedule.start_hour`/`end_hour`
   - What's unclear: If Alpha team (US East) and Beta team (US West) need different hours
   - Recommendation: Start with global enforcement, add per-team config in Phase 3 if needed

2. **How to handle n8n triggering during DST transition hour?**
   - What we know: DST transitions happen at 2 AM (US), n8n runs M-F 9-5
   - What's unclear: If n8n scheduling could drift during transition (unlikely but possible)
   - Recommendation: Log DST transitions in `/trigger` endpoint, monitor for anomalies

3. **What timezone should sprint start/end dates use in Jira?**
   - What we know: Jira stores dates as ISO 8601 strings with timezone
   - What's unclear: Whether Jira API returns sprint dates in UTC or local timezone
   - Recommendation: Parse with Pendulum (handles both), store in state as UTC

4. **Should FakeClock support auto-advancing time per tick?**
   - What we know: Each tick represents ~45 min of activity, but tests may want to control this
   - What's unclear: Whether tests need to simulate multiple ticks or just freeze at specific moments
   - Recommendation: Start with simple freeze, add `.advance()` method if needed

## Sources

### Primary (HIGH confidence)
- [Pendulum Documentation](https://pendulum.eustace.io/docs/) - Official docs for timezone-aware datetime handling
- [Pendulum GitHub](https://github.com/python-pendulum/pendulum) - v3.1.0 released April 2025
- [Clock Pattern Python Package](https://github.com/adriamontoto/clock-pattern) - Dependency injection pattern for time

### Secondary (MEDIUM confidence)
- [Python Timezone Conversion Guide](https://thelinuxcode.com/python-timezone-conversion-a-practical-production-ready-guide/) - Production-ready patterns (2026)
- [Mastering Time-Dependent Tests in Python 2025](https://medium.com/pythoneers/mastering-time-dependent-tests-in-python-2025-freezegun-time-machine-the-clock-pattern-993b8a38f3c9) - Clock pattern vs monkeypatching
- [Handling Timezone and DST Changes with Python](https://www.hacksoft.io/blog/handling-timezone-and-dst-changes-with-python) - DST pitfalls and solutions
- [FastAPI Scheduling Guide](https://sentry.io/answers/schedule-tasks-with-fastapi/) - APScheduler integration patterns

### Tertiary (LOW confidence)
- [Python BusinessHour documentation](https://pandas.pydata.org/pandas-docs/version/0.25.1/user_guide/timeseries.html) - pandas approach (may be overkill)
- [businesstime library](https://github.com/seatgeek/businesstime) - Third-party business hours calculator (verify before using)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Pendulum is well-established, actively maintained, widely used for production datetime handling
- Architecture: HIGH - Clock abstraction pattern is documented best practice, FastAPI dependency injection is standard
- Pitfalls: HIGH - All pitfalls verified by examining existing codebase (40+ `datetime.utcnow()` calls) and researching common datetime bugs
- Business hours: MEDIUM - No single standard library, requires custom implementation with Pendulum

**Research date:** 2026-01-28
**Valid until:** 60 days (Pendulum is mature, unlikely to have breaking changes)

**Key files examined:**
- `src/main.py`: 9 direct time calls, sprint expiration logic
- `src/state/models.py`: 14 direct time calls in Pydantic default_factory
- `src/state/simulation_state.py`: 3 direct time calls, virtual time logic
- `config/settings.yaml`: Business hours config exists (`schedule.days`, `schedule.start_hour`)

**Next steps for planner:**
1. Create `src/time/` module with Clock protocol and implementations
2. Replace all `datetime.utcnow()` calls with `clock.now()`
3. Add business hours dependency to `/trigger` endpoint
4. Remove `simulation_time` and `tick_duration_hours` from state
5. Write tests using FakeClock to verify DST handling
