# Project Research Summary

**Project:** Real-Time Jira Sprint Simulation with Scenario-Based Event Scheduling
**Domain:** Discrete event simulation with external system reconciliation
**Researched:** 2026-01-27
**Confidence:** HIGH

## Executive Summary

This project is a **cron-triggered discrete event simulator** that generates realistic team behavior in Jira through pre-scripted sprint scenarios with chaos injection. The recommended approach treats it as a state reconciliation system where simulation plans are targets (not contracts) that adapt when external reality diverges. Expert implementations use APScheduler for event scheduling, Pendulum for timezone-safe business hours enforcement, and idempotent action patterns with pre-execution validation.

The core architectural shift needed is replacing immediate reactive execution with **scheduled event queues** that maintain 2-3 sprints of lookahead planning. Each tick advances a virtual clock, queries "what's due now?", validates preconditions against live Jira state, and executes actions via existing Crews. This preserves the proven CrewAI orchestration layer while adding temporal coordination and graceful degradation when reality diverges from script.

The primary risk is **state drift between simulation plan and Jira reality**—when users manually edit tickets, sprints end early, or API errors occur, the simulation can make invalid assumptions. Mitigation requires comprehensive reconciliation (detect divergence), adaptation strategies (recalculate remaining script), and idempotency (safe retry). Secondary risks include DST timezone bugs (use UTC throughout), missed ticks due to long execution (add timeouts and async processing), and chaos parameter tuning (implement dynamic feedback loops). All risks are well-documented in the domain with proven prevention patterns.

## Key Findings

### Recommended Stack

The research identified a mature ecosystem for cron-triggered discrete event simulation with proven production implementations. The stack emphasizes reliability over novelty—using APScheduler v4 (production-ready async scheduler) rather than Celery (overkill for single-process execution), Pendulum v3 (DST-safe timezone handling) over Arrow (known bugs), and workalendar for business day calculations.

**Core technologies:**
- **APScheduler 4.x**: Event scheduling with execution windows and persistence — Industry standard with FastAPI lifespan integration, supports in-memory or persistent job stores for scheduled actions that survive app restarts
- **Pendulum 3.x**: Timezone-aware datetime handling, business hours enforcement — More reliable than Arrow for DST edge cases, automatically timezone-aware with intuitive API for sprint cadence calculations
- **workalendar 18.x**: Business day calculations with holiday support — Comprehensive worldwide holiday library essential for sprint planning and realistic M-F 9-5 activity patterns
- **Pydantic 2.x**: State validation and idempotency tracking — Already in stack, use for modeling ScheduledEvent with execution status, idempotency keys, and reconciliation results
- **tenacity 9.x**: Retry logic with exponential backoff — Wrap Jira API calls for transient failure resilience with configurable retry strategies and circuit breaking

**Supporting patterns:**
- SQLAlchemy 2.x for persistent job store if actions must survive Docker restarts (persisted volume at `data/scheduled_actions.db`)
- python-cqrs for command/event separation if complex multi-step workflow dependencies emerge
- Avoid: Arrow (DST bugs), schedule library (blocking, not production), Celery (unnecessary broker complexity)

### Expected Features

Research revealed that scenario-based simulation with external system reconciliation has clear table stakes (users expect) vs competitive differentiators vs anti-features (seem good but problematic).

**Must have (table stakes):**
- **State Reconciliation** — External system (Jira) is source of truth; local state must sync before each action to detect manual changes
- **Idempotency Checks** — Same event executed multiple times must produce same result; critical for cron systems with no rollback capability
- **Graceful Degradation** — System must operate in degraded mode if Jira API fails, cache last-known state, reconcile when connectivity restores
- **Event Execution Tracking** — Must know which events executed to avoid duplication; use executed flags and idempotency keys
- **Phase/Status Mapping** — Local scenario phases must map to Jira statuses with validation that reality matches expectations

