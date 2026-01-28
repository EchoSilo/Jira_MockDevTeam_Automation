# Feature Research: Real-Time Simulation Systems

**Domain:** Real-time scenario-based simulation with external system reconciliation
**Researched:** 2026-01-27
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **State Reconciliation** | External system is source of truth; local state must sync | MEDIUM | Cron-triggered systems MUST reconcile before each action. Use patterns: transactional outbox, idempotency checks. |
| **Script-Based Scheduling** | Scenario-driven systems need pre-planned event sequences | LOW | Already implemented (SprintScenario with ScriptDay events). Store event timing, not execution time. |
| **Graceful Degradation** | External system may be unavailable | MEDIUM | Cache last-known state from Jira; operate in degraded mode if API fails. Reconcile when connectivity restored. |
| **Event Execution Tracking** | Must know which events executed to avoid duplication | LOW | Already implemented (event.executed flag, events_executed list). |
| **Phase/Status Mapping** | Local phases must map to external system states | LOW | Already implemented (ScenarioPhase → Jira Status). Reconciliation ensures consistency. |
| **Timeline Scheduling** | Events scheduled by day/time for multi-day scenarios | LOW | Already implemented (ScriptEvent.day, current_day tracking). Cron advances time. |
| **Rollback-Free Design** | Cron scheduling = no rollback, must be conservative | LOW | Already enforced: no optimistic execution, check-before-act pattern. |
| **Idempotency** | Same event executed multiple times = same result | MEDIUM | Critical for cron systems. Check "already executed" before modifying state. |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Chaos Injection** | Realistic disruptions test system resilience | MEDIUM | Inject blockers, scope creep, QA rejections at planned points. Already designed (EventType: BLOCKER, QA_REJECTION, SCOPE_CREEP). |
| **Adaptive Pathfinding** | Recalculate remaining script when reality diverges | HIGH | If Jira state != expected, pathfinder computes new action sequence to reach goal. Uses graph search through status transitions. |
| **Planning Horizon (2-3 sprints)** | Pre-script multiple sprints for coherent narratives | MEDIUM | Plan Sprint N, N+1, N+2 scenarios ahead. Enables cross-sprint storylines (e.g., "blocker in Sprint 7 resolved in Sprint 8"). |
| **Mood-Based Tone Adaptation** | Comments reflect team stress/energy | LOW | MoodState (energized, stressed, frustrated) influences LLM comment generation. Already modeled. |
| **Scenario Archetypes** | Predefined narrative patterns (smooth, blocker-heavy, crunch) | LOW | Already implemented (ScenarioArchetype enum). LLM generates archetype-specific events. |
| **Realistic Timing Variance** | Events don't execute exactly on schedule | MEDIUM | Add jitter: event scheduled Day 3 might execute Day 2-4 based on agent availability, workload. More realistic than rigid script. |
| **Lookahead Optimization** | Know future events to batch actions efficiently | MEDIUM | If Day 3 has 5 events, execute 2-3 per tick instead of 1. Reduces cron invocations. |
| **State Divergence Metrics** | Measure how far reality drifted from script | LOW | Track script_fidelity: % of scripted events executed vs adaptations made. Analytics gold. |
| **Multi-Team Orchestration** | Coordinate scenarios across Team Alpha and Team Beta | MEDIUM | Sprint scenarios can include cross-team dependencies. Already modeled (DEPENDENCY event type). |
| **Simulation Time Control** | Virtual clock advances faster/slower than wall clock | HIGH | Advance 4 hours per tick instead of real 45 minutes. Enables "replay 2 weeks in 1 day" demos. Already partially implemented (simulation_time, tick_duration_hours). |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Continuous Execution** | "Run 24/7 for max realism" | Cron-triggered = discrete events. Continuous = different architecture (event loop, websockets). Over-engineers for the use case. | Increase cron frequency (30 min → 15 min) if more actions needed. Discrete ticks are the design. |
| **Optimistic Execution** | "Execute speculatively, rollback if Jira changed" | Cron = no rollback capability between ticks. Can't undo Jira changes. Must be conservative (check-then-act). | Always reconcile state before actions. Use locks/transactions if parallel execution added. |
| **Real-Time Streaming** | "WebSocket events from Jira" | Jira doesn't offer real-time webhooks reliably. Polling + cron = proven model. Streaming adds complexity without value. | Polling at tick start is sufficient. Frontend polls dashboard API every 15s for "real-time" feel. |
| **Millisecond Precision Timing** | "Execute at exactly 10:37:42.315" | Cron granularity = minutes. Sub-minute precision is false accuracy. Events happen "around Day 3", not at exact timestamps. | Use day-level scheduling (Day 1-14). Add hour-level if needed (morning/afternoon), not milliseconds. |
| **Perfect Script Adherence** | "Execute script exactly as planned" | Reality always diverges: Jira edited manually, API errors, agent overload. Perfect adherence = brittle. | Adaptive pathfinding: recalculate when reality diverges. Script is target, not contract. |
| **Manual Intervention Mid-Sprint** | "Let user edit scenario while running" | State consistency nightmare. Is running scenario the source of truth or is Jira? Who wins on conflict? | Scripts are immutable once started. Edit next sprint's scenario instead. Reconciliation handles external changes. |
| **Virtual Time Precision** | "Track simulation time to the second" | Discrete events = time hops between events. Sub-event precision is meaningless. | Tick duration (4 hours default) is sufficient granularity. Day-level is often enough. |

