# Phase 6: Tech Debt Cleanup - Research

**Researched:** 2026-01-29
**Domain:** Technical debt remediation, metric mapping, dependency injection
**Confidence:** HIGH

## Summary

Phase 6 addresses two specific tech debt items identified in the v1 milestone audit. These are not architectural deficiencies but implementation gaps where components were built and tested but not fully wired together. The fixes are straightforward: (1) add a simple dictionary key mapping from `metrics["executed"]` to `actions_completed` for dashboard/logging consistency, and (2) pass the globally-initialized `_pathfinding_adapter` instance to the TickExecutor constructor to enable adaptive pathfinding on reconciliation failures.

Both issues have clear locations (main.py lines 695 and 599-604), simple fixes (one line and one parameter respectively), and existing test coverage that validates the individual components. The metric mapping gap is cosmetic (UI/logging only), while the pathfinding adapter wiring is functional but non-critical since basic reconciliation still works via SKIP/CANCEL strategies.

**Primary recommendation:** Implement both fixes as single-line changes in main.py, add integration tests to verify the fixes work end-to-end, and use existing test patterns from Phase 3 and Phase 4 verification. No new libraries or architecture changes needed - this is pure wiring/mapping work using components that already exist and are tested.

## Standard Stack

No new libraries required. Uses existing codebase components:

### Core
| Component | Location | Purpose | Why Standard |
|-----------|----------|---------|--------------|
| TickExecutor | src/orchestrator/tick_executor.py | Action execution with reconciliation | Already built in Phase 3 (254 lines, tested) |
| PathfindingAdapter | src/chaos/pathfinding_adapter.py | Handles RECALCULATE strategy | Already built in Phase 4 (280 lines, 14 tests) |
| main.py | src/main.py | Application entry point and wiring | Contains all global initialization |
| pytest | Testing framework | Integration tests | Used throughout project for verification |

### Supporting
| Component | Version | Purpose | When to Use |
|-----------|---------|---------|-------------|
| Mock/MagicMock | unittest.mock | Test fixtures | For isolating components in integration tests |
| pendulum | 3.1.0+ | Timestamp handling in tests | For creating test scenarios with specific times |

### Alternatives Considered
None - this is wiring work, not new feature development. No architectural alternatives exist.

## Architecture Patterns

### Current State

```
src/main.py (startup_event):
    ├── Initialize global components
    │   ├── _scheduler = Scheduler(store, clock)  [line 275]
    │   ├── _sprint_planner = SprintPlanner(...)   [line 278]
    │   └── _pathfinding_adapter = PathfindingAdapter(...) [line 177]
    │
    └── /trigger endpoint:
        ├── Create TickExecutor
        │   └── NO pathfinding_adapter parameter  [line 599-604]
        │       ❌ GAP: Adapter initialized but not passed
        │
        ├── Execute tick via TickExecutor
        │   └── Returns tick_results with metrics["executed"]
        │
        └── Merge results
            └── NO actions_completed mapping  [after line 695]
                ❌ GAP: Dashboard/logs expect actions_completed
```

### Pattern 1: Metric Key Mapping

**What:** Add dictionary mapping from TickExecutor's `metrics["executed"]` to the expected `actions_completed` key.

**When to use:** When two components use different key names for the same semantic concept.

**Example:**
```python
# src/main.py after line 695 (current location of metric merging)

# Current code (lines 691-703):
results.update(tick_results)  # Merge tick executor results
results["analysis"] = orchestrator_results.get("analysis", {})
results["planning_reasoning"] = orchestrator_results.get("planning_reasoning")
# ... other merges ...
results["chaos"] = chaos_metrics

# Note: actions_completed comes from tick_results, not orchestrator
# since TickExecutor handles execution

# ADD THIS LINE (fix for tech debt):
results["actions_completed"] = results.get("metrics", {}).get("executed", 0)

# Later usage (line 736):
await app.state.log_writer.end_session(
    actions_completed=results.get("actions_completed", 0),  # Now works correctly
    # ...
)
```

**Why it works:**
- TickExecutor populates `results["metrics"]["executed"]` (tick_executor.py line 137)
- Dashboard/logs expect `results["actions_completed"]` (main.py line 736, 744)
- Simple dictionary key extraction bridges the gap
- Zero performance impact, no architectural change

### Pattern 2: Dependency Injection via Constructor

**What:** Pass globally-initialized component instance to constructor instead of leaving parameter as None.

**When to use:** When global component is initialized but consumer's optional parameter defaults to None.

**Example:**
```python
# src/main.py in /trigger endpoint

# Current code (lines 598-604):
tick_executor = TickExecutor(
    scheduler=app.state.scheduler,
    jira_client=logged_jira,
    max_actions_per_tick=4,
    per_ticket_breaker=_per_ticket_breaker,
    # ❌ MISSING: pathfinding_adapter parameter
)

# Fixed code (add one parameter):
tick_executor = TickExecutor(
    scheduler=app.state.scheduler,
    jira_client=logged_jira,
    max_actions_per_tick=4,
    per_ticket_breaker=_per_ticket_breaker,
    pathfinding_adapter=_pathfinding_adapter,  # ✅ ADD THIS LINE
)
```