**Should have (competitive):**
- **Chaos Injection** — Planned disruptions (blockers, QA rejections, scope creep) at specific points test resilience; differentiates from basic simulators
- **Adaptive Pathfinding** — When reality diverges, recalculate remaining script using graph search through status transitions rather than failing
- **Planning Horizon (2-3 sprints)** — Pre-script multiple sprints enables coherent cross-sprint narratives like "blocker in Sprint 7 resolved in Sprint 8"
- **State Divergence Metrics** — Track script_fidelity (% events executed vs adapted) for analytics on how often reality deviates
- **Simulation Time Control** — Virtual clock advances faster than wall clock (4 hours/tick) enables "replay 2 weeks in 1 day" demos

**Defer (v2+):**
- **Multi-Team Orchestration** — Cross-team dependency scenarios add complexity without validating core value first
- **Continuous Execution** — Streaming/websocket model contradicts cron-triggered discrete event design; increase tick frequency instead
- **Millisecond Precision Timing** — False accuracy given cron granularity; day-level scheduling is sufficient
- **Perfect Script Adherence** — Reality always diverges; adaptation is feature not bug

### Architecture Approach

The standard architecture for cron-triggered discrete event simulation uses a **time-triggered + event-triggered hybrid**: scheduled timeline combined with reactive reconciliation. This fits the existing orchestrator-crew pattern by adding a scheduling layer that sits between orchestration and execution, providing temporal coordination without disrupting proven patterns.

**Major components:**
1. **Event Scheduler** — Maintains priority queue of scheduled actions sorted by simulation time; provides "what's due now?" query interface using heap operations
2. **Execution Window Validator** — Checks preconditions against live Jira state before executing; returns proceed/abort/reschedule decision with conflict detection
3. **Reconciler** — Compares simulation plan with Jira reality on mismatch; provides adaptation strategies (cancel if already done, recalculate path if diverged, reschedule if timing drift)
4. **Virtual Clock** — Tracks simulation_time independently of wall clock; advances by tick_duration_hours each tick enabling time compression and deterministic replay
5. **Chaos Engine** — Randomly injects unplanned events from catalog (bugs, blockers, scope creep) with weighted selection based on scenario archetype
6. **Planning Horizon Manager** — Maintains rolling 3-7 day lookahead; triggers LLM to extend plan when horizon falls below threshold

**Data flow:** n8n trigger → load state + advance virtual clock → sync with Jira → query scheduler for due events → execution window validates preconditions → on match: execute via crew, on mismatch: reconciler adapts → update Jira via API → schedule follow-up events → save state.

**Integration with existing architecture:** Scheduler sits alongside existing analyzer-planner-crew flow; orchestrator queries scheduler for scripted events and analyzer for reactive opportunities; gradually migrate from analyzer-driven to scheduler-driven execution; existing per-ticket ActiveScenario deprecated in favor of sprint-level scheduled event queues.

### Critical Pitfalls

Research identified 10 documented pitfalls with prevention patterns. The top 5 by impact:

1. **DST Transitions Create Duplicate or Missing Executions** — When clocks "fall back" cron jobs run twice in 1 AM hour; "spring forward" skips 2 AM hour entirely. Prevention: Switch to UTC for all scheduling, never schedule 1-3 AM, use execution ID deduplication with deterministic IDs, add DST transition detection before advancing simulation_day.

2. **Race Conditions Between Jira State Check and Execution** — Simulator syncs Jira state, makes decisions, executes minutes later; gap allows external changes to invalidate assumptions causing failed transitions. Prevention: Read-modify-write with validation (re-fetch ticket status before execution), idempotent actions only (ensure X vs transition to X), optimistic locking via Jira's updated timestamp, graceful degradation on conflict.

3. **Execution Window Too Narrow Causes Missed Ticks** — If tick takes 50+ minutes when n8n expects 45-minute intervals, next run is skipped breaking simulation cadence. Prevention: Aggressive LLM timeouts (15s planning, 10s per action), limit max actions per tick (cap busy mode to 4 not 6), async execution with queue (return 200 immediately), heartbeat monitoring alerts if gap exceeds 1.5x interval.

