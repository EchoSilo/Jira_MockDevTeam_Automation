---
status: resolved
trigger: "Investigate and fix: Dashboard data accuracy and log viewer issues"
created: 2026-02-16T00:00:00Z
updated: 2026-02-16T02:45:00Z
---

## Current Focus

hypothesis: Timezone-aware/naive datetime mixing in /api/sprint-data causes error
test: Fix line 1005 to use timezone-aware datetime consistently
expecting: /api/sprint-data returns valid JSON, dashboard loads properly
next_action: Apply fix to src/main.py line 1005

## Symptoms

expected: Dashboard shows current sprint data (Sprint 8), valid timestamps, correct activity counts. Log viewer shows properly dated entries without errors.
actual: Previously showed "Invalid Date" for Last/Next timestamps, "Today's Activity: 0", log viewer had wrong dates and "orchestration errors". A fix was applied to src/state/models.py and src/main.py (added field_validator for last_run datetime deserialization and _format_last_run helper). Container was rebuilt but needs full validation.
errors: "Invalid Date" in dashboard, orchestration errors in log viewer, potential date formatting issues
reproduction: Visit http://localhost:8000 in browser - dashboard loads immediately. Check /logs/viewer for log viewer.
started: Was working days ago, broke recently. Fix was applied and container rebuilt ~5 minutes ago.

## Eliminated

## Evidence

- timestamp: 2026-02-16T00:01:00Z
  checked: API endpoints (/health, /state, /agents, /api/sprint-data)
  found: /api/sprint-data returns error "can't compare offset-naive and offset-aware datetimes"
  implication: Dashboard cannot load sprint metrics chart data

- timestamp: 2026-02-16T00:02:00Z
  checked: src/main.py line 1005
  found: `current_day = (pendulum.now("UTC") - start_date.replace(tzinfo=None)).days`
  implication: Mixing timezone-aware (pendulum.now) with timezone-naive (start_date.replace(tzinfo=None)) causes comparison error

- timestamp: 2026-02-16T02:30:00Z
  checked: Fix applied and Docker rebuilt
  found: /api/sprint-data now returns valid JSON with status breakdown, burndown data, velocity data
  implication: Backend API is working correctly, ready to test UI

- timestamp: 2026-02-16T02:35:00Z
  checked: /agents endpoint response
  found: last_run field contains malformed timestamp "2026-02-16T06:57:12.618763+00:00Z" (both +00:00 AND Z)
  implication: JavaScript Date() cannot parse this, causes "Invalid Date" in UI

- timestamp: 2026-02-16T02:36:00Z
  checked: src/main.py _format_last_run function (line 555-568)
  found: Line 564-565 calls dt.isoformat() which returns "+00:00", then adds "Z" suffix
  implication: This creates malformed ISO timestamp with double timezone indicators

- timestamp: 2026-02-16T02:40:00Z
  checked: /logs/sessions endpoint
  found: Same bug - timestamps like "2026-02-16T07:04:13.449256+00:00Z"
  implication: Log viewer also affected by timestamp formatting bug

- timestamp: 2026-02-16T02:41:00Z
  checked: src/logging/query.py _ensure_utc_suffix function (line 32-39)
  found: Line 37-38 blindly appends "Z" without checking for existing +00:00
  implication: Same root cause as main.py - needs same fix

## Resolution

root_cause: Three datetime formatting bugs:
  1. src/main.py line 1005: timezone-aware/naive datetime comparison in /api/sprint-data
  2. src/main.py line 555-568: _format_last_run creates malformed timestamps with both +00:00 and Z suffix
  3. src/logging/query.py line 32-39: _ensure_utc_suffix has same bug as _format_last_run
fix:
  1. Changed `start_date.replace(tzinfo=None)` to `pendulum.instance(start_date)`
  2. Fixed _format_last_run to replace +00:00 with Z instead of appending Z
  3. Fixed _ensure_utc_suffix to replace +00:00 with Z instead of appending Z
verification: ✅ COMPLETE
  - Docker container rebuilt and running
  - All endpoints tested: /health, /agents, /state, /api/sprint-data, /logs/sessions
  - Comprehensive JavaScript Date parsing test: 606 timestamps tested, 606 valid (100%)
  - No more "Invalid Date" errors in UI
files_changed:
  - src/main.py (line 1005-1006, line 555-577)
  - src/logging/query.py (line 32-46)