**Why it works:**
- `_pathfinding_adapter` initialized globally in main.py line 177
- TickExecutor constructor accepts `pathfinding_adapter: Optional[PathfindingAdapter] = None` (tick_executor.py line 42)
- TickExecutor already has logic to use adapter: `if self.pathfinding_adapter:` (tick_executor.py line 212)
- Passing the instance enables pathfinding recalculation on RECALCULATE strategy
- No change to TickExecutor code needed - just wiring

### Anti-Patterns to Avoid

- **Don't create new TickExecutor wrapper**: Tempting to wrap TickExecutor with a "fixed" version, but this duplicates logic and breaks future updates
- **Don't add complex metric transformation logic**: Simple key mapping is sufficient; no need for recursive merging or schema translation
- **Don't instantiate new PathfindingAdapter**: Reuse global instance to maintain shared state (scheduler reference)
- **Don't add runtime configuration**: These are static wiring fixes, not runtime toggles

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Verify metric mapping works | Custom log parsing | Existing LogWriter tests | LogWriter already has test patterns for session metrics (test_log_writer.py) |
| Test pathfinding integration | Mock entire workflow graph | Existing pathfinding tests | PathfindingAdapter already has 14 unit tests covering recalculation logic |
| Integration testing | New test framework | pytest fixtures from Phase 3/4 | Existing fixtures create scheduler, pathfinder, and mock state |

**Key insight:** Phase 3 and Phase 4 verification already have comprehensive test suites. Don't rebuild testing infrastructure - extend existing patterns.

## Common Pitfalls

### Pitfall 1: Forgetting Default Value Fallback

**What goes wrong:** Accessing nested dict keys without `.get()` defaults causes KeyError when metrics dict is empty.

**Why it happens:** TickExecutor might return empty metrics dict on error paths.

**How to avoid:** Always use `.get()` with defaults: `results.get("metrics", {}).get("executed", 0)`

**Warning signs:** KeyError in logs during error scenarios; dashboard crashes on failed ticks.

### Pitfall 2: Circular Import When Moving Code

**What goes wrong:** Temptation to move PathfindingAdapter import to tick_executor.py causes circular dependency.

**Why it happens:** tick_executor.py already imports from chaos module; PathfindingAdapter imports TickExecutor types.

**How to avoid:** Keep initialization in main.py; pass instances via dependency injection, not imports.

**Warning signs:** `ImportError: cannot import name 'PathfindingAdapter' from partially initialized module`

### Pitfall 3: Testing Integration Without End-to-End Flow

**What goes wrong:** Unit tests pass but integration fails because full /trigger flow has untested edge cases.

**Why it happens:** TickExecutor works in isolation; PathfindingAdapter works in isolation; but combined flow through reconciliation has specific ordering requirements.

**How to avoid:** Write integration test that mocks Jira status divergence and verifies pathfinding recalculation happens within /trigger endpoint.

**Warning signs:** Unit tests pass, manual testing works, but production logs show pathfinding never triggers.

### Pitfall 4: Incorrect metrics Dict Access Pattern

**What goes wrong:** Using `results["metrics"]["executed"]` directly instead of nested `.get()` calls.

**Why it happens:** Assuming metrics dict always exists and always has "executed" key.

**How to avoid:** Use defensive dict access: `results.get("metrics", {}).get("executed", 0)`

**Warning signs:** KeyError when TickExecutor returns early due to business hours gate or empty queue.

## Code Examples

Verified patterns from existing codebase:

### Metric Mapping Pattern (from orchestrator.py)

```python
# Source: src/orchestrator/orchestrator.py lines 419-426
# Pattern: Map internal metric names to external API contract

results["actions_completed"] = len(results["actions"])

# Return metrics for observability
return {
    "actions": results["actions"],
    "actions_completed": results["actions_completed"],
    "analysis": results.get("analysis", {}),
    # ...
}
```

This pattern shows the codebase convention: use `actions_completed` in result dicts for consistency.

### Dependency Injection Pattern (from main.py)

```python
# Source: src/main.py lines 598-604
# Pattern: Pass global components to local instances

# Global initialization (startup)
_per_ticket_breaker: Optional[PerTicketCircuitBreaker] = None

# Later usage (in /trigger endpoint)
tick_executor = TickExecutor(
    scheduler=app.state.scheduler,
    jira_client=logged_jira,
    max_actions_per_tick=4,
    per_ticket_breaker=_per_ticket_breaker,  # ✅ Correct pattern
)
```

This shows how other global components are already passed to TickExecutor - just add pathfinding_adapter.

### Integration Test Pattern (from test_pathfinding_adapter.py)

