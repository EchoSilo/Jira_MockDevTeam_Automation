# Codebase Structure

**Analysis Date:** 2026-01-27

## Directory Layout

```
jira-simulator/
├── src/                           # Backend Python application
│   ├── main.py                    # FastAPI app entry point, /trigger handler
│   ├── __init__.py
│   ├── orchestrator/              # Simulation orchestration
│   │   ├── orchestrator.py        # Main ScenarioOrchestrator class
│   │   ├── analyzer.py            # ScenarioAnalyzer - board opportunity detection
│   │   ├── planner.py             # ScenarioPlanner - LLM-driven action planning
│   │   ├── pathfinder.py          # WorkflowPathfinder - scenario script generation
│   │   └── __init__.py
│   ├── agents/                    # Agent definitions (legacy, mostly superseded by crews)
│   │   ├── base_agent.py          # BaseAgent abstract class
│   │   ├── developer_agent.py     # DeveloperAgent implementation
│   │   ├── qa_agent.py            # QAAgent implementation
│   │   ├── pm_agent.py            # PMAgent implementation
│   │   ├── tech_lead_agent.py     # TechLeadAgent implementation
│   │   ├── coordinator_agent.py   # CoordinatorAgent (unused in current flow)
│   │   ├── release_manager_agent.py # ReleaseManagerAgent for version coordination
│   │   ├── agent_factories.py     # Agent factory functions
│   │   └── __init__.py
│   ├── crews/                     # CrewAI-based execution teams
│   │   ├── base_crew.py           # BaseCrew abstract class
│   │   ├── ticket_lifecycle_crew.py # Tasks: pick_up, progress_to_review, qa_approve
│   │   ├── blocker_crew.py        # Tasks: inject_blocker, discuss_blocker, resolve_blocker
│   │   ├── rework_crew.py         # Tasks: qa_reject, acknowledge_rejection, complete_fix, verify_fix
│   │   ├── scope_creep_crew.py    # Tasks: create_mid_sprint_story
│   │   ├── dependency_crew.py     # Tasks: identify_dependency, check_dependency, resolve_dependency
│   │   ├── sprint_planning_crew.py # Tasks: plan_sprint, create_future_sprint, rollover_sprint
│   │   └── __init__.py
│   ├── services/                  # External service integrations
│   │   ├── jira_client.py         # JiraClient - Jira REST API wrapper
│   │   ├── llm_service.py         # LLMService - Anthropic model routing
│   │   └── __init__.py
│   ├── tools/                     # CrewAI tools for agents
│   │   ├── jira_tools.py          # JiraTools - high-level Jira operations for agents
│   │   ├── context_tools.py       # ContextTools - context-aware helpers
│   │   └── __init__.py
│   ├── state/                     # State management and persistence
│   │   ├── models.py              # Pydantic models (SimulationState, ActiveScenario, AgentState, etc.)
│   │   ├── simulation_state.py    # State loading, saving, migration, sync logic
│   │   └── __init__.py
│   ├── scenarios/                 # Scenario management (sprint-level scenarios)
│   │   ├── sprint_scenario.py     # SprintScenario class - scripted sprint events
│   │   ├── scenario_planner.py    # ScenarioPlanner for sprint scenarios (legacy)
│   │   ├── script_executor.py     # ScriptExecutor - executes scenario events
│   │   └── __init__.py
│   ├── logging/                   # Comprehensive observability
│   │   ├── database.py            # LogDatabase - SQLite log persistence
│   │   ├── models.py              # Log data models
│   │   ├── writer.py              # AsyncLogWriter - async log writing
│   │   ├── logged_jira_client.py  # LoggedJiraClient - wraps JiraClient with logging
│   │   ├── logged_llm_service.py  # LoggedLLMService - wraps LLMService with logging
│   │   ├── crewai_callbacks.py    # CrewAILoggingCallback - hooks CrewAI execution
│   │   ├── api.py                 # Logging API routes (/logs/viewer, /logs/stats, etc.)
│   │   ├── query.py               # Log querying utilities
│   │   └── __init__.py
│   └── __init__.py
│
├── frontend/                      # React 19 TypeScript frontend
│   ├── src/
│   │   ├── main.tsx               # React entry point
│   │   ├── App.tsx                # Root component
│   │   ├── pages/                 # Page components
│   │   │   ├── Dashboard.tsx      # Main dashboard
│   │   │   ├── Chat.tsx           # PM chat interface
│   │   │   ├── Settings.tsx       # Settings/configuration
│   │   │   ├── Releases.tsx       # Release notes viewer/downloader
│   │   │   └── index.ts
│   │   ├── components/            # Reusable components
│   │   │   ├── common/            # Common UI components (Header, Footer, Layout)
│   │   │   ├── dashboard/         # Dashboard-specific (SprintCard, AgentPanel, ScenarioList, Charts)
│   │   │   ├── chat/              # Chat interface components
│   │   │   └── index.ts
│   │   ├── store/                 # Zustand state management
│   │   │   ├── dashboardStore.ts  # Dashboard state (agents, sprint, scenarios)
│   │   │   ├── chatStore.ts       # Chat state (messages, PMs)
│   │   │   ├── themeStore.ts      # Theme state (dark/light mode)
│   │   │   ├── releaseNotesStore.ts # Release notes cache
│   │   │   └── index.ts
│   │   ├── hooks/                 # Custom React hooks
│   │   │   ├── useApi.ts          # Data fetching with auto-refresh
│   │   │   └── index.ts
│   │   ├── lib/                   # Utilities and helpers
│   │   │   ├── api.ts             # API client (fetch wrapper)
│   │   │   ├── transformers.ts    # Data transformers (snake_case → camelCase)
│   │   │   ├── utils.ts           # General utilities
│   │   │   ├── mockData.ts        # Fallback data when backend unavailable
│   │   │   └── index.ts
│   │   ├── types/                 # TypeScript type definitions
│   │   │   └── index.ts           # All UI types (Agent, Sprint, Scenario, etc.)
│   │   ├── assets/                # Static assets (images, fonts)
│   │   └── index.css              # Global styles
│   │
│   ├── public/                    # Static public files
│   ├── dist/                      # Built production files (generated)
│   ├── package.json               # Dependencies: React, Vite, TailwindCSS, Zustand, Recharts
│   ├── vite.config.ts             # Vite bundler configuration
│   ├── tsconfig.json              # TypeScript configuration
│   └── tailwind.config.ts         # TailwindCSS configuration
│
├── config/                        # Configuration files
│   ├── settings.yaml              # Simulation parameters (LLM models, action weights, probabilities)
│   ├── personas.yaml              # Agent definitions (team, role, Jira account ID, behaviors)
│   ├── templates.yaml             # Comment templates (reduces LLM calls for routine actions)
│   └── .env.example               # Environment variable template
│
├── data/                          # Runtime data
│   ├── state.json                 # Current simulation state (persisted)
│   ├── logs.db                    # SQLite logging database
│   └── releases/                  # Generated release notes files (version.md, version.json, etc.)
│
├── docs/                          # Documentation
│   ├── plans/                     # Phase implementation plans
│   └── images/                    # Architecture diagrams
│
├── n8n/                           # n8n workflow definitions
│   └── workflows/                 # Exported n8n workflows
│
├── .planning/                     # GSD planning documents (generated)
│   └── codebase/                  # Codebase analysis docs (ARCHITECTURE.md, STRUCTURE.md, etc.)
│
├── Dockerfile                     # Docker image definition
├── docker-compose.yml             # Docker Compose for full stack
├── requirements.txt               # Python dependencies
├── pytest.ini                     # Pytest configuration
├── pyproject.toml                 # Python project metadata
├── CLAUDE.md                      # Claude Code project instructions
└── README.md                      # Project overview
```

