# Project State: Real-Time Scripted Jira Team Simulator

**Last Updated:** 2026-01-29 02:00 UTC
**Current Phase:** Phase 6 - Tech Debt Cleanup (PENDING)
**Current Plan:** None started (0 of 2)
**Status:** GAP CLOSURE - Addressing tech debt from milestone audit

## Project Reference

**Core Value:** The simulation must operate in Jira's time domain (real calendar time), producing realistic sprint timelines and activity patterns that analytics tools can consume as if observing a real development team.

**Current Focus:** Addressing tech debt identified in milestone audit. Two fixes: metric mapping and PathfindingAdapter wiring.

## Current Position

**Phase:** 6 of 6 - Tech Debt Cleanup (PENDING)
**Plans:** 0 of 2 complete in current phase
**Status:** Gap closure in progress
**Last activity:** 2026-01-29 - Created Phase 6 from gap closure plan
**Progress:** [░░░░░░░░░░░░░░░░░░░░░] 0% (0/2 plans in phase 6)

**Phase Goal:** Address tech debt identified in milestone audit - fix metric mapping for accurate dashboard/logging and wire PathfindingAdapter for full adaptive pathfinding capability.

## Performance Metrics

**Overall Milestone Progress:** 59/59 requirements + 0/2 tech debt fixes

**Phase Breakdown:**
- Phase 1: 7/7 (100%) ✓
- Phase 2: 8/8 (100%) ✓
- Phase 3: 24/24 (100%) ✓
- Phase 4: 14/14 (100%) ✓
- Phase 5: 6/6 (100%) ✓
- Phase 6: 0/2 (0%) ← current

## Accumulated Context

### Key Decisions

