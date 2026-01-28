---
phase: 02-state-reconciliation-validation
plan: 06
subsystem: orchestration
tags: [reconciliation, validation, idempotency, circuit-breaker, staleness]

# Dependency graph
requires: ["02-01", "02-02", "02-03", "02-04", "02-05"]
provides:
  - "Orchestrator with pre-execution validation"
  - "Idempotency checks in action execution"
  - "CANCEL/SKIP/RESCHEDULE strategy application"
  - "Circuit breaker error handling"
  - "Reconciliation metrics in tick results"
  - "Stale scenario cleanup at tick end"
affects: ["03-01", "03-02"]  # Scheduling phases will use reconciliation

# Tech tracking
tech-stack:
  added: ["pytest-asyncio"]
  patterns:
    - "Pre-execution validation before action"
    - "Idempotency via execution ID"
    - "Reconciliation strategy routing"
    - "Metrics aggregation per tick"

# File tracking
key-files:
  modified:
    - src/orchestrator/orchestrator.py
  created:
    - tests/test_orchestrator_reconciliation.py

# Decisions
decisions:
  - key: "validation_before_sprint_check"
    choice: "Run reconciliation validation before sprint membership check"
    reason: "Idempotency and status validation should fail fast before expensive sprint lookup"
  - key: "scenario_lookup_twice"
    choice: "Lookup scenario both in validation block and main execution"
    reason: "Validation needs scenario for mark_validated(), main code needs it for crew dispatch - could optimize but keeps logic clear"
  - key: "execution_id_in_result"
    choice: "Pass execution_id in result dict for recording in caller"
    reason: "Same ID must be used for both check and record to ensure idempotency correctness"

# Metrics
metrics:
  duration: "~6 minutes"
  completed: "2026-01-28"
---

# Phase 2 Plan 6: Orchestrator Reconciliation Integration Summary

**One-liner:** Wired all reconciliation components (validators, reconciler, tracker, circuit breaker, staleness) into orchestrator for pre-execution validation and graceful degradation.

## What Was Built

### 1. Reconciliation Component Initialization
Added imports and initialization in `ScenarioOrchestrator.__init__()`:
- `ResilientJiraClient` wrapping the JiraClient with circuit breaker protection
- `PreExecutionValidator` using resilient_jira for status/assignee validation
- `ReconciliationEngine` for divergence strategy decisions
- `ExecutionTracker` for idempotency with 48-hour cleanup
- `_tick_metrics` dict for per-tick reconciliation metrics

### 2. Pre-Execution Validation in `_execute_action()`
Added comprehensive validation block:
- **Execution ID generation** for idempotency check
- **Duplicate detection** via `is_executed()` - skips with reason "idempotent_skip"
- **Status validation** via `validator.validate_status()`
- **Assignee validation** if action has `expected_assignee`
- **Reconciliation strategy routing**:
  - CANCEL: Complete scenario with tombstone, record in action history
  - SKIP: Mark scenario validated, return skipped=True
  - RESCHEDULE: Defer to next tick, don't record execution
  - PROCEED: Continue to action execution
- **CircuitBreakerError handling**: Reschedule on circuit open

### 3. Metrics Logging and Staleness Cleanup in `run_tick()`
- Reset `_tick_metrics` at tick start
- Increment `executed` counter after successful action
- Record successful executions in tracker (using same execution_id from validation)
- Call `cleanup_stale_scenarios()` at tick end (threshold=4 ticks)
- Log and include `reconciliation_metrics` in tick results

### 4. Helper Method
Added `_get_expected_status_for_action()`:
- Maps action types to expected precondition statuses
- Supports: pick_up_task, progress_to_review, complete_review, qa_approve, qa_reject, inject_blocker, resolve_blocker, acknowledge_rejection, complete_fix, verify_fix

## Key Integration Points

| Component | Orchestrator Method | Purpose |
|-----------|-------------------|---------|
| `PreExecutionValidator` | `_execute_action()` | Validate status/assignee before action |
| `ReconciliationEngine` | `_execute_action()` | Decide CANCEL/SKIP/RESCHEDULE/PROCEED |
| `ExecutionTracker` | `_execute_action()` + `run_tick()` | Generate ID, check, record |
| `ResilientJiraClient` | `validator` | Circuit breaker wrapping for validation calls |
| `cleanup_stale_scenarios` | `run_tick()` | Remove unvalidated scenarios |

## Test Coverage

Created `tests/test_orchestrator_reconciliation.py` with 13 integration tests:

| Test Class | Tests | Coverage |
|------------|-------|----------|
| `TestPreExecutionValidation` | 3 | Status validation triggers skip/cancel, marks validated |
| `TestIdempotency` | 2 | Duplicate prevention, execution_id recording |
| `TestCircuitBreaker` | 1 | Reschedule on circuit open |
| `TestReconciliationMetrics` | 2 | Metrics in results, reset each tick |
| `TestStalenessCleanup` | 2 | Stale removal, non-stale preservation |
| `TestAdaptationStrategies` | 3 | Skip/cancel/reschedule behavior |

All 129 reconciliation-related tests pass.

## Deviations from Plan

None - plan executed exactly as written.

## Requirements Completed

| Requirement | Status | Evidence |
|-------------|--------|----------|
| RECON-01 | Complete | Pre-execution validation checks Jira ticket state |
| RECON-04 | Complete | Idempotency checks using execution IDs |
| RECON-08 | Complete | Circuit breaker + metrics visibility in tick results |

## Success Criteria Verification

1. [x] Orchestrator validates Jira state before each action execution
2. [x] Idempotency check prevents duplicate action execution
3. [x] CANCEL/SKIP/RESCHEDULE strategies work as designed
4. [x] Circuit breaker errors trigger reschedule (not cascade failure)
5. [x] Reconciliation metrics visible in tick results and logs
6. [x] Stale scenarios cleaned up at end of each tick
7. [x] All 129 tests pass

## Phase 2 Completion

This plan completes Phase 2 (State Reconciliation & Validation):
- All 8 RECON requirements are now implemented
- All 6 plans (02-01 through 02-06) are complete
- System validates Jira state before every action
- Graceful adaptation when reality diverges from simulation plan

## Next Phase Readiness

Ready for Phase 3 (Event Scheduling & Pre-scripted Scenarios):
- Reconciliation infrastructure provides reliable execution guarantees
- Idempotency allows safe retries for scheduled actions
- Circuit breaker prevents cascade failures during scheduled execution
- Staleness detection cleans up abandoned scenarios