## Directory Purposes

**`src/`:**
- Purpose: All backend Python code
- Contains: FastAPI app, orchestration logic, integrations, state management
- Key files: `main.py` (entry point), `orchestrator/orchestrator.py` (core logic)

**`src/orchestrator/`:**
- Purpose: Simulation orchestration and decision making
- Contains: Three-phase tick logic (Analyzer → Planner → Executor)
- Key files:
  - `orchestrator.py`: Main coordinator
  - `analyzer.py`: Rules-based opportunity detection
  - `planner.py`: LLM-driven action planning
  - `pathfinder.py`: Scenario script generation

**`src/agents/`:**
- Purpose: Legacy agent implementations (mostly superseded by crews)
- Contains: BaseAgent, individual agent role implementations
- Key files: `base_agent.py` (abstract base), role implementations

**`src/crews/`:**
- Purpose: CrewAI-based execution teams handling specific scenario types
- Contains: One crew per scenario type (lifecycle, blocker, rework, scope_creep, dependency, sprint_planning)
- Key files:
  - `base_crew.py`: Common crew functionality
  - `ticket_lifecycle_crew.py`: Handles normal workflow progression
  - `blocker_crew.py`: Handles blocking issues
  - `rework_crew.py`: Handles QA rejections and fixes
  - `sprint_planning_crew.py`: Handles sprint planning and releases

