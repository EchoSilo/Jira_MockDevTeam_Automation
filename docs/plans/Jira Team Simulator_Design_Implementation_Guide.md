# Jira Team Simulator - Design & Implementation Plan

## Overview

A multi-agent simulation system that generates realistic development team activity in Jira for productivity analytics testing. Uses CrewAI for agent orchestration, triggered by n8n on a schedule.

## Key Decisions

| Aspect | Choice |
|--------|--------|
| Goal | Pattern realism with natural scenario coverage |
| Comments | Hybrid (templates for routine, LLM for substantive) |
| Team structure | 2 teams (4-5 agents each), 9 total agents |
| Stack | CrewAI (Python) + n8n as trigger only |
| Deployment | Docker container on shared n8n network |
| Jira approach | Mixed realistic - work existing backlog + create new |
| LLM | Claude Haiku for routine, Sonnet for complex |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     n8n (existing)                       │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Cron: M-F, every 30-60 min during work hours   │    │
│  │  → HTTP POST to jira-simulator:8000/trigger     │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│              Docker: jira-simulator                      │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │   FastAPI    │  │  Orchestrator│  │    Agents    │   │
│  │  /trigger    │──│  (who acts)  │──│  (CrewAI)    │   │
│  └──────────────┘  └──────────────┘  └──────────────┘   │
│                           │                 │           │
│                           ▼                 ▼           │
│                    ┌──────────────┐  ┌──────────────┐   │
│                    │    State     │  │  Jira Tools  │   │
│                    │  (JSON file) │  │  (API calls) │   │
│                    └──────────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## Team Structure

### Team Alpha (5 agents)
| Role | Persona Name | Behavior |
|------|--------------|----------|
| PM | Sarah Chen | Strategic, concise, data-informed |
| Tech Lead | Marcus Johnson | Architectural focus, reviews code approach |
| Senior Dev | Elena Rodriguez | Fast, clean code, brief comments |
| Mid Dev | James Park | Thorough, asks questions, detailed comments |
| QA | Priya Sharma | Detail-oriented, specific test scenarios |

### Team Beta (4 agents)
| Role | Persona Name | Behavior |
|------|--------------|----------|
| PM | David Kim | Metrics-focused, roadmap driver |
| Senior Dev | Ana Costa | Mentoring style, educational comments |
| Junior Dev | Tyler Brooks | Slower, learning, needs occasional rework |
| QA | Rachel Green | Automation-focused, coverage references |

---

## Activity Patterns

### Trigger Frequency
- n8n cron: Every 30-60 minutes, M-F, 9am-5pm
- Each trigger: 2-5 agents take actions (randomized)
- Not every agent acts every tick

### Action Distribution
| Action | Frequency | LLM? |
|--------|-----------|------|
| Status transitions | High | No (template) |
| Assignment changes | Medium | No |
| Simple comments | Medium | Template + variance |
| Substantive comments | Medium | Yes (Haiku) |
| Create new tickets | Low | Yes (Sonnet) |
| Link tickets | Low | No |
| Log work time | Medium | No |

### Realistic Scenarios (emerge naturally)
- Blocked tickets with blocker comments
- QA rejections bouncing tickets back
- PM adding scope mid-sprint
- Developer overload (5+ assigned items)
- Cross-team dependencies

### Cycle Time Targets
- Bugs: 1-3 days
- Stories: 3-7 days
- Complex features: 1-2 weeks
- Some tickets stall (friction)

---

## Project Structure

```
jira-team-simulator/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
├── config/
│   ├── settings.yaml           # Jira project, timing config
│   ├── personas.yaml           # Agent definitions
│   └── templates.yaml          # Comment templates
├── src/
│   ├── main.py                 # FastAPI app with /trigger endpoint
│   ├── orchestrator.py         # Decides who acts, what actions
│   ├── agents/
│   │   ├── base_agent.py       # CrewAI agent base
│   │   ├── pm_agent.py         # PM behaviors
│   │   ├── developer_agent.py  # Dev behaviors
│   │   ├── qa_agent.py         # QA behaviors
│   │   └── tech_lead_agent.py  # Tech lead behaviors
│   ├── tools/
│   │   ├── jira_tools.py       # CrewAI tools for Jira actions
│   │   └── context_tools.py    # Fetch ticket context
│   ├── services/
│   │   ├── jira_client.py      # Jira API wrapper
│   │   └── llm_service.py      # LLM calls (Haiku/Sonnet routing)
│   └── state/
│       └── simulation_state.py # Load/save state
├── data/
│   └── state.json              # Persisted simulation state
└── tests/
    └── test_orchestrator.py
```

---

## Configuration Files

### settings.yaml
```yaml
jira:
  project_key: "YOUR_PROJECT"
  base_url: "https://yoursite.atlassian.net"

simulation:
  work_hours:
    start: 9
    end: 17
    timezone: "America/New_York"
  agents_per_tick:
    min: 2
    max: 5

llm:
  routine_model: "claude-3-haiku-20240307"
  complex_model: "claude-sonnet-4-20250514"
```

