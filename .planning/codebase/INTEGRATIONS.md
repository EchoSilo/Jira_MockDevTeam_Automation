# External Integrations

**Analysis Date:** 2026-01-27

## APIs & External Services

**Jira Cloud/Server:**
- What: Issue tracking and project management
- SDK/Client: `jira` Python package (3.6.0+)
- Auth: Basic auth with email + API token (from `JIRA_EMAIL`, `JIRA_API_TOKEN`)
- Endpoints: REST API for issue CRUD, workflow transitions, sprint operations, board queries
- Configuration: `JIRA_URL` (instance URL), `PROJECT_KEY` (Jira project key)

**Large Language Models:**
- Anthropic Claude (primary): Used via direct SDK or LiteLLM wrapper
  - SDK/Client: `anthropic` (0.40.0+) for direct access
  - Auth: `ANTHROPIC_API_KEY`
  - Models: Configured in `config/settings.yaml` (`llm.routine_model`, `llm.complex_model`)
  - Current: `gemini/gemini-2.5-flash-lite` (can be changed)

- OpenRouter (optional): Multi-model provider
  - SDK/Client: LiteLLM abstraction
  - Auth: `OPENROUTER_API_KEY`
  - Models: Supports 100+ models (Claude, GPT-4, Llama, etc.)

- OpenAI (optional): Direct OpenAI API
  - SDK/Client: LiteLLM abstraction
  - Auth: `OPENAI_API_KEY`

- Google Gemini (optional): Google's LLM
  - SDK/Client: LiteLLM abstraction
  - Auth: `GOOGLE_API_KEY`

**CrewAI Framework:**
- What: Multi-agent orchestration and collaboration
- Role: Manages agent hierarchy, task coordination, tool execution
- Package: `crewai` (0.80.0+), `crewai-tools` (0.14.0+)

## Data Storage

**State Persistence:**
- Type: File system (JSON)
- Connection: Local file at `data/state.json`
- Format: SimulationState JSON containing agent workloads, active scenarios, sprint data
- Client: Python pathlib and json standard library

**Logging:**
- Type: SQLite database
- Connection: Local file at `data/logs.db`
- Client: Python sqlite3 standard library via `src/logging/database.py`
- Schema: Tables for sessions, LLM calls, Jira API calls, agent decisions, orchestrator logs
- Retention: Configurable in `config/settings.yaml` (`logging.retention_days`)

**File Storage:**
- Type: Local filesystem only
- Usage: State files, config files, generated documents (Word/PowerPoint)
- Generated artifacts: Release notes (Word), release presentations (PowerPoint)

**Caching:**
- In-memory caching for Jira status lists (TTL: 1 hour)
- HTTP response caching for dashboard data (TTL: 5 seconds)
- Jira connection health check caching (TTL: 60 seconds)

## Authentication & Identity

**Auth Provider:**
- Type: Custom (no centralized auth service)
- Approach: Direct Jira API token authentication
  - Each agent action authenticates directly to Jira with shared credentials
  - Agents identified by persona in `config/personas.yaml`, not separate user accounts

**Jira Integration:**
- Authentication: Email + API token (Basic Auth)
- Audience: Simulated agent activity tied to team member identities configured in personas
- Agent-to-Jira mapping: Configured in `config/personas.yaml` with Jira account IDs

## Monitoring & Observability

**Error Tracking:**
- Type: Local logging (no external error tracking service)
- Implementation: Python logging module + SQLite log database
- Severity levels: Captured in `src/logging/database.py`

**Logs:**
- Approach: Multi-layered local logging
- Destination: SQLite database (`data/logs.db`) + Python logging handlers
- Coverage:
  - LLM API calls: Prompts, responses, token usage, latency
  - Jira API calls: Endpoint, status, payload, timing
  - Agent decisions: Reasoning, action selection, outcome
  - Orchestrator planning: Scenario injection, agent selection logic
  - Session metadata: Tick ID, simulation day, sprint number, intensity

**Dashboard/Monitoring:**
- Frontend: Real-time dashboard polling `/api/dashboard` every 15 seconds
- Log viewer: HTML UI at `/logs/viewer` with SQL query interface
- Log statistics: Token usage stats at `/logs/stats`
- Session browser: List and drill-down into sessions at `/logs/sessions`

## CI/CD & Deployment

**Hosting:**
- Type: Docker container
- Platform: Any Docker-compatible environment (local, cloud, orchestration)
- Current: n8n network integration (external Docker network `n8n_default`)

**CI Pipeline:**
- Type: None detected
- Deployment: Manual Docker build and restart via Docker Compose

**Container Registry:**
- No external registry; builds locally via Dockerfile

## Webhook Configuration & n8n Integration

**Incoming Webhooks:**
- `POST /trigger` - Main entry point called by n8n scheduler
  - Caller: n8n (external scheduler)
  - Frequency: Configurable, approximately every 45 minutes (M-F, 9 AM-5 PM)
  - Response: `TriggerResponse` with action summary
  - Idempotent: Checks if already run this minute to prevent double-execution

**Outgoing Webhooks:**
- None detected
- All output is persistence to Jira and state files

## n8n Integration

**n8n Role:**
- Dumb scheduler/trigger only
- Calls `/trigger` endpoint on a cron schedule
- No business logic in n8n; all logic in FastAPI application

**Network:**
- Connects to `n8n_default` Docker network (external network defined in `docker-compose.yml`)
- Service name: `jira-simulator`

## Environment Configuration

**Required Environment Variables:**

| Variable | Purpose | Example |
|----------|---------|---------|
| `JIRA_URL` | Jira instance URL | `https://yoursite.atlassian.net` |
| `JIRA_EMAIL` | Jira API user email | `user@domain.com` |
| `JIRA_API_TOKEN` | Jira API authentication token | *(API token from Jira)* |
| `PROJECT_KEY` | Jira project key | `PROJ` |
| `ANTHROPIC_API_KEY` | Anthropic Claude API key | *(required if using Anthropic models)* |
| `OPENROUTER_API_KEY` | OpenRouter API key (optional) | *(only if using OpenRouter)* |
| `OPENAI_API_KEY` | OpenAI API key (optional) | *(only if using OpenAI)* |
| `GOOGLE_API_KEY` | Google Gemini API key (optional) | *(only if using Gemini)* |

**Configuration Files:**

| File | Purpose |
|------|---------|
| `.env` | Runtime environment variables |
| `config/settings.yaml` | Simulation parameters, LLM models, cycle times, sprint config |
| `config/personas.yaml` | Agent definitions and team assignments |
| `config/templates.yaml` | Routine comment templates (reduces LLM token usage) |

**Secrets Location:**
- `.env` file (not committed; use `.env.example` as template)
- Should be rotated and protected in production
- Docker: Environment variables passed via `docker-compose.yml` from host `.env`

## Model Selection

**LLM Routing:**
- Configured in `config/settings.yaml` under `llm` section
- Format: `provider/model-name` (e.g., `anthropic/claude-3-5-sonnet`, `gemini/gemini-2.5-flash-lite`)
- Routine model: Used for standard comments, status updates
- Complex model: Used for story creation, architecture discussions, scenario planning
- LiteLLM abstraction: Transparently routes to correct provider based on prefix

## External Service Dependencies Summary

| Service | Type | Criticality | Fallback |
|---------|------|-------------|----------|
| Jira API | Required | Critical | None; app cannot run without Jira |
| LLM API | Required | Critical | None; agents need LLM for content generation |
| n8n | Optional | Not critical | Manual `/trigger` calls via curl/Postman |

---

*Integration audit: 2026-01-27*