**`src/services/`:**
- Purpose: External service integrations
- Contains: JiraClient (Jira API wrapper), LLMService (Anthropic routing)
- Key files:
  - `jira_client.py`: All Jira REST API calls
  - `llm_service.py`: LLM routing, content generation

**`src/tools/`:**
- Purpose: High-level Jira operations exposed to CrewAI agents
- Contains: JiraTools (wrapped operations), ContextTools
- Key files: `jira_tools.py` (agent-facing API)

**`src/state/`:**
- Purpose: State management and persistence
- Contains: Pydantic models, save/load logic, migration helpers, state sync
- Key files:
  - `models.py`: All state models (SimulationState, ActiveScenario, AgentState, SprintScenario, ReleaseState, etc.)
  - `simulation_state.py`: Persistence and helper functions

**`src/scenarios/`:**
- Purpose: Sprint-level scenario management
- Contains: SprintScenario class with scripted events
- Key files: `sprint_scenario.py` (scenario definition), `script_executor.py` (event execution)

**`src/logging/`:**
- Purpose: Comprehensive observability
- Contains: SQLite database, async log writing, CrewAI integration, query APIs
- Key files:
  - `writer.py`: AsyncLogWriter (core logging)
  - `database.py`: LogDatabase (persistence)
  - `crewai_callbacks.py`: CrewAI integration hooks
  - `api.py`: Logging API routes

**`frontend/src/`:**
- Purpose: React 19 TypeScript frontend
- Contains: Components, pages, stores, hooks, types
- Key subdirectories:
  - `pages/`: Full page components (Dashboard, Chat, Releases, Settings)
  - `components/`: Reusable UI components organized by area
  - `store/`: Zustand state stores
  - `hooks/`: Custom React hooks (useApi, etc.)
  - `lib/`: Utilities and API client
  - `types/`: TypeScript type definitions

**`config/`:**
- Purpose: Simulation configuration
- Contains: YAML files for settings, personas, templates
- Key files:
  - `settings.yaml`: LLM models, probabilities, scenario distribution targets
  - `personas.yaml`: Agent definitions with team, role, Jira account ID
  - `templates.yaml`: Pre-written comment templates (reduces LLM cost)

**`data/`:**
- Purpose: Runtime data storage
- Contains: Persistent state, logs, release notes
- Key files:
  - `state.json`: Current simulation state (loaded/saved per tick)
  - `logs.db`: SQLite database with comprehensive logging
  - `releases/`: Generated release notes (v1.0.0.md, v1.0.0.json, etc.)

## Key File Locations

**Entry Points:**
- `src/main.py`: FastAPI application root
  - Lines 269-274: FastAPI app creation
  - Lines 356-493: `/trigger` endpoint (main simulation trigger)
  - Lines 341-353: `/health` endpoint (status check)
  - Lines 496-523: `/state` endpoint (state export)

**Configuration:**
- `config/settings.yaml`: Simulation parameters
- `config/personas.yaml`: Agent definitions
- `config/templates.yaml`: Comment templates