```python
# Source: tests/test_pathfinding_adapter.py lines 53-77
# Pattern: Test component with real scheduler, mock workflow

def test_handle_recalculate_schedules_new_actions(adapter, scheduler, base_time):
    """handle_recalculate should schedule new actions for computed path."""
    # Set current simulation time
    scheduler.clock.current_time = base_time

    # Recalculate path from In Progress to Done
    result = adapter.handle_recalculate(
        ticket_key="PROJ-123",
        current_status="In Progress",
        target_status="done",
        scenario_id="scenario_1",
    )

    # Verify scheduled actions
    assert len(result.actions_scheduled) == 3
    assert result.actions_scheduled[0].action_type == "progress_to_review"
    # ...
```

Use this pattern for integration tests: real components, minimal mocking, assert observable outcomes.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Orchestrator immediate execution | TickExecutor scheduled execution | Phase 3 (2026-01-28) | TickExecutor is now the SOLE execution path |
| Manual workflow adaptation | PathfindingAdapter with WorkflowPathfinder | Phase 4 (2026-01-28) | Automatic recalculation on status divergence |
| Centralized metric keys | Component-specific metric naming | Phase 3 (2026-01-28) | Requires explicit mapping between layers |

**Deprecated/outdated:**
- Orchestrator's `_tick_metrics["executed"]` pattern: Now replaced by TickExecutor's metrics dict, but dashboard still expects old key names
- Direct PathfindingAdapter instantiation per request: Now uses global singleton to share scheduler state

## Open Questions

Things that couldn't be fully resolved:

1. **Should actions_completed be renamed to executed throughout codebase?**
   - What we know: Two components use different names; metric mapping fixes symptoms
   - What's unclear: Whether long-term solution is standardizing all code to one name
   - Recommendation: Fix mapping now (Phase 6), defer standardization to future refactor if needed

2. **Should PathfindingAdapter be per-request or global singleton?**
   - What we know: Currently global; works for single-instance deployment
   - What's unclear: Multi-instance deployment might need request-scoped adapters
   - Recommendation: Keep global for Phase 6; deployment architecture is out of scope

3. **Does AsyncActionExecutor integration affect metric naming?**
   - What we know: Phase 5 tech debt notes AsyncActionExecutor not integrated
   - What's unclear: Whether future async integration changes metric dict structure
   - Recommendation: Fix current mapping; async refactor can adjust if needed

## Sources

### Primary (HIGH confidence)

- **Codebase Analysis:**
  - src/main.py lines 599-604, 691-719 - TickExecutor initialization and result merging
  - src/orchestrator/tick_executor.py lines 37-57, 136-144 - Constructor signature and metrics dict
  - src/chaos/pathfinding_adapter.py lines 61-76, 78-109 - Constructor and reconciliation handling
  - .planning/v1-MILESTONE-AUDIT.md lines 169-183 - Tech debt items with locations and fixes

- **Test Evidence:**
  - tests/test_tick_executor.py lines 49-91 - TickExecutor test patterns
  - tests/test_pathfinding_adapter.py lines 53-99 - PathfindingAdapter test patterns
  - .planning/phases/03-event-scheduler-queue-system/03-VERIFICATION.md lines 56-60 - Metric mapping gap identified
  - .planning/phases/04-adaptive-pathfinding-chaos-injection/04-VERIFICATION.md lines 84-89 - PathfindingAdapter verified

### Secondary (MEDIUM confidence)

- **Phase Research:**
  - .planning/phases/03-event-scheduler-queue-system/03-RESEARCH.md - TickExecutor architecture patterns
  - .planning/phases/04-adaptive-pathfinding-chaos-injection/04-RESEARCH.md - PathfindingAdapter integration patterns

### Tertiary (LOW confidence)

None - all research based on direct codebase analysis and audit documentation.

## Metadata

**Confidence breakdown:**
- Fix locations: HIGH - Audit document specifies exact line numbers and code changes
- Component behavior: HIGH - Verified by existing test suites (58 scheduling tests, 14 pathfinding tests)
- Integration patterns: HIGH - Observed from existing Phase 5 integrations (PerTicketCircuitBreaker follows same pattern)
- Test approach: HIGH - Phase 3 and Phase 4 verification documents show successful patterns

**Research date:** 2026-01-29
**Valid until:** 2026-02-28 (stable - pure implementation fixes, no external dependencies)

**Assumptions verified:**
1. TickExecutor.metrics["executed"] is populated correctly - VERIFIED (tick_executor.py line 137)
2. PathfindingAdapter.handle_reconciliation_result() works when pathfinding_adapter is not None - VERIFIED (14 tests in test_pathfinding_adapter.py)
3. Global _pathfinding_adapter initialized before /trigger endpoint called - VERIFIED (main.py startup_event runs first)
4. LogWriter expects actions_completed key - VERIFIED (log_writer.py line 103, 120)

**Risk assessment:**
- Metric mapping: LOW risk - Simple dict key access, has default fallback
- Pathfinding wiring: LOW risk - Component already tested, constructor signature unchanged
- Regression potential: LOW - Changes are additive (add mapping, add parameter), don't modify existing logic
- Testing complexity: LOW - Extend existing test fixtures, no new test infrastructure needed
