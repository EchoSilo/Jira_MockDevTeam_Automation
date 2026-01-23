# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Jira Team Simulator - a multi-agent system that generates realistic development team activity in Jira for productivity analytics testing. Simulates 9 agents across 2 teams performing actions like status transitions, comments, story creation, and work logging.

## Common Commands

```bash
# Backend setup
pip install -r requirements.txt

# Run backend locally
uvicorn src.main:app --reload

# Run tests
pytest tests/ -v

# Frontend setup
cd frontend
npm install

# Run frontend dev server
npm run dev

# Build frontend for production
npm run build

# Build and run entire stack with Docker
docker-compose up --build
```

## Docker Deployment

The application runs in Docker in production. **After making code changes, you must rebuild and restart the container:**

```bash
# Rebuild and restart (recommended after code changes)
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Quick restart (if only config changes, no code)
docker-compose restart

# View logs
docker-compose logs -f jira-simulator
```

The Docker build includes both frontend (built during image creation) and backend. Changes to `src/`, `frontend/src/`, or `config/` require a rebuild.

## Architecture

```
                                    ┌─────────────────────┐
                                    │  React Frontend     │
                                    │  (Dashboard, Chat)  │
                                    └──────────┬──────────┘
                                               │ HTTP
                                               ↓
n8n (cron scheduler) → POST /trigger → FastAPI Backend
                                          │      ↓
                                Orchestrator  JiraClient
                                   ↓              ↓
                                Agents ────→ Jira API
                                   ↓
                            State (data/state.json)
```

**Frontend to Backend:**
- React frontend at `http://localhost:5173` (dev) or served from backend in production
- REST API calls to backend (`http://localhost:8000/api/*`)
- 15-second polling for real-time dashboard updates
- WebSocket for interactive chat features

**Key flow:**
1. n8n triggers `/trigger` endpoint on schedule (every ~45 min, M-F, 9-5)
2. `main.py` loads state, determines random intensity (light/normal/busy)
3. `Orchestrator` selects 2-5 agents based on intensity and activity levels
4. Each agent's `act()` method: `select_action()` → `execute_action()` → record to state
5. Agents use `JiraClient` for API calls and `LLMService` for generating content

**Agent hierarchy:**
- `BaseAgent` (abstract): Common interface with `should_act()`, `act()`, template selection
- `PMAgent`: Creates stories, prioritizes backlog
- `DeveloperAgent`: Picks up tasks, transitions status, logs work
- `QAAgent`: Tests tickets, files bugs, rejects/approves work
- `TechLeadAgent`: Architectural reviews, code review comments

**LLM routing:**
- `LLMService` routes to Haiku (routine actions) or Sonnet (complex actions like story creation)
- Complex actions defined in `config/settings.yaml` under `llm.complex_actions`

**Process Adherence:**
- Issue type permissions: Devs/QA/Tech Leads work on Stories, Bugs, Tasks only. Epics are PM-only.
- Sprint integration: Items must be in active sprint to be worked on (Board ID: 4)
- Epic lifecycle: Epic status syncs with children; Epics auto-assigned to team PMs
- Sprint planning: PMs plan 7-day sprints on Mondays; maintains 1-2 future sprints
- Violation cleanup: Gradually fixes process violations with explanatory comments

## Detailed Architecture Reference

**IMPORTANT:** For complex debugging, feature development, or understanding execution flow, refer to `ARCHITECTURE.md`. It contains:

- **Execution Flow Diagrams**: Step-by-step sequence of `/trigger` endpoint
- **State Machine Diagrams**: Sprint lifecycle, scenario phase transitions
- **Dependency Graph**: What depends on what for correct operation
- **Critical Invariants**: Conditions that must always be true
- **Known Edge Cases**: Common failure scenarios and their causes
- **Quick Debugging Reference**: Checklist for common issues

Always consult `ARCHITECTURE.md` when:
- Modifying sprint lifecycle logic
- Changing state synchronization
- Debugging "state out of sync" issues
- Adding new detection/completion mechanisms

## Configuration

- `config/settings.yaml`: Simulation parameters, LLM models, action weights, cycle times
- `config/personas.yaml`: Agent definitions with Jira account IDs, personas, behaviors
- `config/templates.yaml`: Comment templates for routine actions (reduces LLM costs)

## Environment Variables

Required in `.env`:
```
JIRA_URL=https://yoursite.atlassian.net
JIRA_EMAIL=your-email@domain.com
JIRA_API_TOKEN=your-api-token
PROJECT_KEY=YOUR_PROJECT_KEY
ANTHROPIC_API_KEY=your-anthropic-api-key
```

## API Endpoints

### Simulation Control

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check and Jira connectivity |
| `/trigger` | POST | Run one simulation tick |
| `/state` | GET | View current simulation state |
| `/reset` | POST | Reset simulation state |

### Agent & Activity

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/agents` | GET | List configured agents |
| `/scenarios` | GET | List active scenarios |

### Observability

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/logs/viewer` | GET | HTML log viewer UI |
| `/logs/sessions` | GET | List simulation sessions |
| `/logs/stats` | GET | Token usage statistics |

### Frontend Integration

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/dashboard` | GET | Combined data for dashboard (state + agents + scenarios) |
| `/api/dashboard?team=alpha` | GET | Filter by team (alpha or beta) |
| `/ws/chat` | WebSocket | Chat interface with PMs |

## Frontend

**Location:** `frontend/` directory

**Tech Stack:**
- React 19 with TypeScript
- Vite for bundling
- TailwindCSS + Radix UI for styling
- Zustand for state management
- Recharts for visualizations
- React Router for navigation

**Key Directories:**
- `src/pages/` - Page components (Dashboard, Chat, Settings)
- `src/components/` - Reusable components (common, dashboard, chat)
- `src/store/` - Zustand stores (theme, dashboard, chat)
- `src/hooks/` - Custom hooks for data fetching
- `src/lib/` - Utilities and transformers

**Running Frontend:**
```bash
cd frontend
npm install           # First time only
npm run dev          # Dev server at http://localhost:5173
npm run build        # Production build
npm run lint         # Check code quality
```

**Features:**
- Real-time dashboard with 15s auto-refresh
- Interactive PM chat interface
- Team filtering (Alpha/Beta)
- Light/dark theme support
- Responsive design
- Error boundaries for backend unavailability

## State Management

State persists to `data/state.json`. Tracks:
- Last run timestamp, simulation day, current sprint
- Per-agent: last action time, daily action count, assigned tickets
- Active tickets with status and timing
- Recent actions log

State resets daily counters and advances sprint day automatically on new day detection.