**Core Logic:**
- `src/orchestrator/orchestrator.py`: Lines 159-348 (run_tick method)
- `src/orchestrator/analyzer.py`: Lines 72+ (analyze method)
- `src/orchestrator/planner.py`: Lines 72+ (plan_tick method)
- `src/state/models.py`: All Pydantic model definitions

**Testing:**
- `tests/`: Pytest test files (structure mirrored to src/)

## Naming Conventions

**Files:**
- Snake_case: `ticket_lifecycle_crew.py`, `jira_client.py`, `simulation_state.py`
- Module-level: `__init__.py` for package exports
- Tests: `test_*.py` or `*_test.py` (pytest convention)

**Directories:**
- Lowercase plural: `src/crews/`, `src/agents/`, `src/services/`, `frontend/src/components/`
- Functional grouping: By concern (agents, crews, services) or domain (orchestrator, logging, scenarios)

**Classes:**
- PascalCase: `ScenarioOrchestrator`, `ActiveScenario`, `JiraClient`, `SprintScenario`
- Abstract base classes: Prefix with `Base` (BaseAgent, BaseCrew)
- Enums: `ScenarioType`, `ScenarioPhase`, `TicketComplexity`

**Functions:**
- snake_case: `load_state()`, `save_state()`, `get_active_sprint()`, `run_tick()`
- Private functions: Prefix with `_` (e.g., `_analyze()`, `_execute_action()`)
- Async functions: Use `async def`, named as regular functions (no special prefix)

**Variables:**
- snake_case: `scenario_id`, `ticket_key`, `agent_id`, `state_dict`
- Constants: UPPER_CASE (e.g., `BOARD_ID = 4`)
- Private: Prefix with `_` (e.g., `_status_cache`)

**TypeScript/Frontend:**
- PascalCase for types: `type Agent`, `interface Sprint`, `type ScenarioArchetype`
- camelCase for variables: `assignedTickets`, `sprintNumber`, `issueType`
- snake_case for API responses (then transform to camelCase in transformers.ts)

## Where to Add New Code

**New Feature (Backend):**
- Primary code: `src/orchestrator/` (if orchestration logic) or `src/services/` (if external integration)
- Tests: `tests/orchestrator/` or `tests/services/`
- Config: Add settings to `config/settings.yaml` if needed

**New Crew/Scenario Type:**
- Implementation: `src/crews/` (e.g., `new_scenario_crew.py`)
- Register in: `src/orchestrator/orchestrator.py` (lines 88-96 for initialization, lines 576-1403 for routing)
- Model update: `src/state/models.py` (add scenario type if needed)

**New Component (Frontend):**
- Location: `frontend/src/components/` (organize by domain: common, dashboard, chat)
- Types: Update `frontend/src/types/index.ts`
- Store: Add to appropriate Zustand store in `frontend/src/store/` or create new

**New API Endpoint:**
- Location: `src/main.py` (add route decorated with `@app.get()` or `@app.post()`)
- Documentation: Add docstring and response model (Pydantic BaseModel)
- Response format: Use snake_case in Python, transform to camelCase in transformers.ts if needed

**Utilities:**
- Shared helpers: `src/` root level (e.g., `utils.py`)
- Frontend helpers: `frontend/src/lib/` (e.g., `transformers.ts` for data transformation)

## Special Directories

**`data/`:**
- Purpose: Runtime data storage
- Generated: Yes (created on first run if missing)
- Committed: No (gitignored, persisted across restarts)

**`frontend/dist/`:**
- Purpose: Built production frontend files
- Generated: Yes (built during Docker image creation)
- Committed: No (generated by `npm run build`)

**`.planning/codebase/`:**
- Purpose: GSD mapping documents (this file and related docs)
- Generated: Yes (created by `/gsd:map-codebase` command)
- Committed: Yes (checked into repo for reference)

**`n8n/workflows/`:**
- Purpose: n8n automation workflow definitions
- Generated: No (manually created in n8n UI and exported)
- Committed: Yes (used to set up scheduling)

---

*Structure analysis: 2026-01-27*
