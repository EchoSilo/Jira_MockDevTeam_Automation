# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Jira Team Simulator - a multi-agent system that generates realistic development team activity in Jira for productivity analytics testing. Simulates 9 agents across 2 teams performing actions like status transitions, comments, story creation, and work logging.

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
uvicorn src.main:app --reload

# Run tests
pytest tests/ -v

# Build and run with Docker
docker-compose up --build
```

## Architecture

```
n8n (cron scheduler) → POST /trigger → FastAPI → Orchestrator → Agents → Jira API
                                                      ↓
                                              State (data/state.json)
```

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

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check and Jira connectivity |
| `/trigger` | POST | Run one simulation tick |
| `/state` | GET | View current simulation state |
| `/reset` | POST | Reset simulation state |
| `/agents` | GET | List configured agents |

## State Management

State persists to `data/state.json`. Tracks:
- Last run timestamp, simulation day, current sprint
- Per-agent: last action time, daily action count, assigned tickets
- Active tickets with status and timing
- Recent actions log

State resets daily counters and advances sprint day automatically on new day detection.
