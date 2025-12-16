# Flow Diagrams

Visual diagrams to help understand the system architecture and flows.

> **Note:** These diagrams use [Mermaid](https://mermaid.js.org/) syntax. They render automatically on GitHub and in many Markdown viewers.

---

## System Architecture

High-level view of how components connect:

```mermaid
flowchart TB
    subgraph External["External Systems"]
        N8N[n8n Scheduler]
        JIRA[Jira Cloud API]
        ANTHROPIC[Anthropic API]
    end

    subgraph Simulator["Jira Team Simulator"]
        API[FastAPI Server]
        ORCH[Orchestrator]

        subgraph AI["AI Layer"]
            ANALYZER[Analyzer<br/>Rules-based]
            PLANNER[Planner<br/>Claude Sonnet]
            CREWS[CrewAI Crews<br/>Claude Haiku]
        end

        STATE[(State<br/>JSON file)]
        CONFIG[(Config<br/>YAML files)]
    end

    N8N -->|POST /trigger| API
    API --> ORCH
    ORCH --> ANALYZER
    ANALYZER -->|Opportunities| PLANNER
    PLANNER -->|Planned Actions| CREWS
    CREWS -->|Jira API calls| JIRA
    PLANNER -.->|LLM calls| ANTHROPIC
    CREWS -.->|LLM calls| ANTHROPIC
    ORCH <-->|Read/Write| STATE
    ORCH -->|Read| CONFIG
```

---

## Tick Execution Flow

What happens when `/trigger` is called:

```mermaid
flowchart TD
    START([POST /trigger]) --> LOAD[Load State<br/>from JSON]
    LOAD --> INTENSITY{Determine<br/>Intensity}

    INTENSITY -->|20%| LIGHT[Light<br/>1-2 actions]
    INTENSITY -->|60%| NORMAL[Normal<br/>2-4 actions]
    INTENSITY -->|20%| BUSY[Busy<br/>4-6 actions]

    LIGHT --> ANALYZE
    NORMAL --> ANALYZE
    BUSY --> ANALYZE

    ANALYZE[Analyze Board<br/>Detect Opportunities] --> PLAN[Plan Actions<br/>LLM Decision]

    PLAN --> EXECUTE[Execute Actions<br/>via CrewAI]

    EXECUTE --> UPDATE[Update State]
    UPDATE --> SAVE[Save State<br/>to JSON]
    SAVE --> RESPONSE([Return Response])

    style PLAN fill:#e1f5fe
    style EXECUTE fill:#e1f5fe
```

---

## Scenario State Machine

How tickets flow through different scenario types:

```mermaid
stateDiagram-v2
    [*] --> CREATED: New ticket
    CREATED --> BACKLOG: Added to backlog

    state "Normal Flow" as normal {
        BACKLOG --> ASSIGNED: Developer picks up
        ASSIGNED --> IN_PROGRESS: Work starts
        IN_PROGRESS --> IN_REVIEW: PR submitted
        IN_REVIEW --> IN_TESTING: Review approved
        IN_TESTING --> COMPLETED: QA passes
    }

    COMPLETED --> [*]

    state "Blocker Path" as blocker {
        IN_PROGRESS --> BLOCKED: Issue found
        BLOCKED --> BLOCKER_DISCUSSED: Team discusses
        BLOCKER_DISCUSSED --> UNBLOCKING: Resolution found
        UNBLOCKING --> IN_PROGRESS: Continue work
    }

    state "Rework Path" as rework {
        IN_TESTING --> REJECTED: QA fails
        REJECTED --> FIXING: Dev fixes
        FIXING --> RE_REVIEW: Fix complete
        RE_REVIEW --> RE_TESTING: Review passes
        RE_TESTING --> COMPLETED: QA passes
    }

    state "Dependency Path" as dependency {
        IN_PROGRESS --> WAITING_DEPENDENCY: Blocked by other ticket
        WAITING_DEPENDENCY --> DEPENDENCY_RESOLVED: Other ticket done
        DEPENDENCY_RESOLVED --> IN_PROGRESS: Continue work
    }
```

---

## Agent Decision Flow

How an agent decides what action to take:

```mermaid
flowchart TD
    START([Agent Selected]) --> CHECK_TIME{Last action<br/>> 20 min ago?}

    CHECK_TIME -->|No| SKIP([Skip this tick])
    CHECK_TIME -->|Yes| CHECK_PROB{Activity level<br/>check}

    CHECK_PROB -->|Fail| SKIP
    CHECK_PROB -->|Pass| GET_CONTEXT[Get Board Context]

    GET_CONTEXT --> ROLE{Agent Role?}

    ROLE -->|PM| PM_ACTIONS[Create story<br/>Add AC<br/>Prioritize<br/>Comment]
    ROLE -->|Developer| DEV_ACTIONS[Pick up task<br/>Transition<br/>Log work<br/>Comment]
    ROLE -->|QA| QA_ACTIONS[Approve/Reject<br/>Add scenarios<br/>Create bug]
    ROLE -->|Tech Lead| TL_ACTIONS[Code review<br/>Architecture<br/>Flag blocker]

    PM_ACTIONS --> WEIGHT[Weight by<br/>board state]
    DEV_ACTIONS --> WEIGHT
    QA_ACTIONS --> WEIGHT
    TL_ACTIONS --> WEIGHT

    WEIGHT --> SELECT[Select Action<br/>Weighted random]
    SELECT --> EXECUTE[Execute via<br/>Jira API]
    EXECUTE --> RECORD[Record to State]
    RECORD --> DONE([Complete])
```

---

## Jira Workflow Mapping

How simulator states map to Jira workflow:

```mermaid
flowchart LR
    subgraph Simulator["Simulator Phases"]
        S_BACK[BACKLOG]
        S_PROG[IN_PROGRESS]
        S_REV[IN_REVIEW]
        S_TEST[IN_TESTING]
        S_DONE[COMPLETED]
    end

    subgraph Jira["Jira Statuses"]
        J_BACK[Backlog]
        J_TODO[To Do]
        J_PROG[In Progress]
        J_REV[Code Review]
        J_TEST[Testing / QA]
        J_DONE[Done]
    end

    S_BACK -.-> J_BACK
    S_BACK -.-> J_TODO
    S_PROG -.-> J_PROG
    S_REV -.-> J_REV
    S_TEST -.-> J_TEST
    S_DONE -.-> J_DONE

    style S_BACK fill:#fff3e0
    style S_PROG fill:#e3f2fd
    style S_REV fill:#f3e5f5
    style S_TEST fill:#e8f5e9
    style S_DONE fill:#e0f2f1
```

---

## AI Planning Flow

How the planner decides actions:

```mermaid
flowchart TD
    subgraph Input["Inputs to Planner"]
        BOARD[Board State<br/>Tickets by status]
        SCENARIOS[Active Scenarios<br/>Type, phase, age]
        OPPS[Opportunities<br/>High/Med/Low priority]
        RECENT[Recent Actions<br/>Avoid repetition]
        SPRINT[Sprint Context<br/>Day 1-14]
    end

    subgraph Planning["LLM Planning (Sonnet)"]
        PROMPT[Build Prompt<br/>with all context]
        LLM[Claude Sonnet<br/>Strategic reasoning]
        PARSE[Parse JSON<br/>response]
    end

    subgraph Output["Planned Actions"]
        A1[Action 1<br/>e.g., qa_approve]
        A2[Action 2<br/>e.g., pick_up_task]
        A3[Action 3<br/>e.g., progress_to_review]
    end

    BOARD --> PROMPT
    SCENARIOS --> PROMPT
    OPPS --> PROMPT
    RECENT --> PROMPT
    SPRINT --> PROMPT

    PROMPT --> LLM
    LLM --> PARSE

    PARSE --> A1
    PARSE --> A2
    PARSE --> A3

    style LLM fill:#e1f5fe
```

---

## Comment Generation Flow

How AI generates contextual comments:

```mermaid
flowchart TD
    subgraph Context["Context Gathering"]
        PERSONA[Agent Persona<br/>Communication style]
        TICKET[Ticket Details<br/>Summary, description]
        HISTORY[Recent Comments<br/>Last 3 messages]
        ACTION[Action Context<br/>What they're doing]
    end

    subgraph Generation["LLM Generation"]
        BUILD[Build Prompt]
        DECIDE{Complex<br/>action?}
        HAIKU[Claude Haiku<br/>Fast & cheap]
        SONNET[Claude Sonnet<br/>Technical depth]
        RESULT[Generated Comment]
    end

    subgraph Output["Posted to Jira"]
        COMMENT[Jira Comment<br/>Persona-appropriate]
    end

    PERSONA --> BUILD
    TICKET --> BUILD
    HISTORY --> BUILD
    ACTION --> BUILD

    BUILD --> DECIDE
    DECIDE -->|No| HAIKU
    DECIDE -->|Yes| SONNET

    HAIKU --> RESULT
    SONNET --> RESULT
    RESULT --> COMMENT

    style HAIKU fill:#c8e6c9
    style SONNET fill:#e1f5fe
```

---

## Sprint Lifecycle

How activity varies through a sprint:

```mermaid
gantt
    title Sprint Activity Patterns
    dateFormat X
    axisFormat Day %s

    section Task Pickup
    High pickup rate    :active, 1, 3
    Moderate pickup     :        4, 7
    Low pickup         :        8, 14

    section Development
    Ramping up         :        1, 3
    Peak development   :active, 4, 10
    Finishing up       :        11, 14

    section Code Review
    Low activity       :        1, 4
    Peak reviews       :active, 5, 11
    Final reviews      :        12, 14

    section QA/Testing
    Minimal testing    :        1, 7
    Peak testing       :active, 8, 13
    Final verification :        14, 14

    section Blockers
    May emerge         :crit,   4, 10

    section Scope Creep
    Possible window    :crit,   4, 10
```

---

## Team Interaction Pattern

How teams and roles interact:

```mermaid
flowchart TB
    subgraph Team_Alpha["Team Alpha"]
        SARAH[Sarah<br/>PM]
        MARCUS[Marcus<br/>Tech Lead]
        ELENA[Elena<br/>Sr Dev]
        JAMES[James<br/>Mid Dev]
        PRIYA[Priya<br/>QA]
    end

    subgraph Team_Beta["Team Beta"]
        DAVID[David<br/>PM]
        ANA[Ana<br/>Mid Dev]
        TYLER[Tyler<br/>Jr Dev]
        RACHEL[Rachel<br/>QA]
    end

    SARAH -->|Creates stories| ELENA
    SARAH -->|Creates stories| JAMES
    DAVID -->|Creates stories| ANA
    DAVID -->|Creates stories| TYLER

    ELENA -->|Submits for review| MARCUS
    JAMES -->|Submits for review| MARCUS
    ANA -->|Submits for review| MARCUS
    TYLER -->|Submits for review| MARCUS

    MARCUS -->|Approves| PRIYA
    MARCUS -->|Approves| RACHEL

    PRIYA -->|Tests| ELENA
    PRIYA -->|Tests| JAMES
    RACHEL -->|Tests| ANA
    RACHEL -->|Tests| TYLER

    TYLER -.->|Asks questions| MARCUS
    TYLER -.->|Gets help| ANA

    style MARCUS fill:#f3e5f5
    style PRIYA fill:#e8f5e9
    style RACHEL fill:#e8f5e9
```

---

## Data Flow

How data moves through the system:

```mermaid
flowchart LR
    subgraph Config["Configuration"]
        SETTINGS[settings.yaml<br/>Parameters]
        PERSONAS[personas.yaml<br/>Agent definitions]
        TEMPLATES[templates.yaml<br/>Comment templates]
    end

    subgraph Runtime["Runtime"]
        STATE[state.json<br/>Current state]
        LOGS[logs.db<br/>Activity logs]
    end

    subgraph External["External"]
        JIRA[(Jira Cloud)]
        ANTHROPIC[(Anthropic API)]
    end

    CONFIG --> |Loaded at startup| RUNTIME
    SETTINGS --> RUNTIME
    PERSONAS --> RUNTIME
    TEMPLATES --> RUNTIME

    RUNTIME <-->|Read/Write| STATE
    RUNTIME -->|Append| LOGS

    RUNTIME <-->|API calls| JIRA
    RUNTIME -->|LLM calls| ANTHROPIC

    style STATE fill:#fff3e0
    style LOGS fill:#e3f2fd
```

---

## Error Handling Flow

How the system handles failures:

```mermaid
flowchart TD
    ACTION[Execute Action] --> TRY{Try Jira<br/>API Call}

    TRY -->|Success| UPDATE[Update State]
    TRY -->|Failure| LOG_ERR[Log Error]

    LOG_ERR --> RETRY{Retry?}
    RETRY -->|Yes| TRY
    RETRY -->|No| MARK_FAIL[Mark Action Failed]

    MARK_FAIL --> CONTINUE{More<br/>actions?}
    UPDATE --> CONTINUE

    CONTINUE -->|Yes| NEXT[Next Action]
    CONTINUE -->|No| SAVE[Save State]

    NEXT --> ACTION
    SAVE --> RESPONSE[Return Response<br/>with errors noted]

    style LOG_ERR fill:#ffcdd2
    style MARK_FAIL fill:#ffcdd2
```
