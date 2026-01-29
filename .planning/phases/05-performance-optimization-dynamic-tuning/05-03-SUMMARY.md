---
phase: 05-performance-optimization
plan: 03
subsystem: monitoring
tags: [heartbeat, gap-detection, business-hours, pendulum, logging]

# Dependency graph
requires:
  - phase: 01-time-infrastructure
    provides: Pendulum datetime library for timezone-aware time handling
provides:
  - HeartbeatMonitor class for tick gap detection
  - Business hours and weekend awareness
  - 67.5 minute alert threshold (1.5x 45 min expected)
affects: [05-04-integration, observability, alerting]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Business hours detection using pendulum day_of_week"
    - "Expected vs unexpected gap classification"
    - "HeartbeatAlert dataclass for structured gap reporting"

key-files:
  created:
    - src/monitoring/__init__.py
    - src/monitoring/heartbeat.py
    - tests/test_heartbeat.py
  modified: []

key-decisions:
  - "67.5 minute threshold (1.5x 45 min interval) balances sensitivity with false positive avoidance"
  - "Business hours M-F 9-5 configurable via constructor for flexibility"
  - "Expected gaps (weekend, overnight, off-hours) logged as INFO, unexpected as WARNING"
  - "HeartbeatAlert dataclass returns structured data for alerting integration"

patterns-established:
  - "Gap detection: Record each tick, calculate gap from last, check threshold and business context"
  - "Expected gap logic: weekend days, after-hours start, before-hours end, day transitions all expected"
  - "Logging levels: DEBUG for normal, INFO for expected gaps, WARNING for unexpected gaps"

# Metrics
duration: 2min
completed: 2026-01-28
---

# Phase 05 Plan 03: Heartbeat Monitor Summary

**Tick gap detection with 67.5 minute threshold, business hours awareness, and expected gap classification for off-hours and weekend intervals**

## Performance

- **Duration:** 2 min
- **Started:** 2026-01-28T21:15:40Z
- **Completed:** 2026-01-28T21:17:40Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- HeartbeatMonitor class tracks tick timestamps and detects anomalous gaps
- 67.5 minute threshold (1.5x 45 min expected interval) with configurable multiplier
- Business hours awareness prevents false alerts during weekends and off-hours
- 10 comprehensive tests cover gap detection, business hours logic, and requirement verification

## Task Commits

Each task was committed atomically:

1. **Task 1: Create monitoring package with HeartbeatMonitor** - `825eac0` (feat)
2. **Task 2: Add comprehensive tests for heartbeat monitor** - `f5d7bcc` (test)

## Files Created/Modified
- `src/monitoring/__init__.py` - Package initialization, exports HeartbeatMonitor
- `src/monitoring/heartbeat.py` - HeartbeatMonitor and HeartbeatAlert classes
- `tests/test_heartbeat.py` - 10 tests covering gap detection and business hours logic

## Decisions Made

**1. 67.5 minute threshold for alerts**
- Rationale: 1.5x the 45 minute expected interval balances sensitivity (catches real issues) with tolerance (avoids false positives from slight delays)
- Impact: Alerts trigger when gaps exceed ~1 hour, indicating potential scheduler issues

**2. Configurable business hours and days**
- Rationale: Constructor parameters enable flexibility for different operational schedules
- Default: M-F 9am-5pm matches project's business hours gate
- Impact: Reusable across different scheduling patterns

**3. INFO vs WARNING log levels**
- Rationale: Expected gaps (weekend, overnight) are informational; unexpected gaps during business hours are concerning
- Impact: Alerts focus on actionable issues, not routine off-hours gaps

**4. HeartbeatAlert dataclass return**
- Rationale: Structured data enables future integration with alerting systems (Slack, PagerDuty)
- Impact: Monitor is integration-ready, not just logging-only

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - implementation proceeded smoothly with all tests passing.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

**Ready for Plan 04 (Integration):**
- HeartbeatMonitor ready to integrate into main.py /trigger endpoint
- record_tick() method takes pendulum.DateTime, returns Optional[HeartbeatAlert]
- Business hours logic tested and verified
- Alert structure defined for future observability integration

**No blockers or concerns.**

---
*Phase: 05-performance-optimization*
*Completed: 2026-01-28*