| Decision | Rationale | Phase | Date |
|----------|-----------|-------|------|
| 5-phase structure aligned with research | Research suggests optimal grouping by time -> reconciliation -> scheduling -> chaos -> perf | All | 2026-01-27 |
| Replace virtual time with real-time scheduling | Jira operates in real time; virtual time creates unrealistic patterns | 1 | 2026-01-27 |
| Preserve existing agent personalities and LLM system | Agent behavior is sophisticated and working well; problem is orchestration timing | 3 | 2026-01-27 |
| Start fresh rather than migrate existing data | Existing data is based on flawed time model; clean slate is simpler | 1 | 2026-01-27 |
| Use Pendulum for all datetime handling | Pendulum provides timezone-safe arithmetic and DST handling | 1 | 2026-01-28 |
| Clock abstraction via Protocol | Enables dependency injection for testing without monkeypatching | 1 | 2026-01-28 |
| SQLite for action persistence | Simple file-based persistence without external dependencies | 3 | 2026-01-28 |
| TickExecutor as SOLE execution path | Single execution path via skip_execution=True prevents dual execution | 3 | 2026-01-28 |
| asyncio.run() for sync/async bridge | TickExecutor is sync, orchestrator._execute_action is async; bridge required | 3 | 2026-01-28 |
| 80% capacity buffer | Conservative buffer for unknowns in sprint planning | 3 | 2026-01-28 |
| 2-sprint minimum + 14-day lookahead | Dual trigger for planning horizon ensures continuous coverage | 3 | 2026-01-28 |
| Dataclass validation in __post_init__ | Immediate validation on construction for early error detection | 4 | 2026-01-28 |
| Default chaos weights favor blockers/shifts | external_blocker (0.15) and priority_shift (0.12) reflect realistic disruption patterns | 4 | 2026-01-28 |
| Two-stage dice rolling for chaos events | Stage 1: base_event_chance, Stage 2: weighted selection; separates "if event" from "which event" | 4 | 2026-01-28 |
| Seeded random.Random for deterministic testing | Optional seed parameter enables reliable test assertions while preserving production randomness | 4 | 2026-01-28 |
| Weight multipliers for archetype chaos | Archetype-specific multipliers adjust event probabilities (smooth: 0.2-0.5x, blocker_heavy: 2.0x external_blocker) | 4 | 2026-01-28 |
| Event catalog pattern | Central registry provides templates with response actions; enables scenario-aware chaos intensity | 4 | 2026-01-28 |
| Positive adaptations don't hurt fidelity | Early completion treated as success in fidelity calculation; formula: (executed_as_planned + positive_adaptations) / total | 4 | 2026-01-28 |
| Dual-threshold accept reality | Both fidelity < 0.7 AND external_overrides >= 3 required to abandon script; prevents premature abandonment | 4 | 2026-01-28 |
| Direct queue heap access for adaptation | Use _get_pending_actions() to scan queue._heap; get_due_actions() filters by time window | 4 | 2026-01-28 |
| Track postponed actions in actions_inserted | Postponed actions ARE inserted into queue, should appear in insertion list for transparency | 4 | 2026-01-28 |
| Simple replacement agent mapping | Phase 4 focuses on pathfinding logic, not state management; hardcoded role mapping sufficient | 4 | 2026-01-28 |
| Use WorkflowPathfinder for recalculation | Leverages existing pathfinding logic for consistency with workflow topology | 4 | 2026-01-28 |
| Mark all pending actions for ticket as ADAPTED | Prevents conflicting actions after recalculation; maintains action queue consistency | 4 | 2026-01-28 |
| Stagger recalculated action timing | 15-minute intervals for recalculated actions creates realistic action spacing | 4 | 2026-01-28 |
| Chaos injection after tick execution | Chaos phase runs after TickExecutor but before orchestrator planning; ensures chaos can modify queue before new actions planned | 4 | 2026-01-28 |
| ChaosConfig accepts dict or path | load_from_settings accepts either dict or file path for flexible loading from lifespan | 4 | 2026-01-28 |
| Confidence tracking requires sprint scenario | Only calculate confidence when sprint scenario exists; avoids errors on legacy per-ticket scenarios | 4 | 2026-01-28 |
| Per-action timeout (10s default) | Prevents individual slow Jira API calls from blocking tick execution | 5 | 2026-01-29 |
| Global timeout (45s default) | Ensures entire tick completes within budget, preventing overruns | 5 | 2026-01-29 |
| return_exceptions=True for cascade prevention | One failing action doesn't cancel other concurrent actions | 5 | 2026-01-29 |
| ActionResult dataclass structure | Tracks success/failure, execution time, timeout vs exception separately | 5 | 2026-01-29 |
| EMA alpha=0.2 for chaos tuning | 20% new value, 80% previous creates gradual adjustments over 3-5 sprints | 5 | 2026-01-29 |
| Asymmetric thresholds for chaos | 60% low, 85% high favor stability; wide zone prevents constant adjustments | 5 | 2026-01-29 |
| Multiplier bounds 0.2x-2.0x | Prevents extreme probability swings while allowing meaningful adjustment | 5 | 2026-01-29 |
| Adjustment history tracking | Observability for debugging feedback loop; enables future metrics/dashboard | 5 | 2026-01-29 |
| Per-ticket failure threshold of 3 | Default configurable threshold balances quick circuit opening with transient issue tolerance | 5 | 2026-01-29 |
| 24-hour timeout for circuit reset | Prevents permanent blacklisting; allows recovery if external issue resolved | 5 | 2026-01-29 |
| Per-ticket isolation pattern | Unlike global circuit breaker, tracks failures per ticket_key to prevent one broken ticket affecting others | 5 | 2026-01-29 |
| Performance configuration centralized | All Phase 5 components configured from settings.yaml with defaults | 5 | 2026-01-29 |
| Heartbeat at /trigger start | Records tick before processing to accurately capture gaps | 5 | 2026-01-29 |
| Dynamic tuning at sprint transitions | Sprint number change triggers adjustment based on completion rate | 5 | 2026-01-29 |
| Performance metrics exposed | Heartbeat status, chaos multiplier, unhealthy tickets in /trigger response for observability | 5 | 2026-01-29 |

### Completed Phases

**Phase 1: Time Infrastructure & UTC Migration** (Completed 2026-01-28)
- 4 plans executed across 3 waves
- 21/21 verification checks passed
- Key deliverables:
  - Clock abstraction (RealClock/FakeClock) with Pendulum
  - Removed virtual time from SimulationState
  - Migrated 49 datetime calls to pendulum.now("UTC")
  - Business hours gate in /trigger endpoint (M-F 9-5)
  - DST transition detection and logging

**Phase 2: State Reconciliation & Validation** (Completed 2026-01-28)
- 6 plans executed across 3 waves
- 129 reconciliation tests pass
- Key deliverables:
  - PreExecutionValidator for status/assignee/sprint validation
  - OptimisticLockingValidator for timestamp-based conflict detection
  - ExecutionTracker for idempotency with 48-hour cleanup
  - ReconciliationEngine with CANCEL/SKIP/RESCHEDULE/RECALCULATE/PROCEED strategies
  - ResilientJiraClient with circuit breaker protection
  - Staleness detection via validation_tick_count

