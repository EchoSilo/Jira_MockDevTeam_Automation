# Jira Team Simulator - Architecture & Logic Flow

This document provides a comprehensive reference for understanding the app's execution flow, state management, and interdependencies. It serves as a guide for Claude Code and developers to understand the system's intent and behavior.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Core Execution Flow](#core-execution-flow)
3. [State Management](#state-management)
4. [Sprint Lifecycle](#sprint-lifecycle)
5. [Scenario Lifecycle](#scenario-lifecycle)
6. [Agent System](#agent-system)
7. [Critical Invariants](#critical-invariants)
8. [Known Edge Cases](#known-edge-cases)
9. [Dependency Graph](#dependency-graph)

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         JIRA TEAM SIMULATOR                              │
│                                                                          │
│  Purpose: Generate realistic development team activity in Jira for       │
│           productivity analytics testing                                 │
│                                                                          │
│  Trigger: n8n cron job → POST /trigger (every ~45 min, M-F, 9-5)        │
│                                                                          │
│  Output: Jira tickets, comments, status changes, work logs              │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│    n8n       │────▶│   FastAPI    │────▶│ Orchestrator │────▶│   Jira API   │
│  (trigger)   │     │  (main.py)   │     │  (scenario)  │     │   (output)   │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                            │                    │
                            ▼                    ▼
                     ┌──────────────┐     ┌──────────────┐
                     │    State     │     │     LLM      │
                     │ (state.json) │     │  (planning)  │
                     └──────────────┘     └──────────────┘
```

---

## Core Execution Flow

### /trigger Endpoint Sequence

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    /trigger ENDPOINT EXECUTION ORDER                     │
└─────────────────────────────────────────────────────────────────────────┘

PHASE 1: INITIALIZATION
═══════════════════════════════════════════════════════════════════════════
│
├─ 1. load_state()                    [main.py:351]
│      └─ Read state.json from disk
│
├─ 2. is_new_day() check              [main.py:354]
│      └─ If True: advance_day()
│           ├─ Increment simulation_day
│           ├─ Reset agent daily counters
│           └─ Advance sprint.sprint_day (may trigger new sprint)
│
├─ 3. determine_intensity()           [main.py:358]
│      └─ Random: light (2-3 actions) / normal (3-4) / busy (4-5)
│
└─ 4. Start logging session           [main.py:361-366]


PHASE 2: STATE SYNCHRONIZATION (ORDER MATTERS!)
═══════════════════════════════════════════════════════════════════════════
│
├─ 5. sync_state_with_jira()          [main.py:374] ◄── FIRST
│      ├─ Get active sprint from Jira
│      ├─ Parse sprint_number from name (e.g., "ESCRUM Sprint 7" → 7)
│      ├─ Update state.sprint.sprint_number if different
│      ├─ Calculate sprint_day from Jira start_date
│      └─ Sync scenarios with Jira tickets
│
├─ 6. check_and_handle_expired_sprint [main.py:379] ◄── SECOND
│      ├─ Get active sprint from Jira
│      ├─ Check if end_date has passed
│      └─ If expired:
│           ├─ Call SprintPlanningCrew.rollover_sprint()
│           ├─ state.clear_sprint_scenario()
│           ├─ state.sprint.sprint_number += 1
│           └─ state.sprint.sprint_day = 1
│
└─ 7. validate_state_agent_ids()      [main.py:384]
       └─ Remove invalid agent references


PHASE 3: ORCHESTRATOR EXECUTION
═══════════════════════════════════════════════════════════════════════════
│
├─ 8. Create ScenarioOrchestrator     [main.py:387-393]
│
└─ 9. orchestrator.run_tick()         [main.py:399-402]
       │
       ├─ 9a. Validate sprint scenario  [orchestrator.py:187-200]
       │       └─ Clear if stale (scenario.sprint_name != active_sprint.name)
       │
       ├─ 9b. ANALYZE                   [orchestrator.py:203-218]
       │       ├─ Get board snapshot (active sprint, issues, metrics)
       │       └─ Detect opportunities (phase advances, sprint actions, etc.)
       │
       ├─ 9c. PLAN                      [orchestrator.py:238-248]
       │       └─ LLM decides which actions to take based on opportunities
       │
       └─ 9d. EXECUTE                   [orchestrator.py:251-316]
               └─ For each planned action:
                    ├─ _execute_action() modifies state
                    └─ Record result


PHASE 4: PERSISTENCE
═══════════════════════════════════════════════════════════════════════════
│
├─ 10. save_state(state)              [main.py:405]
│       └─ Write state.json to disk
│
├─ 11. _state_cache.update(state)     [main.py:406]
│
└─ 12. Return TriggerResponse         [main.py:421-435]
```

---

## State Management

### State Structure

```
SimulationState (state.json)
│
├── last_run: datetime                 # When simulation last ran
├── simulation_day: int                # Total days simulated
│
├── sprint: SprintState
│   ├── sprint_number: int             # Current sprint (e.g., 7)
│   ├── sprint_day: int                # Day within sprint (1-7)
│   ├── total_days: int                # Sprint duration (7)
│   └── start_date: datetime           # When this sprint started
│
├── active_scenarios: dict[id, ActiveScenario]
│   └── Each scenario tracks a ticket through its lifecycle
│
├── agents: dict[agent_id, AgentState]
│   └── Each agent's workload, assignments, action counts
│
├── sprint_scenario: SprintScenario    # Current sprint's planned events
│   ├── sprint_id: int                 # Sprint number this is for
│   ├── sprint_name: str               # e.g., "ESCRUM Sprint 7"
│   ├── archetype: str                 # smooth/overloaded/blocker-heavy
│   └── script: list[DayEvents]        # Planned events by day
│
└── completed_sprint_scenarios: list   # History of completed sprint IDs
```

### State Modification Rules

```
WHO CAN MODIFY STATE:
═══════════════════════════════════════════════════════════════════════════

1. SYNC_STATE_WITH_JIRA (sync phase)
   ├─ CAN: Update sprint_number, sprint_day from Jira
   ├─ CAN: Create scenarios for untracked tickets
   └─ CANNOT: Modify sprint_scenario

2. CHECK_AND_HANDLE_EXPIRED_SPRINT (sync phase)
   ├─ CAN: Increment sprint_number
   ├─ CAN: Reset sprint_day to 1
   ├─ CAN: Clear sprint_scenario
   └─ CANNOT: Create new sprint_scenario (happens in next tick)

3. ORCHESTRATOR.RUN_TICK (execution phase)
   ├─ CAN: Clear stale sprint_scenario
   ├─ CAN: Create/modify scenarios
   ├─ CAN: Update agent states
   ├─ CAN: Record actions
   └─ CAN: Create sprint_scenario (via planned action)

4. AGENT ACTIONS (during execution)
   ├─ CAN: Transition scenario phases
   ├─ CAN: Update agent workload
   └─ CAN: Record action in scenario history
```

---

## Sprint Lifecycle

### Sprint State Machine

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        SPRINT STATE MACHINE                              │
└─────────────────────────────────────────────────────────────────────────┘

                    ┌──────────────────┐
                    │  FUTURE SPRINT   │
                    │  (state=future)  │
                    └────────┬─────────┘
                             │
                    start_sprint()
                             │
                             ▼
                    ┌──────────────────┐
        ┌──────────│  ACTIVE SPRINT   │◄─────────────────┐
        │          │  (state=active)  │                  │
        │          └────────┬─────────┘                  │
        │                   │                            │
        │          sprint_day advances                   │
        │                   │                            │
        │                   ▼                            │
        │          ┌──────────────────┐                  │
        │          │   DAY 7 CHECK    │                  │
        │          │ is_sprint_       │                  │
        │          │ complete_day()   │                  │
        │          └────────┬─────────┘                  │
        │                   │                            │
        │        ┌──────────┴──────────┐                 │
        │        │                     │                 │
        │   True (day==7)        False (day<7)          │
        │        │                     │                 │
        │        ▼                     │                 │
        │   complete_sprint            └─────────────────┘
        │   opportunity                  (continue)
        │        │
        │        ▼
        │   ┌──────────────────┐
        │   │ ROLLOVER CHECK   │
        │   │ (end_date check) │
        │   └────────┬─────────┘
        │            │
        │   ┌────────┴────────┐
        │   │                 │
        │ expired         not expired
        │   │                 │
        │   ▼                 │
        │   rollover_sprint   └───────────────────────────┐
        │        │                                        │
        │        ▼                                        │
        │   ┌──────────────────┐                          │
        │   │  CLOSED SPRINT   │                          │
        │   │  (state=closed)  │                          │
        │   └────────┬─────────┘                          │
        │            │                                    │
        │   move incomplete items                         │
        │            │                                    │
        │            ▼                                    │
        │   ┌──────────────────┐                          │
        └───│  NEW SPRINT      │──────────────────────────┘
            │  (next sprint    │
            │   becomes active)│
            └──────────────────┘


DETECTION MECHANISMS:
═══════════════════════════════════════════════════════════════════════════

1. LOCAL STATE DETECTION (analyzer.py:808)
   └─ Condition: state.sprint.is_sprint_complete_day()
   └─ Returns: sprint_day == total_days (i.e., day 7)
   └─ Creates: "complete_sprint" opportunity

2. JIRA DATE DETECTION (main.py:142)
   └─ Condition: datetime.now(utc) > active_sprint.end_date
   └─ Triggers: Automatic rollover via SprintPlanningCrew
```

### Sprint Scenario Lifecycle

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SPRINT SCENARIO LIFECYCLE                             │
└─────────────────────────────────────────────────────────────────────────┘

1. CREATION
   └─ When: Analyzer detects scenario_missing or scenario_stale
   └─ Creates: "sprint_planning" opportunity with scenario_reason
   └─ Executed: SprintPlanningCrew.plan_sprint_with_scenario()
   └─ Generates: Archetype-based event script (smooth, blocker-heavy, etc.)

2. ACTIVE USE
   └─ Orchestrator reads sprint_scenario.script for current day
   └─ Events guide which actions to take (blocker injection, completion, etc.)
   └─ Tracked: sprint_scenario.events_executed

3. VALIDATION
   └─ When: Each tick at orchestrator.py:187-200
   └─ Check: scenario.sprint_name == active_sprint.name
   └─ If mismatch: state.clear_sprint_scenario()

4. CLEARING
   └─ When: Sprint rolls over (check_and_handle_expired_sprint)
   └─ Action: state.clear_sprint_scenario()
   └─ Scenario ID added to completed_sprint_scenarios

5. EDGE CASE: Gap Between Clear and Regeneration
   └─ Tick N: Sprint expires, scenario cleared
   └─ Tick N+1: Analyzer detects missing scenario, schedules planning
   └─ Result: One tick runs without scenario guidance
```

---

## Scenario Lifecycle

### Ticket Scenario Phases

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SCENARIO PHASE STATE MACHINE                          │
└─────────────────────────────────────────────────────────────────────────┘

    ┌─────────┐
    │ BACKLOG │◄──────────────────────────────────────────────────────┐
    └────┬────┘                                                        │
         │ pick_up_task                                                │
         ▼                                                             │
    ┌─────────┐                                                        │
    │ASSIGNED │                                                        │
    └────┬────┘                                                        │
         │ start_work                                                  │
         ▼                                                             │
    ┌───────────┐              ┌─────────┐                             │
    │IN_PROGRESS│──────────────│ BLOCKED │ (blocker scenario)          │
    └────┬──────┘   inject_    └────┬────┘                             │
         │          blocker         │ resolve_blocker                  │
         │                          ▼                                  │
         │          ┌───────────────┴───────────────┐                  │
         │          │                               │                  │
         ▼          ▼                               │                  │
    ┌───────────┐                                   │                  │
    │ IN_REVIEW │◄──────────────────────────────────┘                  │
    └────┬──────┘                                                      │
         │ approve_review                                              │
         ▼                                                             │
    ┌────────────┐                                                     │
    │ IN_TESTING │                                                     │
    └────┬───────┘                                                     │
         │                                                             │
    ┌────┴────────────────┐                                            │
    │                     │                                            │
    ▼                     ▼                                            │
┌────────┐          ┌───────────┐                                      │
│APPROVED│          │ REJECTED  │                                      │
└───┬────┘          └─────┬─────┘                                      │
    │                     │ rework (back to IN_PROGRESS)               │
    ▼                     └────────────────────────────────────────────┘
┌─────────┐
│COMPLETED│
└─────────┘


PHASE TRANSITION RULES:
═══════════════════════════════════════════════════════════════════════════

Phase              → Next Phase(s)           Triggered By
─────────────────────────────────────────────────────────────────────────
BACKLOG            → ASSIGNED                PM/Dev picks up task
ASSIGNED           → IN_PROGRESS             Dev starts work
IN_PROGRESS        → IN_REVIEW               Dev completes work
IN_PROGRESS        → BLOCKED                 Blocker injected
BLOCKED            → IN_PROGRESS             Blocker resolved
IN_REVIEW          → IN_TESTING              Tech Lead approves
IN_TESTING         → COMPLETED               QA approves
IN_TESTING         → IN_PROGRESS (rework)    QA rejects
```

---

## Agent System

### Agent Roles and Permissions

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          AGENT HIERARCHY                                 │
└─────────────────────────────────────────────────────────────────────────┘

ROLE          │ CAN CREATE     │ CAN WORK ON        │ SPECIAL ACTIONS
══════════════╪════════════════╪════════════════════╪══════════════════════
PM            │ Epics, Stories │ Epics only         │ Sprint planning
              │ Bugs, Tasks    │                    │ Backlog grooming
──────────────┼────────────────┼────────────────────┼──────────────────────
Developer     │ Bugs           │ Stories, Bugs,     │ Status transitions
              │                │ Tasks (no Epics)   │ Work logging
──────────────┼────────────────┼────────────────────┼──────────────────────
QA            │ Bugs           │ Stories, Bugs,     │ Testing
              │                │ Tasks (no Epics)   │ Approve/Reject
──────────────┼────────────────┼────────────────────┼──────────────────────
Tech Lead    │ -              │ Stories, Bugs,     │ Code review
              │                │ Tasks (no Epics)   │ Architectural review


AGENT WORKLOAD TRACKING:
═══════════════════════════════════════════════════════════════════════════

AgentState {
  agent_id: str
  last_action: datetime
  actions_today: int              # Reset daily
  assigned_tickets: list[str]     # Currently assigned
  current_workload: int           # len(assigned_tickets)
  is_overloaded: bool             # workload >= 5
  sprint_assignments: int         # Tickets assigned this sprint
}

OVERLOAD PREVENTION:
- is_overloaded triggers at workload >= 5
- Analyzer creates "agent_overloaded" opportunity
- Planner may redistribute work
```

---

## Critical Invariants

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       CRITICAL INVARIANTS                                │
│              (Conditions that MUST always be true)                       │
└─────────────────────────────────────────────────────────────────────────┘

1. SPRINT NUMBER CONSISTENCY
   ├─ state.sprint.sprint_number MUST match Jira's active sprint number
   ├─ Enforced by: sync_state_with_jira() on each tick
   └─ Violation: Causes is_sprint_complete_day() to give wrong result

2. SPRINT DAY BOUNDS
   ├─ state.sprint.sprint_day MUST be in range [1, total_days]
   ├─ Enforced by: max(1, min(days_elapsed, total_days))
   └─ Violation: day > total_days breaks completion detection

3. SPRINT SCENARIO ALIGNMENT
   ├─ sprint_scenario.sprint_name MUST equal active_sprint.name
   ├─ Enforced by: Orchestrator validation at tick start
   └─ Violation: Stale scenario causes wrong events

4. AGENT-TICKET ASSIGNMENT SYMMETRY
   ├─ If ticket assigned to agent: agent.assigned_tickets MUST contain ticket
   ├─ If agent.assigned_tickets contains ticket: ticket MUST be assigned to agent
   └─ Enforced by: sync_agent_workloads() on state load

5. SCENARIO PHASE-STATUS CONSISTENCY
   ├─ scenario.current_phase MUST map to Jira ticket status
   ├─ Enforced by: Phase transition methods
   └─ Violation: Simulator acts on outdated state

6. JIRA END_DATE REQUIREMENT
   ├─ Active sprint MUST have end_date set for expiration detection
   ├─ Enforced by: create_sprint() and start_sprint() passing dates
   └─ Violation: Expired sprints never detected
```

---

## Known Edge Cases

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        KNOWN EDGE CASES                                  │
└─────────────────────────────────────────────────────────────────────────┘

1. EXTERNAL SPRINT MODIFICATION
   ├─ Scenario: User closes sprint manually in Jira
   ├─ Detection: sync_state_with_jira() sees different active sprint
   ├─ Resolution: Updates local sprint_number, clears stale scenario
   └─ Gap: One tick may use stale sprint_day

2. SPRINT SCENARIO GENERATION GAP
   ├─ Scenario: Sprint rolls over, scenario cleared
   ├─ Detection: Analyzer sees missing scenario on next tick
   ├─ Resolution: Schedules sprint_planning action
   └─ Gap: One tick runs without scenario guidance

3. DOUBLE SPRINT INCREMENT RISK
   ├─ Scenario: Jira sprint externally advanced AND expired
   ├─ Detection: sync updates sprint_number, then rollover increments
   ├─ Resolution: Actually correct behavior - rollover creates next sprint
   └─ Risk: If Jira has Sprint N but local has Sprint N-2, large jump

4. MISSING END_DATE ON SPRINT
   ├─ Scenario: Sprint created without end_date
   ├─ Detection: check_and_handle_expired_sprint() returns None silently
   ├─ Resolution: Fix create_sprint() to always return dates
   └─ Risk: Sprint never detected as expired

5. AGENT REASSIGNMENT WINDOW
   ├─ Scenario: Agent reassigned in Jira between sync and execution
   ├─ Detection: None during current tick
   ├─ Resolution: Next tick's sync catches it
   └─ Gap: Current tick may assign work to wrong agent

6. STATE FILE CORRUPTION
   ├─ Scenario: state.json becomes invalid JSON
   ├─ Detection: load_state() fails
   ├─ Resolution: Creates fresh SimulationState with defaults
   └─ Risk: Loses all state history, sprint_number resets to 1
```

---

## Dependency Graph

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DEPENDENCY GRAPH                                  │
│            (What depends on what for correct operation)                  │
└─────────────────────────────────────────────────────────────────────────┘

JIRA API (Source of Truth)
    │
    ├──▶ get_active_sprint()
    │        │
    │        ├──▶ sync_state_with_jira()
    │        │        └──▶ state.sprint.sprint_number
    │        │        └──▶ state.sprint.sprint_day
    │        │
    │        ├──▶ check_and_handle_expired_sprint()
    │        │        └──▶ state.sprint (on rollover)
    │        │        └──▶ state.sprint_scenario (cleared)
    │        │
    │        └──▶ Analyzer.detect_opportunities()
    │                 └──▶ complete_sprint opportunity
    │                 └──▶ sprint_planning opportunity
    │
    ├──▶ get_future_sprints()
    │        └──▶ Analyzer: next_sprint_id for rollover
    │
    └──▶ get_all_active_issues()
             └──▶ sync_state_with_jira()
                      └──▶ active_scenarios


STATE (Persisted)
    │
    ├──▶ sprint.sprint_number
    │        └──▶ sprint_scenario validation
    │        └──▶ Logging context
    │
    ├──▶ sprint.sprint_day
    │        └──▶ is_sprint_complete_day()
    │        └──▶ is_sprint_planning_day()
    │        └──▶ is_mid_sprint()
    │
    ├──▶ sprint_scenario
    │        └──▶ Orchestrator event scheduling
    │        └──▶ Planner context
    │
    └──▶ active_scenarios
             └──▶ detect_opportunities() (phase advances)
             └──▶ Agent workload calculations


ANALYZER (Detection)
    │
    ├──▶ depends on: board_snapshot (Jira state)
    │
    ├──▶ depends on: SimulationState
    │
    └──▶ produces: opportunities[]
             └──▶ consumed by: Planner


PLANNER (Decision)
    │
    ├──▶ depends on: opportunities (from Analyzer)
    │
    ├──▶ depends on: SimulationState
    │
    └──▶ produces: planned_actions[]
             └──▶ consumed by: Orchestrator._execute_action()


ORCHESTRATOR (Execution)
    │
    ├──▶ depends on: planned_actions (from Planner)
    │
    ├──▶ depends on: SimulationState (modified in place)
    │
    ├──▶ depends on: Crews (SprintPlanningCrew, etc.)
    │
    └──▶ produces: modified state, Jira changes
             └──▶ persisted by: save_state()
```

---

## Quick Reference: Common Debugging Scenarios

### Sprint Not Completing

```
CHECK IN ORDER:
1. state.sprint.sprint_day == 7?
   └─ No: Check sync_state_with_jira() is calculating from start_date

2. active_sprint.end_date exists?
   └─ No: Check create_sprint() is returning dates

3. Analyzer creating complete_sprint opportunity?
   └─ No: Check is_sprint_complete_day() logic

4. Planner selecting complete_sprint action?
   └─ No: Check planning priorities

5. complete_sprint includes next_sprint_id?
   └─ No: Items go to backlog instead of next sprint
```

### State Out of Sync with Jira

```
CHECK IN ORDER:
1. sync_state_with_jira() running?
   └─ Check /trigger endpoint calls it (line 374)

2. Jira sprint name parseable?
   └─ Must be "ESCRUM Sprint N" or "Sprint N" format

3. Exception being silently caught?
   └─ Check logs for "Failed to sync" warnings
```

### Missing Sprint Scenario

```
CHECK IN ORDER:
1. sprint_scenario.sprint_name matches active_sprint.name?
   └─ No: Scenario is stale, will be cleared

2. Analyzer detecting scenario_missing?
   └─ Check _detect_sprint_planning_opportunities()

3. sprint_planning action being scheduled?
   └─ Check Planner priorities

4. SprintPlanningCrew.plan_sprint_with_scenario() succeeding?
   └─ Check crew execution logs
```

---

*This document should be updated whenever significant logic changes are made to the simulator.*
