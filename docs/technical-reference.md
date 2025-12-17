# Technical Reference

Complete reference for API endpoints, configuration files, and state management.

---

## API Endpoints

Base URL: `http://localhost:8000`

### Core Endpoints

#### `GET /health`

Health check and Jira connectivity status.

**Response:**
```json
{
  "status": "healthy",
  "jira_connected": true,
  "last_run": "2024-01-15T14:30:00",
  "simulation_day": 5
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `"healthy"` or `"degraded"` |
| `jira_connected` | boolean | Whether Jira API is reachable |
| `last_run` | string (ISO) | Timestamp of last trigger |
| `simulation_day` | integer | Days since simulation started |

---

#### `POST /trigger`

Main endpoint to run one simulation tick. Called by n8n scheduler.

**Response:**
```json
{
  "success": true,
  "actions_taken": 3,
  "actions_planned": 4,
  "intensity": "normal",
  "analysis_summary": {
    "board_state": {
      "backlog": 5,
      "in_progress": 3,
      "in_review": 2,
      "in_testing": 1
    },
    "opportunities_found": 6
  },
  "planning_reasoning": "Two scenarios ready to advance. Tyler has capacity.",
  "actions": [
    {
      "type": "qa_approve",
      "ticket_key": "PROJ-38",
      "agent_id": "alpha_qa",
      "agent_name": "Priya Sharma",
      "success": true
    }
  ],
  "errors": [],
  "active_scenarios": 8,
  "simulation_day": 5,
  "sprint": "Sprint 3",
  "tick_start": "2024-01-15T14:30:00",
  "tick_end": "2024-01-15T14:30:45"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | True if no errors occurred |
| `actions_taken` | integer | Actions successfully completed |
| `actions_planned` | integer | Actions the LLM planned |
| `intensity` | string | `"light"`, `"normal"`, or `"busy"` |
| `analysis_summary` | object | Board state and opportunities |
| `planning_reasoning` | string | LLM's explanation of decisions |
| `actions` | array | Details of each action |
| `errors` | array | Any errors that occurred |
| `active_scenarios` | integer | In-flight ticket scenarios |
| `simulation_day` | integer | Days since start |
| `sprint` | string | Current sprint name |
| `tick_start` / `tick_end` | string | Tick timing |

---

#### `GET /state`

View current simulation state (for debugging).

**Response:**
```json
{
  "last_run": "2024-01-15T14:30:00",
  "simulation_day": 5,
  "current_sprint": {
    "sprint_number": 3,
    "sprint_day": 8,
    "name": "Sprint 3"
  },
  "active_scenarios": {
    "scenario_abc123": {
      "ticket_key": "PROJ-42",
      "scenario_type": "normal_flow",
      "current_phase": "in_review",
      "assigned_agent": "alpha_dev_senior"
    }
  },
  "agent_states": {
    "alpha_dev_senior": {
      "daily_action_count": 3,
      "current_workload": 2,
      "assigned_tickets": ["PROJ-42", "PROJ-45"]
    }
  },
  "scenario_distribution": {
    "normal_flow": 6,
    "blocker": 1,
    "rework": 1
  }
}
```

---

#### `GET /scenarios`

View active scenarios and their status.

**Response:**
```json
{
  "active_count": 8,
  "scenarios": [
    {
      "id": "scenario_abc123",
      "ticket_key": "PROJ-42",
      "scenario_type": "normal_flow",
      "current_phase": "in_review",
      "assigned_agent": "alpha_dev_senior",
      "complexity": "story",
      "is_blocked": false,
      "blocker_reason": null,
      "is_rejected": false,
      "rejection_reason": null,
      "rework_count": 0,
      "started_at": "2024-01-13T10:00:00",
      "target_end": "2024-01-17T10:00:00"
    }
  ],
  "distribution": {
    "normal_flow": 6,
    "blocker": 1,
    "rework": 1
  }
}
```

---

#### `POST /reset`

Reset simulation state (clears all history).

**Response:**
```json
{
  "message": "State reset successfully"
}
```

**Warning:** This clears all active scenarios and history. Use for testing only.

---

#### `GET /agents`

List configured agents and their current state.

**Response:**
```json
{
  "agents": [
    {
      "id": "alpha_pm",
      "name": "Sarah Chen",
      "team": "alpha",
      "role": "pm",
      "assigned_tickets": [],
      "current_workload": 0,
      "daily_actions": 2
    },
    {
      "id": "alpha_dev_senior",
      "name": "Elena Rodriguez",
      "team": "alpha",
      "role": "developer",
      "assigned_tickets": ["PROJ-42", "PROJ-45"],
      "current_workload": 2,
      "daily_actions": 4
    }
  ]
}
```

---

### Logging Endpoints

#### `GET /logs/sessions`

List simulation sessions.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 20 | Max results |
| `offset` | integer | 0 | Pagination offset |
| `start_date` | string (ISO) | null | Filter by date |
| `end_date` | string (ISO) | null | Filter by date |

**Response:**
```json
{
  "sessions": [
    {
      "session_id": "sess_abc123",
      "started_at": "2024-01-15T14:30:00",
      "ended_at": "2024-01-15T14:30:45",
      "intensity": "normal",
      "simulation_day": 5,
      "sprint_day": 8,
      "sprint_number": 3,
      "llm_calls": 2,
      "actions_planned": 4,
      "actions_completed": 3,
      "total_input_tokens": 3200,
      "total_output_tokens": 450,
      "success": true
    }
  ],
  "total": 150
}
```

---

#### `GET /logs/sessions/{session_id}`

Get details for a specific session.

**Response includes:**
- Session metadata
- Timeline of all actions
- Errors encountered

---

#### `GET /logs/sessions/{session_id}/conversation`

View LLM prompts and responses for a session.

**Response:**
```json
{
  "session_id": "sess_abc123",
  "conversation": [
    {
      "role": "system",
      "content": "You are the Scenario Orchestrator...",
      "timestamp": "2024-01-15T14:30:05"
    },
    {
      "role": "assistant",
      "content": "{\"reasoning\": \"...\", \"actions\": [...]}",
      "timestamp": "2024-01-15T14:30:10",
      "model": "claude-sonnet-4",
      "tokens": {"input": 1500, "output": 300}
    }
  ]
}
```

---

#### `GET /logs/llm-calls`

Query LLM API calls.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | string | Filter by session |
| `agent_id` | string | Filter by agent |
| `ticket_key` | string | Filter by ticket |
| `model` | string | Filter by model |

---

#### `GET /logs/jira-calls`

Query Jira API calls.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | string | Filter by session |
| `agent_id` | string | Filter by agent |
| `ticket_key` | string | Filter by ticket |
| `method` | string | HTTP method filter |

---

#### `GET /logs/stats`

Get LLM token usage statistics.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `start_date` | string (ISO) | Filter by date |
| `end_date` | string (ISO) | Filter by date |

**Response:**
```json
{
  "total_calls": 25,
  "total_input_tokens": 45000,
  "total_output_tokens": 8500,
  "total_tokens": 53500,
  "avg_duration_ms": 2500,
  "complex_calls": 10,
  "routine_calls": 15
}
```

---

#### `GET /logs/viewer`

HTML-based log viewer UI. Open in a browser to view sessions, LLM conversations, and timelines.

**Usage:** Navigate to `http://localhost:8000/logs/viewer` in a browser.

**Features:**
- Session list with token usage and error counts
- Conversation view showing LLM prompts/responses
- Timeline view of all events (LLM calls, Jira calls, orchestrator events)
- Auto-refresh every 30 seconds

---

## Configuration Files

### `config/settings.yaml`

Main simulation parameters.

#### Simulation Settings

```yaml
simulation:
  work_hours:
    start: 9          # Start of work day (24h)
    end: 17           # End of work day (24h)
    timezone: "America/New_York"

  actions_per_tick:
    light:
      min: 1
      max: 2
    normal:
      min: 2
      max: 4
    busy:
      min: 4
      max: 6

  max_concurrent_scenarios:
    normal_flow: 10
    blocker: 3
    rework: 2
    scope_creep: 2
    dependency: 2
```

#### Scenario Configuration

```yaml
scenarios:
  target_distribution:
    normal_flow: 0.50   # 50% normal progression
    blocker: 0.15       # 15% blockers
    rework: 0.15        # 15% QA rejections
    scope_creep: 0.10   # 10% mid-sprint additions
    dependency: 0.10    # 10% cross-team deps

  injection_rules:
    min_in_progress_for_blocker: 2
    min_in_progress_for_rework: 3
    max_active_blockers: 2
    max_active_rework: 2
    max_active_scope_creep: 1
    max_active_dependencies: 2
    blocker_duration:
      min: 2            # Minimum ticks
      max: 5            # Maximum ticks
    max_rework_iterations: 3

  phase_durations:       # As fraction of cycle time
    backlog: 0.0
    in_progress: 0.40
    in_review: 0.15
    in_testing: 0.25
    done: 0.0
    blocked: 0.10
    rejected: 0.05
    waiting_on_dependency: 0.15
```

#### Cycle Times

```yaml
cycle_times:
  bug:
    min_hours: 4
    max_hours: 24
    typical_hours: 12
  story:
    min_hours: 24
    max_hours: 72
    typical_hours: 40
  task:
    min_hours: 8
    max_hours: 40
    typical_hours: 20
  epic:
    min_hours: 168      # 1 week
    max_hours: 504      # 3 weeks
    typical_hours: 280  # ~2 weeks
```

#### LLM Configuration

```yaml
llm:
  routine_model: "claude-3-haiku-20240307"
  complex_model: "claude-sonnet-4-20250514"
  planning_temperature: 0.7
  routine_temperature: 0.3

  complex_actions:
    - scenario_planning
    - create_story
    - create_epic
    - architectural_comment
    - design_discussion
    - blocker_analysis
    - dependency_identification
```

#### Workload Limits

```yaml
workload:
  max_assigned_per_agent:
    developer: 3
    qa: 4
    tech_lead: 2
    pm: 5

  max_daily_actions:
    developer: 8
    qa: 10
    tech_lead: 6
    pm: 12
```

#### Sprint Settings

```yaml
sprint:
  duration_days: 7        # 1-week sprints
  planning_day: 1         # Monday (day 1 of sprint)
  board_id: 4             # Jira board ID for sprint operations
  future_sprints_to_maintain: 2  # Always keep 1-2 future sprints planned
```

#### Issue Type Permissions

Controls which issue types each role can act on and create. This prevents developers from acting on Epics (PM-only) and enforces realistic process adherence.

```yaml
issue_type_permissions:
  pm:
    can_act_on: ["Epic", "Story", "Bug", "Task"]
    can_create: ["Epic", "Story"]
  developer:
    can_act_on: ["Story", "Bug", "Task"]
    can_create: ["Bug"]
  qa:
    can_act_on: ["Story", "Bug", "Task"]
    can_create: ["Bug"]
  tech_lead:
    can_act_on: ["Story", "Bug", "Task"]
    can_create: ["Bug"]
```

**Key Rules:**
- **Epics are PM-only**: Developers, QA, and Tech Leads cannot pick up or comment on Epics
- **Story creation is PM-only**: Only PMs can create Stories and Epics
- **All roles can create Bugs**: For reporting issues during development/testing

#### Analyzer Thresholds

```yaml
analyzer:
  wip_limit_warning: 5
  stale_ticket_hours: 48
  overdue_threshold: 1.2

  opportunity_weights:
    phase_advancement: 1.0
    blocker_injection: 0.3
    rework_injection: 0.3
    scope_creep: 0.2
    dependency_injection: 0.2
    workload_balance: 0.5
```

#### Logging Settings

```yaml
logging:
  enabled: true
  db_path: "data/logs.db"
  retention_days: 30
  log_full_prompts: true
  log_full_responses: true
  viewer_enabled: true
```

---

### `config/personas.yaml`

Agent definitions with Jira account mappings.

```yaml
agents:
  alpha_pm:
    jira_account_id: "712020:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
    jira_email: "sarah.chen@company.com"
    display_name: "Sarah Chen"
    team: "alpha"
    role: "pm"
    persona: |
      Strategic thinker, user-focused, asks clarifying questions.
      Communication style: Clear, prioritizes user value.
    behaviors:
      - create_story
      - add_acceptance_criteria
      - prioritize_backlog
      - comment_on_progress
    activity_level: "high"    # high=70%, medium=50%, low=30%

  alpha_dev_senior:
    jira_account_id: "712020:yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"
    jira_email: "elena.rodriguez@company.com"
    display_name: "Elena Rodriguez"
    team: "alpha"
    role: "developer"
    seniority: "senior"       # senior, mid, junior
    persona: |
      10 years experience, values clean maintainable code.
      Fast executor who prefers action over lengthy discussion.
      Communication style: Brief, technical, to the point.
    behaviors:
      - pick_up_tasks
      - transition_status
      - add_technical_comments
      - log_work
      - resolve_blockers
    activity_level: "high"

  beta_dev_junior:
    jira_account_id: "712020:zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz"
    jira_email: "tyler.brooks@company.com"
    display_name: "Tyler Brooks"
    team: "beta"
    role: "developer"
    seniority: "junior"
    persona: |
      1 year experience, eager to learn and improve.
      Sometimes needs guidance, occasionally makes mistakes.
      Communication style: Asks lots of questions, grateful for help.
    behaviors:
      - pick_up_tasks
      - transition_status
      - ask_questions
      - request_help
      - log_work
    activity_level: "medium"
    error_rate: 0.15          # 15% chance of rework
```

#### Agent Fields Reference

| Field | Required | Description |
|-------|----------|-------------|
| `jira_account_id` | Yes | Jira account ID (from profile URL) |
| `jira_email` | Yes | Email associated with Jira account |
| `display_name` | Yes | Name shown in comments |
| `team` | Yes | Team identifier (`alpha`, `beta`) |
| `role` | Yes | `pm`, `developer`, `qa`, `tech_lead` |
| `seniority` | Devs only | `senior`, `mid`, `junior` |
| `persona` | Yes | Personality description for LLM |
| `behaviors` | Yes | List of allowed action types |
| `activity_level` | Yes | `high`, `medium`, `low` |
| `error_rate` | Optional | Probability of needing rework (0-1) |

---

### `config/templates.yaml`

Pre-written comment templates for routine actions.

```yaml
status_transitions:
  to_in_progress:
    - "Starting work on this now."
    - "Picking this up."
    - "Beginning implementation."
    - "Got it, working on this."

  to_code_review:
    - "Ready for review."
    - "PR is up, ready for code review."
    - "Implementation complete, requesting review."
    - "Done with implementation, please review."

  to_testing:
    - "Code review approved, moving to QA."
    - "Ready for testing."
    - "Moving to QA."

qa_actions:
  approval_prefix:
    - "✅ Verified:"
    - "✅ All tests pass."
    - "✅ QA approved."
    - "✅ Looks good:"

  rejection_prefix:
    - "❌ QA Failed:"
    - "❌ Found issue:"
    - "❌ Needs fix:"

work_log:
  descriptions:
    - "Implementation work"
    - "Development"
    - "Bug fix"
    - "Code review"
    - "Testing"
    - "Documentation"

assignment:
  self_assign:
    - "Taking this one."
    - "I'll handle this."
    - "Assigning to myself."
```

Templates are selected randomly to add variety.

---

## State Management

### State File Location

`data/state.json`

### State Structure

```json
{
  "last_run": "2024-01-15T14:30:00",
  "simulation_day": 5,
  "current_sprint": {
    "sprint_number": 3,
    "sprint_day": 8,
    "name": "Sprint 3",
    "started_at": "2024-01-08T09:00:00"
  },
  "active_scenarios": {
    "scenario_abc123": {
      "ticket_key": "PROJ-42",
      "scenario_type": "normal_flow",
      "current_phase": "in_review",
      "assigned_agent": "alpha_dev_senior",
      "complexity": "story",
      "started_at": "2024-01-13T10:00:00",
      "phase_started_at": "2024-01-14T15:00:00",
      "target_end": "2024-01-17T10:00:00",
      "is_blocked": false,
      "is_rejected": false,
      "rework_count": 0
    }
  },
  "completed_scenarios": [],
  "agent_states": {
    "alpha_dev_senior": {
      "last_action_time": "2024-01-15T14:15:00",
      "daily_action_count": 4,
      "current_workload": 2,
      "assigned_tickets": ["PROJ-42", "PROJ-45"],
      "is_overloaded": false
    }
  },
  "scenario_distribution": {
    "normal_flow": 6,
    "blocker": 1,
    "rework": 1,
    "scope_creep": 0,
    "dependency": 0
  },
  "recent_actions": [
    {
      "timestamp": "2024-01-15T14:30:00",
      "agent_id": "alpha_qa",
      "action_type": "qa_approve",
      "ticket_key": "PROJ-38"
    }
  ]
}
```

### Automatic State Updates

**Daily Reset** (when new day detected):
- Agent daily action counts → 0
- Sprint day advances

**Sprint Reset** (after day 7):
- Sprint number increments
- Sprint day → 1

**Scenario Completion**:
- Moved from `active_scenarios` to `completed_scenarios`
- Agent workload decremented

### State Recovery

If state becomes corrupted:

```bash
# Reset to fresh state
curl -X POST http://localhost:8000/reset
```

Or manually delete `data/state.json` and restart.

---

## Process Adherence Features

### Sprint Integration

The simulation integrates with Jira's actual sprint system (Board ID: 4).

**Sprint Requirements:**
- Items must be in the active sprint to be worked on
- Work actions (pick up, transition, comment) are blocked for items not in sprint
- Violations are detected and gradually fixed with explanatory comments

**Sprint Planning (Every Monday):**
- PMs (Sarah Chen, David Kim) plan sprints on day 1
- System maintains 1-2 future sprints
- Unassigned backlog items are allocated to sprints

**Sprint Configuration:**
```yaml
sprint:
  duration_days: 7        # 1-week sprints (Monday to Sunday)
  planning_day: 1         # Monday
  board_id: 4             # Jira board ID
  future_sprints_to_maintain: 2
```

### Epic Lifecycle Management

Epics follow automatic lifecycle rules based on child issue status.

**Epic Status Rules:**
| Child Status | Epic Should Be |
|--------------|----------------|
| All "To Do" | "To Do" |
| Any in progress | "In Progress" |
| All "Done" | "Done" |

**Epic Ownership:**
- Epics are automatically assigned to team PMs
- Unassigned Epics get assigned with explanatory comments
- Sarah Chen handles Alpha team Epics
- David Kim handles Beta team Epics

### Violation Detection & Cleanup

The system gradually fixes process violations with explanatory comments.

**Detected Violations:**
| Violation | Detection | Fix |
|-----------|-----------|-----|
| Work without sprint | Item in progress but no sprint | Add to active sprint |
| Non-PM on Epic | Developer assigned to Epic | Reassign to team PM |
| Epic status mismatch | Epic status doesn't match children | Transition Epic |
| Unassigned Epic | Epic with no assignee | Assign to team PM |

**Cleanup Behavior:**
- Maximum 2 violations fixed per tick (gradual)
- Each fix includes an explanatory comment
- Comments explain why the change was made

---

## Environment Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `JIRA_URL` | Atlassian site URL | `https://mycompany.atlassian.net` |
| `JIRA_EMAIL` | API user email | `admin@company.com` |
| `JIRA_API_TOKEN` | Jira API token | `ATATT3xFfGF0...` |
| `PROJECT_KEY` | Jira project key | `PROJ` |
| `ANTHROPIC_API_KEY` | Anthropic API key | `sk-ant-api03-...` |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `STATE_FILE` | State file path | `data/state.json` |

---

## Error Codes

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad request (invalid parameters) |
| 500 | Internal error (check logs) |

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Jira connection failed` | Invalid credentials | Check `.env` values |
| `Agent account not found` | Invalid account ID | Verify `personas.yaml` |
| `No actions taken` | Empty board | Add tickets to Jira |
| `LLM rate limit` | Too many requests | Wait and retry |
| `State file corrupt` | JSON parse error | Reset state |