**Phase 3: Event Scheduler & Queue System** (Completed 2026-01-28)
- 9 plans executed (8 original + 1 gap closure)
- 58 scheduling tests pass
- 23/24 requirements verified (96%)
- Key deliverables:
  - ScheduledAction dataclass with heap-compatible ordering
  - ActionStatus enum (PENDING, READY, COMPLETED, SKIPPED, ADAPTED)
  - ScheduledActionStore with SQLite persistence
  - VirtualClock for simulation time advancement (0.75 hour ticks)
  - ScenarioScheduler converts script days to calendar timestamps
  - Weekend skipping and business hours enforcement
  - Scheduler wrapper combining queue, persistence, VirtualClock
  - TickExecutor with reconciliation integration
  - SprintPlanner orchestrator for full planning flow
  - SimulationState planning fields (planning_horizon, velocity_tracker, action_queue)
  - Full integration: Scheduler, TickExecutor, SprintPlanner wired into /trigger

**Phase 4: Adaptive Pathfinding & Chaos Injection** (Completed 2026-01-28)
- 7 plans executed across 5 waves
- 84 chaos tests pass
- 14/14 requirements verified (100%)
- Key deliverables:
  - ChaosEventType enum with 6 event types
  - RandomEvent dataclass with validation
  - ChaosConfig with dict/path loading and threshold configuration
  - RandomEventGenerator with probability rolling and seeded testing
  - EventCatalog with archetype-aware weight adjustment
  - ConfidenceTracker with dual-threshold accept reality logic
  - ScenarioAdapter with event-specific handlers
  - PathfindingAdapter with RECALCULATE handling
  - Full /trigger integration with chaos metrics
  - Comprehensive integration test suite

**Phase 5: Performance Optimization & Dynamic Tuning** (Completed 2026-01-29)
- 5 plans executed across 3 waves
- 20/20 verification checks passed
- Key deliverables:
  - AsyncActionExecutor with concurrent execution and timeout enforcement
  - DynamicChaosTuner with EMA-based feedback loop for chaos probability adjustment
  - HeartbeatMonitor for tick gap detection with business hours awareness
  - PerTicketCircuitBreaker prevents retry loops on persistently failing tickets
  - Threshold-based chaos adjustment (<60% reduces, >85% increases)
  - Multiplier clamping (0.2x-2.0x) for system stability
  - Per-ticket failure tracking with 24-hour auto-reset
  - Full integration: All components wired into /trigger endpoint
  - Performance configuration in settings.yaml
  - Performance metrics exposed via API response

### Minor Gaps

**Phase 3 minor gap (non-blocking):**
- TickExecutor returns execution count in `metrics["executed"]` but main.py line 540 expects `actions_completed`
- Impact: Dashboard shows 0 actions even when TickExecutor executes successfully
- Severity: Cosmetic - actions execute correctly, only metric display affected

### Open Questions

- None currently

### Known Blockers

- None

### Technical Debt

- Anaconda has Pydantic v1.10.12 (Python 3.11), system Python has v2.11.10 (Python 3.12)
- Planning models use Pydantic v1-compatible Config class for test compatibility
- Some tests use hardcoded dates that may need adjustment
- Added pytest-asyncio dependency for orchestrator tests
- Minor metric field name mismatch (metrics.executed vs actions_completed)

## Session Continuity

**Last Session:** Gap Closure Phase Created (2026-01-29)

**What Happened:**
- Ran `/gsd:plan-milestone-gaps` to review audit results
- Audit found 59/59 requirements satisfied, but 3 tech debt items
- Created Phase 6: Tech Debt Cleanup to address 2 of 3 items
- Deferred AsyncActionExecutor integration (requires async refactor)

**Commits This Session:**
- `7f9157c`: docs(roadmap): add Phase 6 tech debt cleanup for gap closure

**Next Session Should:**
- Run `/gsd:plan-phase 6` to create execution plans for Phase 6
- Execute the 2 plans (metric mapping + PathfindingAdapter wiring)
- Re-audit with `/gsd:audit-milestone` to verify gaps closed
- Then `/gsd:complete-milestone` to archive

**Context for Next Agent:**
- Phase 6 created with 2 plans to write
- Tech debt to fix:
  1. Metric mapping: `metrics["executed"]` → `actions_completed` in main.py
  2. PathfindingAdapter: Wire to TickExecutor for RECALCULATE handling
- AsyncActionExecutor integration deferred (future work)
- Original 59/59 requirements remain complete

---
*State updated: 2026-01-29 01:30 UTC after MILESTONE COMPLETE*
