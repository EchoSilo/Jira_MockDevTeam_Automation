---
phase: 03-event-scheduler-queue-system
plan: 02
subsystem: database
tags: [sqlite, persistence, scheduling, pendulum]

# Dependency graph
requires:
  - phase: 02-state-reconciliation-validation
    provides: Infrastructure for state management and validation
provides:
  - SQLite persistence for scheduled actions
  - ScheduledActionStore with CRUD operations
  - Action status tracking and cleanup
  - Database schema with indexes for performance
affects: [03-03, 03-04, scheduler, queue-system]

# Tech tracking
tech-stack:
  added: [sqlite3, json serialization]
  patterns:
    - Per-operation connection lifecycle (no persistent connections)
    - Pendulum datetime serialization to ISO format
    - Optional field handling with NULL support
    - Upsert pattern (INSERT OR REPLACE)

key-files:
  created:
    - src/scheduling/__init__.py
    - src/scheduling/models.py
    - src/scheduling/persistence.py
    - tests/test_scheduling_persistence.py
  modified: []

key-decisions:
  - "Use SQLite for simple file-based persistence without external dependencies"
  - "Per-operation connection lifecycle for thread safety"
  - "Pendulum datetime serialization to ISO 8601 format"
  - "INSERT OR REPLACE for upsert semantics"
  - "Index on scheduled_time and status for query performance"
  - "48-hour default retention for completed/skipped actions"

patterns-established:
  - "ScheduledAction dataclass with order=True for heap compatibility"
  - "ActionStatus enum for type-safe status values"
  - "Store handles connection lifecycle internally"
  - "JSON serialization for params and result dicts"
  - "Optional fields stored as NULL in database"

# Metrics
duration: 3min
completed: 2026-01-28
---

# Phase 03 Plan 02: Scheduled Action Persistence Summary

**SQLite persistence layer enabling scheduled actions to survive simulator restarts with CRUD operations and automatic cleanup**

## Performance

- **Duration:** 3 minutes
- **Started:** 2026-01-28T08:33:55Z
- **Completed:** 2026-01-28T08:37:29Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- Created ScheduledAction and ActionStatus models with heap-compatible ordering
- Implemented ScheduledActionStore with SQLite backend
- Comprehensive test coverage (10 tests) for all CRUD operations
- Database schema with indexes for scheduled_time and status queries
- Automatic cleanup of old completed/skipped actions

## Task Commits

Each task was committed atomically:

1. **Task 1: Create ScheduledActionStore with SQLite schema** - `3243b6d` (feat)
2. **Task 2: Add persistence tests** - `0282727` (test)
3. **Task 3: Update scheduling __init__.py exports** - (included in Task 1)

## Files Created/Modified

- `src/scheduling/__init__.py` - Package exports with optional import handling
- `src/scheduling/models.py` - ScheduledAction dataclass and ActionStatus enum
- `src/scheduling/persistence.py` - ScheduledActionStore with SQLite operations
- `tests/test_scheduling_persistence.py` - 10 comprehensive persistence tests

## Key Components

### ScheduledAction Model

Dataclass with heap-compatible ordering (sorted by scheduled_time):
- `scheduled_time`: Pendulum DateTime (comparison key)
- `action_id`: Unique identifier (default: uuid4()[:8])
- `action_type`, `agent_id`, `ticket_key`: Action metadata
- `scenario_id`: Optional scenario reference
- `window_minutes`: Execution window (default: 30 minutes)
- `expected_status`, `expected_assignee`: Preconditions
- `status`: ActionStatus enum (PENDING, READY, COMPLETED, SKIPPED, ADAPTED)
- `params`: JSON-serializable action parameters
- `result`: JSON-serializable execution result
- `created_at`, `executed_at`: Timestamps

Methods:
- `is_due(current_time)`: Check if within execution window
- `is_overdue(current_time)`: Check if past execution window
- `mark_completed(result)`: Mark as completed with result
- `mark_skipped(reason)`: Mark as skipped with reason

### ScheduledActionStore

SQLite-backed persistence with CRUD operations:
- `save_action(action)`: Insert or update action (upsert)
- `load_pending_actions()`: Load all pending actions sorted by scheduled_time
- `update_status(action_id, status, result, executed_at)`: Update action status
- `cleanup_old_actions(max_age_hours=48)`: Delete old completed/skipped actions
- `get_action(action_id)`: Retrieve specific action by ID