4. **State Drift from Stale Cached Assumptions** — Local state caches Jira data; external changes (user closes sprint, reassigns tickets) make cache stale causing invalid actions on closed sprints. Prevention: Full reconciliation every tick (re-fetch all sprint issues, cross-check active_scenarios), scenario staleness detection (remove if not validated in 4+ ticks), sprint mismatch detection before execution, tombstone tracking logs why scenarios invalidated.

5. **Over-Adaptation Creates Incoherent Scenarios** — When reconciliation detects mismatches, naïve fix is immediate adaptation creating thrashing where simulator fights user actions. Prevention: Accept reality after threshold (abandon script if 3+ events overridden), graceful degradation to reactive mode, human override detection (respect work-hours changes), scenario confidence score (mark degraded below 60%), immutable past + flexible future (don't undo, only adapt forward).

## Implications for Roadmap

Based on research, suggested phase structure prioritizes foundational time handling and reconciliation before advanced features:

### Phase 1: Time Infrastructure & UTC Migration
**Rationale:** DST bugs and timezone inconsistencies are systemic risks that affect all features; must fix foundational time handling before building scheduling on top of it. Research shows mixing naive/aware datetimes causes subtle bugs in sprint day calculations and business hours enforcement.

**Delivers:**
- All datetimes converted to timezone-aware UTC
- Virtual clock with injectable Clock interface for testing (RealClock vs FakeClock)
- Business hours gate in /trigger endpoint that respects settings.yaml schedule
- DST transition detection and graceful handling

**Addresses:**
- State Reconciliation (table stakes) — requires consistent time comparisons
- Simulation Time Control (competitive) — foundation for virtual clock

**Avoids:**
- Pitfall 1: DST Transitions Create Duplicate Executions
- Pitfall 6: Timezone Conversion Bugs in Multi-System Architecture
- Pitfall 8: Business Hours Enforcement Creates Execution Gaps
- Pitfall 9: Real-Time Clock Makes Tests Non-Deterministic

### Phase 2: State Reconciliation & Validation
**Rationale:** External system is source of truth; local plans must gracefully adapt when reality diverges. Research shows reconciliation is table stakes for cron-triggered systems but current implementation only syncs sprint number/day, not ticket-level state.

**Delivers:**
- Pre-execution validation (check Jira state before action)
- Reconciliation engine (detect divergence, adapt or cancel)
- Tombstone tracking (log why scenarios invalidated by external changes)
- Scenario staleness detection (auto-cleanup orphaned scenarios)
- Idempotency checks (execution IDs prevent duplicate comments)

**Uses:**
- Pydantic models for ReconciliationResult
- Existing JiraClient for state queries

**Implements:**
- Execution Window Validator component
- Reconciler component

**Addresses:**
- State Reconciliation, Idempotency, Graceful Degradation (all table stakes)

**Avoids:**
- Pitfall 2: Race Conditions Between Jira State Check and Execution
- Pitfall 4: State Drift from Stale Cached Assumptions
- Pitfall 5: Over-Adaptation Creates Incoherent Scenarios

### Phase 3: Event Scheduler & Queue System
**Rationale:** Core architectural shift from immediate reactive execution to scheduled event queues; enables lookahead planning and timeline coherence. Research shows APScheduler with priority queue is proven pattern for this use case.

**Delivers:**
- Event Scheduler with priority queue (ScheduledEvent sorted by time)
- Virtual clock integration (simulation_time advances by tick_duration)
- Execution window logic (should_execute_now checks time bounds)
- Schedule persistence in state.json or SQLite
- Scenario Planner enhancement (convert script days to absolute timestamps)

**Uses:**
- APScheduler 4.x for job scheduling
- Pendulum 3.x for time arithmetic
- Existing ScenarioPlanner to populate queue

**Implements:**
- Event Scheduler component
- Virtual Clock component
- Planning Horizon Manager (basic version)

**Addresses:**
- Script-Based Scheduling, Timeline Scheduling (table stakes)
- Planning Horizon (competitive differentiator)

**Avoids:**
- Pitfall 3: Execution Window Too Narrow Causes Missed Ticks (via timeout budgets)
- Pitfall 7: Unbounded Retry Loops (via retry count tracking)

### Phase 4: Adaptive Pathfinding & Chaos Injection
**Rationale:** Differentiation features that make simulation realistic; chaos injection tests resilience, pathfinding gracefully adapts when plans break. Research shows these are competitive advantages but require solid reconciliation foundation.

**Delivers:**
- Chaos Engine with event catalog (blockers, QA rejections, scope creep)
- Weighted random injection based on scenario archetype
- Workflow Pathfinder enhancement (recalculate path on divergence)
- Scenario confidence tracking (script_fidelity metric)
- Mood-based tone adaptation in LLM prompts

**Uses:**
- Existing Workflow Pathfinder for graph search
- LLMService for generating chaos event details
- Reconciler output to trigger pathfinding

**Implements:**
- Chaos Engine component
- Adaptive pathfinding in Reconciler

**Addresses:**
- Chaos Injection, Adaptive Pathfinding (competitive differentiators)
- State Divergence Metrics (analytics)

**Avoids:**
- Pitfall 5: Over-Adaptation (confidence score prevents thrashing)
- Pitfall 10: Chaos Parameter Tuning (basic version; dynamic tuning deferred to Phase 5)

### Phase 5: Performance Optimization & Dynamic Tuning
**Rationale:** After core functionality validated, optimize for scale and realism; dynamic chaos tuning prevents boom-bust cycles, async processing handles high action counts.

**Delivers:**
- Async action execution with asyncio.gather (parallelize independent actions)
- Dynamic chaos probability adjustment (feedback loop from completion rates)
- Lookahead optimization (batch 2-3 events per tick when safe)
- Realistic timing variance (jitter in event execution)
- Performance monitoring (execution time budgets, missed tick alerts)

**Uses:**
- tenacity for retry with exponential backoff
- python-bizdays for sprint day arithmetic
- workalendar for holiday awareness

**Addresses:**
- Realistic Timing Variance, Lookahead Optimization (competitive)

**Avoids:**
- Pitfall 3: Missed Ticks (async returns immediately)
- Pitfall 7: Unbounded Retry Loops (circuit breaker per ticket)
- Pitfall 10: Chaos Parameter Tuning (dynamic adjustment)

### Phase Ordering Rationale

- **Phase 1 first:** Time handling is foundational; DST bugs corrupt sprint day calculations affecting all downstream features. Timezone-aware UTC must be in place before building scheduling system that depends on accurate time comparisons.

- **Phase 2 before Phase 3:** Reconciliation patterns must be established before scheduler adds complexity; need to prove validation and adaptation logic works before queueing hundreds of events. Idempotency is prerequisite for scheduled retries.

- **Phase 3 before Phase 4:** Event scheduler is infrastructure for chaos injection; can't inject random disruptions without queue to hold them. Adaptive pathfinding requires scheduler API to reschedule adapted events.

- **Phase 4 before Phase 5:** Chaos and adaptation are core value; prove these work before optimizing. Dynamic tuning requires baseline chaos implementation to tune against.

- **Phase 5 last:** Performance optimization after functionality validated; premature optimization risks complicating debugging. Dynamic tuning requires multiple sprint runs to establish feedback loop baselines.

### Research Flags

Phases likely needing deeper research during planning:

- **Phase 3 (Event Scheduler):** APScheduler persistence patterns for Docker environments; need to research SQLAlchemy job store setup, volume mounting for `data/scheduled_actions.db`, and atomic state updates. Research APScheduler's lifespan integration with FastAPI.

- **Phase 4 (Adaptive Pathfinding):** Graph search algorithms for Jira workflow transitions; need to research which pathfinding algorithm (Dijkstra, A*, BFS) best fits status transition graphs with cycle handling (some workflows allow back-transitions).

Phases with standard patterns (skip research-phase):

- **Phase 1 (Time Infrastructure):** Well-documented Pendulum patterns, timezone handling is established practice. Plenty of DST gotcha articles with solutions.

- **Phase 2 (State Reconciliation):** Standard read-modify-write with optimistic locking; extensively documented for event-driven architectures with external systems.

- **Phase 5 (Performance Optimization):** Async patterns with asyncio.gather are vanilla Python; retry logic with tenacity is well-documented. Dynamic parameter tuning is experimentation not research.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Official APScheduler docs, Pendulum vs Arrow comparison backed by community consensus, workalendar is mature library. No controversial choices. |
| Features | HIGH | Table stakes validated by discrete event simulation literature, chaos engineering best practices. Anti-features identified from cron scheduling pitfall articles. |
| Architecture | HIGH | Discrete event simulation patterns are textbook CS; time-triggered + event-triggered hybrid extensively documented for real-time systems. Integration strategy preserves existing working components. |
| Pitfalls | HIGH | All 10 pitfalls documented in production systems (DST bugs in RedHat KB, race conditions in microservices blogs, retry patterns in Temporal docs). Prevention patterns proven. |

**Overall confidence:** HIGH

Research drew from official documentation (APScheduler, Pendulum, workalendar), established computer science literature (discrete event simulation), and production experience reports (DST gotchas, reconciliation patterns). No speculative approaches or untested technologies. The recommended stack and patterns have multiple production deployments documented.

### Gaps to Address

Gaps are operational/tuning questions, not fundamental unknowns:

- **APScheduler persistent store sizing:** Research shows how to use SQLAlchemy job store but not optimal settings for 2-3 sprints of queued events (hundreds of jobs). Test under load to determine if in-memory vs persistent is needed.

- **Chaos injection probability tuning:** Research provides framework (weighted selection, archetype multipliers) but optimal probabilities (15% blocker rate vs 10% vs 20%) require experimentation. Phase 5 addresses with dynamic tuning but initial values need A/B testing.

- **Reconciliation adaptation thresholds:** Research says "accept reality after 3+ overrides" but threshold (3 vs 5 vs 2) depends on user intervention patterns. Monitor script_fidelity for first month to calibrate.

- **Jira API rate limiting:** Research notes this as first bottleneck but actual rate limits vary by Atlassian plan. Implement metrics to detect approaching limits; may need caching strategy tuning.

All gaps are tuning parameters discoverable through instrumentation, not architectural unknowns blocking development.

## Sources

### Primary (HIGH confidence)
- [APScheduler GitHub Repository](https://github.com/agronholm/apscheduler) — Event scheduling patterns, FastAPI integration
- [Pendulum Documentation](https://pendulum.eustace.io/) — Timezone-aware datetime handling, DST safety
- [workalendar PyPI](https://pypi.org/project/workalendar/) — Business day calculations
- [Discrete-event simulation - Wikipedia](https://en.wikipedia.org/wiki/Discrete-event_simulation) — Core DES concepts
- [Time-triggered architecture - Wikipedia](https://en.wikipedia.org/wiki/Time-triggered_architecture) — Hybrid time/event triggering
- [RedHat KB: Daylight Savings and Cron](https://access.redhat.com/solutions/477963) — DST pitfalls

### Secondary (MEDIUM confidence)
- [Python Job Scheduling: Methods and Overview in 2026](https://research.aimultiple.com/python-job-scheduling/) — Scheduler comparison
- [Implementing Idempotency Keys in REST APIs](https://zuplo.com/learning-center/implementing-idempotency-keys-in-rest-apis-a-complete-guide) — Idempotency patterns
- [Event-Driven Architecture Done Right](https://www.growin.com/blog/event-driven-architecture-scale-systems-2025/) — Reconciliation strategies
- [Temporal Retry Policies](https://docs.temporal.io/encyclopedia/retry-policies) — Retry and circuit breaker patterns
- [LitmusChaos Documentation](https://litmuschaos.io/) — Chaos engineering scenarios

### Tertiary (LOW confidence)
- Community blog posts on DST cron failures — Anecdotal but consistent patterns
- Medium articles on microservice race conditions — Good examples but not authoritative

---
*Research completed: 2026-01-27*
*Ready for roadmap: yes*