### personas.yaml
```yaml
agents:
  alpha_pm:
    jira_account_id: "abc123"
    display_name: "Sarah Chen"
    team: "alpha"
    role: "pm"
    persona: |
      Strategic product thinker. Writes concise, clear tickets.
      Focuses on user value and measurable outcomes.
      Communication style: Direct, uses bullet points.
    behaviors:
      - create_stories
      - prioritize_backlog
      - add_acceptance_criteria
      - comment_on_blockers

  alpha_dev_senior:
    jira_account_id: "def456"
    display_name: "Elena Rodriguez"
    team: "alpha"
    role: "developer"
    seniority: "senior"
    persona: |
      10 years experience. Values clean, maintainable code.
      Fast executor, prefers action over discussion.
      Communication style: Brief, technical, to the point.
    behaviors:
      - pick_up_tasks
      - transition_status
      - add_technical_comments
      - log_work
```

---

## State Management

### state.json structure
```json
{
  "last_run": "2025-12-15T14:30:00Z",
  "simulation_day": 12,
  "current_sprint": {
    "name": "Sprint 23",
    "day": 4,
    "total_days": 10
  },
  "agents": {
    "alpha_pm": {
      "last_action": "2025-12-15T10:15:00Z",
      "actions_today": 3,
      "assigned_tickets": []
    },
    "alpha_dev_senior": {
      "last_action": "2025-12-15T14:30:00Z",
      "actions_today": 5,
      "assigned_tickets": ["PROJ-101", "PROJ-105"]
    }
  },
  "active_tickets": {
    "PROJ-101": {
      "assigned_to": "alpha_dev_senior",
      "status": "In Progress",
      "started": "2025-12-13",
      "blocked": false,
      "comments_count": 3
    }
  },
  "recent_actions": [
    {"agent": "alpha_dev_senior", "action": "comment", "ticket": "PROJ-101", "time": "2025-12-15T14:30:00Z"}
  ]
}
```

---

## Docker Setup

### docker-compose.yml
```yaml
version: '3.8'

services:
  jira-simulator:
    build: .
    container_name: jira-simulator
    ports:
      - "8000:8000"
    environment:
      - JIRA_URL=${JIRA_URL}
      - JIRA_EMAIL=${JIRA_EMAIL}
      - JIRA_API_TOKEN=${JIRA_API_TOKEN}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    volumes:
      - ./data:/app/data
      - ./config:/app/config
    networks:
      - n8n_default
    restart: unless-stopped

networks:
  n8n_default:
    external: true
```

### Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY config/ ./config/

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## n8n Workflow

Simple 2-node workflow:

1. **Cron Node**
   - Expression: `0 */45 9-17 * * 1-5` (roughly every 45 min, M-F, 9-5)

2. **HTTP Request Node**
   - Method: POST
   - URL: `http://jira-simulator:8000/trigger`
   - Body: `{ "intensity": "normal" }`

---

## API Endpoint

### POST /trigger
```python
@app.post("/trigger")
async def trigger_simulation(request: TriggerRequest):
    """
    Called by n8n to run one simulation tick.
    Returns summary of actions taken.
    """
    state = load_state()
    jira = JiraClient()

    # Sync with actual Jira state
    state = sync_jira_state(state, jira)

    # Orchestrator picks agents and actions
    actions = orchestrator.plan_tick(state, request.intensity)

    # Execute actions
    results = []
    for action in actions:
        agent = get_agent(action.agent_id)
        result = await agent.execute(action, jira, state)
        results.append(result)

    save_state(state)

    return {"actions_taken": len(results), "details": results}
```

---

## Implementation Tasks

### Phase 1: Foundation
1. Create project structure and Docker setup
2. Implement Jira client with authentication
3. Create FastAPI app with /trigger endpoint
4. Implement state management (load/save)

### Phase 2: Core Agents
5. Build base CrewAI agent class
6. Implement PM agent with story creation
7. Implement Developer agent with status transitions
8. Implement QA agent with testing workflow
9. Implement Tech Lead agent

### Phase 3: Orchestration
10. Build orchestrator logic (who acts, what actions)
11. Implement action selection based on state
12. Add randomization for realistic patterns

### Phase 4: LLM Integration
13. Create LLM service with Haiku/Sonnet routing
14. Build prompt templates for each action type
15. Implement comment generation

### Phase 5: Polish & Deploy
16. Add comment templates for routine actions
17. Configure personas in YAML
18. Set up n8n workflow
19. Test end-to-end simulation
20. Deploy and monitor

---

## Setup Requirements

### Jira Setup (manual)
- Create 9 user accounts in Jira free plan
- Note account IDs for each
- Ensure all accounts have access to target project

### Environment Variables
```
JIRA_URL=https://yoursite.atlassian.net
JIRA_EMAIL=your-email@domain.com
JIRA_API_TOKEN=your-api-token
ANTHROPIC_API_KEY=your-api-key
```

### n8n Network
Ensure Docker network name matches your n8n setup (commonly `n8n_default`)

---

## Estimated Costs

- **LLM usage**: ~$0.50-1.50/day (20-30 calls, mix of Haiku/Sonnet)
- **Jira**: Free tier (10 users)
- **Infrastructure**: Docker on local machine (free) or ~$5/month cloud VM

---

## Success Criteria

- [ ] Realistic activity patterns visible in Jira
- [ ] Cycle time variance across ticket types
- [ ] Cross-team interactions (dependencies, comments)
- [ ] Blocked tickets and rework scenarios
- [ ] Velocity differences between teams
- [ ] No obvious "bot" patterns in comments