Database schema:
```sql
CREATE TABLE scheduled_actions (
    action_id TEXT PRIMARY KEY,
    scheduled_time TEXT NOT NULL,
    action_type TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    ticket_key TEXT NOT NULL,
    scenario_id TEXT,
    window_minutes INTEGER DEFAULT 30,
    expected_status TEXT,
    expected_assignee TEXT,
    status TEXT DEFAULT 'pending',
    params TEXT,
    created_at TEXT NOT NULL,
    executed_at TEXT,
    result TEXT
);

CREATE INDEX idx_scheduled_time ON scheduled_actions(scheduled_time);
CREATE INDEX idx_status ON scheduled_actions(status);
```

### Test Coverage

10 tests covering all functionality:
1. **test_save_and_load_action** - Basic save/load operations
2. **test_update_status** - Status updates with result and executed_at
3. **test_load_pending_only** - Filtering by PENDING status
4. **test_cleanup_old_actions** - Cleanup of old completed/skipped actions
5. **test_get_action** - Retrieval by action_id
6. **test_get_action_not_found** - Handle non-existent actions
7. **test_actions_sorted_by_scheduled_time** - Chronological ordering
8. **test_save_action_updates_existing** - Upsert behavior
9. **test_save_action_with_null_fields** - NULL field handling
10. **test_database_persistence_across_instances** - Persistence verification

All tests pass with pytest.

## Decisions Made

1. **Per-operation connection lifecycle**: Open connection for each operation rather than maintaining persistent connection. Ensures thread safety and prevents lock contention.

2. **Pendulum datetime serialization**: Serialize all timestamps to ISO 8601 format for storage. Pendulum.parse() handles deserialization. Maintains timezone information (UTC).

3. **INSERT OR REPLACE for upsert**: SQLite's upsert syntax enables save_action() to both create and update actions with same call.

4. **Indexes on scheduled_time and status**: Performance optimization for common queries (load_pending_actions filters by status and orders by scheduled_time).

5. **48-hour retention for completed actions**: Default cleanup threshold balances audit trail with database size. Configurable via max_age_hours parameter.

6. **Optional import handling in __init__.py**: Try/except blocks allow incremental module development. Other plans can import available components without requiring all modules.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Created ScheduledAction and ActionStatus models**
- **Found during:** Task 1 (ScheduledActionStore implementation)
- **Issue:** Plan 03-02 depends on models from plan 03-01, but 03-01 not yet executed. Persistence layer requires ScheduledAction and ActionStatus to function.
- **Fix:** Created minimal models.py with ScheduledAction dataclass and ActionStatus enum following 03-01 specification. Includes heap-compatible ordering, window calculations, and status methods.
- **Files modified:** src/scheduling/models.py (created)
- **Verification:** Import succeeds, ScheduledAction instances can be created and persisted
- **Committed in:** 3243b6d (part of Task 1 commit)

**2. [Rule 3 - Blocking] Fixed business_hours import in __init__.py**
- **Found during:** Task 1 (Import verification)
- **Issue:** src/scheduling/__init__.py contained import for business_hours.BusinessHoursScheduler which doesn't exist yet, causing ModuleNotFoundError
- **Fix:** Replaced with try/except import blocks for all scheduling modules (models, persistence, priority_queue, business_hours). Allows incremental development.
- **Files modified:** src/scheduling/__init__.py
- **Verification:** from src.scheduling import ScheduledActionStore succeeds
- **Committed in:** 3243b6d (part of Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 blocking)
**Impact on plan:** Both fixes necessary to unblock execution. Creating models from 03-01 spec enables 03-02 to proceed independently (wave 1 plans have no dependencies). Flexible import handling enables incremental module development.

## Issues Encountered

None - all operations completed as planned after auto-fixes.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

**Ready for:**
- Plan 03-03: Business hours scheduling (can use persistence layer)
- Plan 03-04: Scenario script loader (can persist scheduled actions)
- Plan 03-05: Event queue processor (can load pending actions)

**Foundation established:**
- Actions persist across simulator restarts
- Status filtering and chronological ordering work correctly
- Automatic cleanup prevents database growth
- Test coverage ensures reliability

**No blockers** - persistence layer complete and tested.

---
*Phase: 03-event-scheduler-queue-system*
*Completed: 2026-01-28*
