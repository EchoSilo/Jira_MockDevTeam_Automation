# Jira Team Simulator

A multi-agent simulation system that generates realistic development team activity in Jira for productivity analytics testing.

## Overview

This tool simulates two development teams (9 agents total) working on a Jira project, generating:
- Status transitions
- Contextual comments (LLM-generated)
- New stories and bugs
- Work logs
- Realistic team dynamics (blockers, QA rejections, cross-team dependencies)

## Architecture

```
n8n (scheduler) → FastAPI endpoint → Orchestrator → Agents → Jira API
                                          ↓
                                    State (JSON)
```

## Quick Start

### 1. Configure Environment

Copy `.env.example` to `.env` and fill in:

```bash
JIRA_URL=https://yoursite.atlassian.net
JIRA_EMAIL=your-email@domain.com
JIRA_API_TOKEN=your-api-token
PROJECT_KEY=YOUR_PROJECT_KEY
ANTHROPIC_API_KEY=your-anthropic-api-key
```

### 2. Configure Agent Accounts

Edit `config/personas.yaml` and replace `jira_account_id` for each agent with actual Jira account IDs from your 9 user accounts.

### 3. Build and Run

```bash
docker-compose up --build
```

The API will be available at `http://localhost:8000`

### 4. Configure n8n Trigger

Create a workflow in n8n:
1. **Cron Node**: `0 */45 9-17 * * 1-5` (every ~45 min, M-F, 9-5)
2. **HTTP Request Node**: POST to `http://jira-simulator:8000/trigger`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check and Jira connectivity |
| `/trigger` | POST | Run one simulation tick |
| `/state` | GET | View current simulation state |
| `/reset` | POST | Reset simulation state |
| `/agents` | GET | List configured agents |

### Trigger Request Body

```json
{
  "intensity": "normal",  // "light", "normal", or "busy"
  "force_agents": null    // Optional: ["alpha_pm", "beta_dev_senior"]
}
```

## Team Structure

### Team Alpha (5 agents)
- **Sarah Chen** - PM
- **Marcus Johnson** - Tech Lead
- **Elena Rodriguez** - Senior Developer
- **James Park** - Mid Developer
- **Priya Sharma** - QA

### Team Beta (4 agents)
- **David Kim** - PM
- **Ana Costa** - Senior Developer
- **Tyler Brooks** - Junior Developer
- **Rachel Green** - QA

## Configuration

### settings.yaml
- Work hours and timezone
- Agents per tick (min/max)
- Action weights
- Cycle time targets
- LLM model selection

### personas.yaml
- Agent definitions
- Jira account mappings
- Personality descriptions
- Behavior lists

### templates.yaml
- Comment templates for routine actions
- Reduces LLM costs for simple actions

## Cost Estimation

- **LLM**: ~$0.50-1.50/day (Haiku for routine, Sonnet for complex)
- **Jira**: Free tier (10 users)
- **Infrastructure**: Docker on local machine

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
uvicorn src.main:app --reload

# Run tests
pytest tests/ -v
```

## License

MIT