## Feature Dependencies

```
State Reconciliation
    └──requires──> Idempotency
                       └──requires──> Event Execution Tracking

Adaptive Pathfinding
    └──requires──> State Reconciliation
    └──requires──> Phase/Status Mapping

Planning Horizon (2-3 sprints)
    └──requires──> Script-Based Scheduling
    └──enhances──> Chaos Injection (cross-sprint disruptions)

Realistic Timing Variance
    ──conflicts──> Lookahead Optimization (less predictable = harder to batch)

Simulation Time Control
    └──requires──> Graceful Degradation (if time != wall clock, cache invalidation matters more)
    ──enhances──> Planning Horizon (faster time = test more sprints quickly)

Multi-Team Orchestration
    └──requires──> State Reconciliation (more state to sync)
    └──requires──> Event Execution Tracking (which team executed what)
```

### Dependency Notes

- **State Reconciliation requires Idempotency:** If reconciliation re-processes events, idempotency prevents duplicate Jira changes.
- **Adaptive Pathfinding requires State Reconciliation:** Can't recalculate path if local state is stale.
- **Planning Horizon enhances Chaos Injection:** Pre-planning 3 sprints enables "blocker injected Sprint 7, resolved Sprint 8" narratives.
- **Realistic Timing Variance conflicts with Lookahead Optimization:** If events execute with jitter, batching becomes harder (can't predict which events will execute this tick).
- **Simulation Time Control enhances Planning Horizon:** If virtual time advances 4 hours/tick instead of wall-clock 45 minutes, you can simulate weeks in days.

## MVP Definition

### Launch With (v1)

Minimum viable product — what's needed to validate the concept.

- [x] **State Reconciliation** — Already implemented (sync_state_with_jira). Essential for cron architecture.
- [x] **Script-Based Scheduling** — Already implemented (SprintScenario, ScriptEvent). Core differentiator.
- [x] **Event Execution Tracking** — Already implemented (executed flags). Prevents duplication.
- [x] **Phase/Status Mapping** — Already implemented. Local phases map to Jira statuses.
- [ ] **Idempotency Checks** — Partially implemented. Needs explicit "already executed" guards before Jira writes.
- [x] **Graceful Degradation** — Already implemented (cached Jira data, fallback to last-known state).
- [x] **Chaos Injection** — Already designed (BLOCKER, QA_REJECTION events). Needs execution hookup.
- [x] **Scenario Archetypes** — Already implemented (SMOOTH_SPRINT, BLOCKER_HEAVY, etc.).

### Add After Validation (v1.x)

Features to add once core is working.

- [ ] **Adaptive Pathfinding** — When reality diverges, recalculate remaining script. High value, high complexity.
- [ ] **Planning Horizon (2-3 sprints)** — Generate Sprint N+1, N+2 scenarios ahead. Enables better narratives.
- [ ] **Realistic Timing Variance** — Add jitter so events don't execute on exact schedule. More realistic.
- [ ] **Lookahead Optimization** — Batch 2-3 events per tick when safe. Reduces cron invocations.
- [ ] **State Divergence Metrics** — Track script_fidelity for analytics. Low effort, high insight.
- [ ] **Mood-Based Tone Adaptation** — Already modeled, needs LLM prompt integration. Polish feature.

### Future Consideration (v2+)

Features to defer until product-market fit is established.

- [ ] **Multi-Team Orchestration** — Cross-team dependency scenarios. Complex, niche value for now.
- [ ] **Simulation Time Control** — Virtual clock vs wall clock. Useful for demos, not core use case yet.
- [ ] **Advanced Reconciliation Strategies** — CQRS, SAGA patterns. Over-engineering until scale demands it.
- [ ] **Event Replay/Audit Trail** — Full event sourcing for debugging. Nice to have, not critical for MVP.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| State Reconciliation | HIGH | MEDIUM | P1 (done) |
| Idempotency Checks | HIGH | MEDIUM | P1 |
| Chaos Injection | HIGH | LOW | P1 |
| Adaptive Pathfinding | HIGH | HIGH | P2 |
| Planning Horizon | MEDIUM | MEDIUM | P2 |
| Realistic Timing Variance | MEDIUM | MEDIUM | P2 |
| Lookahead Optimization | MEDIUM | MEDIUM | P2 |
| State Divergence Metrics | MEDIUM | LOW | P2 |
| Mood-Based Tone Adaptation | LOW | LOW | P2 |
| Multi-Team Orchestration | MEDIUM | MEDIUM | P3 |
| Simulation Time Control | LOW | HIGH | P3 |
| Event Replay/Audit Trail | LOW | MEDIUM | P3 |

**Priority key:**
- P1: Must have for launch (next milestone)
- P2: Should have, add when possible (v1.x)
- P3: Nice to have, future consideration (v2+)

## Competitor Feature Analysis

| Feature | Chaos Engineering Tools (LitmusChaos, Chaos Mesh) | Treasury Management Systems (2026) | Our Approach |
|---------|--------------|--------------|--------------|
| **Scenario-Based Simulation** | Pre-built experiments, game-day simulations | Scenario analysis in seconds | Sprint-level archetypes with pre-scripted events |
| **Chaos Injection** | Fault injection (network, pod failures) | Not applicable | Blockers, QA rejections, scope creep at planned times |
| **State Reconciliation** | Kubernetes state observation | Real-time data from banks/ERPs | Poll Jira API at tick start, reconcile local state |
| **Real-Time Execution** | Event-driven chaos experiments | Real-time cash data flows | Cron-triggered ticks (45 min intervals), not continuous |
| **Automation** | CI/CD integration, GitOps triggers | AI-powered forecasting | LLM-generated scenarios, automated event execution |
| **Observability** | Metrics, dashboards, experiment results | Predictive insights, anomaly detection | Event execution logs, state divergence metrics |

**Key Insight:** Chaos engineering tools focus on infrastructure resilience (pods, networks). We focus on team/workflow resilience (blockers, overload, rework). Treasury systems show that real-time reconciliation + AI automation = 2026 baseline expectation.

## Architecture Pattern: Cron-Triggered Discrete Event Simulation

This system is a **real-time discrete event simulator triggered by cron**, a pattern with historical roots:

> "A Purdue graduate student, Robert Brown, recognized the parallel between cron and discrete event simulators, and created an implementation of the Franta–Maly event list manager (ELM) for experimentation. Discrete event simulators run in virtual time, peeling events off the event queue as quickly as possible. Running the event simulator in 'real time' instead of virtual time created a version of cron."
> — [Cron - Wikipedia](https://en.wikipedia.org/wiki/Cron)

### Key Characteristics

1. **Discrete Events, Not Continuous:** Time hops between ticks. Events scheduled by day (Day 1-14), not continuous time.
2. **Conservative Synchronization:** No rollback capability. Must reconcile before acting (check-then-act).
3. **Wall Clock vs Simulation Time:** Wall clock = real time between cron invocations (45 min). Simulation time = virtual time advanced per tick (configurable, e.g., 4 hours).
4. **No Lookahead Assumptions:** Unlike parallel DES, can't assume future events are safe. Must check Jira state each tick.
5. **Eventual Consistency:** Between ticks, external system (Jira) may change. Reconciliation brings system back to consistency.

### Design Implications

- **No optimistic execution:** Can't execute speculatively and rollback if Jira changed. Must verify state before action.
- **Idempotency critical:** If tick fails mid-execution, retry must be safe. Check "already executed" before Jira writes.
- **Reconciliation = table stakes:** External system is source of truth. Local state is cache. Sync at tick start.
- **Script is target, not contract:** Pre-planned events may not execute if reality diverged. Adaptive pathfinding recalculates.
- **Time granularity = tick duration:** Sub-tick timing is false precision. Events happen "around Day 3", not exact timestamps.

## Sources

Research informed by:

### Real-Time Simulation and Scheduling
- [Discrete-event simulation - Wikipedia](https://en.wikipedia.org/wiki/Discrete-event_simulation)
- [A simulation-based scheduling system for real-time optimization and decision making support - ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S073658451100007X)
- [Chapter 12 Simulation-based Scheduling in Industry 4.0 | Simio and Simulation](https://textbook.simio.com/SASMAA7/ch-scheduling.html)
- [Top 10 Treasury Management Systems for 2025: AI-Powered Intelligence | GTreasury](https://www.gtreasury.com/posts/top-10-treasury-management-systems)

### Chaos Engineering and Scenario-Based Systems
- [Analysis of the Seven Application Scenarios of ChaosBlade - Oreate AI Blog](https://www.oreateai.com/blog/analysis-of-the-seven-application-scenarios-and-technical-features-of-the-chaos-engineering-fault-injection-tool-chaosblade/9da4bb3a01f22da2cea7a3bca672ae12)
- [LitmusChaos - Open Source Chaos Engineering Platform](https://litmuschaos.io/)
- [Bootstrap your chaos engineering journey with AWS FIS Scenarios Library | AWS Blog](https://aws.amazon.com/blogs/mt/bootstrap-your-chaos-engineering-journey-with-aws-fault-injection-service-scenarios-library/)
- [Chaos Mesh: A Powerful Chaos Engineering Platform for Kubernetes](https://chaos-mesh.org/)

### Event-Driven Architecture and State Reconciliation
- [Microservices Pattern: Event-driven architecture](https://microservices.io/patterns/data/event-driven-architecture.html)
- [Eventual Consistency in Microservices: Event-Driven vs. REST | Solace](https://solace.com/blog/eventual-consistency-in-microservices/)
- [Event-Driven Architecture (EDA): A Complete Introduction](https://www.confluent.io/learn/event-driven-architecture/)
- [Ensuring Data Consistency in Event-Driven Architectures - DEV Community](https://dev.to/isaactony/ensuring-data-consistency-in-event-driven-5hhk)

### Discrete Event Simulation and Time Management
- [A Major Difference Between Continuous Simulation and Discrete-Event Simulation | R.P. Churchill](https://rpchurchill.com/wordpress/posts/2016/01/11/a-major-difference-between-continuous-simulation-and-discrete-event-simulation/)
- [Discrete Event Simulation](https://www.med.upenn.edu/kmas/DES.htm)
- [Discrete-Event vs Continuous Simulation: A Comparison Guide](https://www.linkedin.com/advice/1/how-can-you-compare-discrete-event-continuous)
- [Simulation time vs. wall-clock time | ResearchGate](https://www.researchgate.net/figure/Simulation-time-vs-wall-clock-time_fig2_252024712)

---
*Feature research for: Real-time scenario-based simulation with external system reconciliation*
*Researched: 2026-01-27*
