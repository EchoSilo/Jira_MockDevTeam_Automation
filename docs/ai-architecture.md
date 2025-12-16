# AI Architecture

This document explains how the simulator uses AI to make decisions and generate realistic content.

---

## Overview

The system uses a multi-layered AI architecture:

```
┌─────────────────────────────────────────────────────────────────┐
│                        AI Decision Flow                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│   │   Analyzer   │───▶│   Planner    │───▶│    Crews     │     │
│   │  (Rules)     │    │  (LLM)       │    │  (CrewAI)    │     │
│   └──────────────┘    └──────────────┘    └──────────────┘     │
│         │                    │                    │             │
│    No AI needed         Claude Sonnet       Claude Haiku       │
│    Pattern matching     Strategic decisions  Content generation│
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

| Component | AI Model | Purpose |
|-----------|----------|---------|
| **Analyzer** | None (rules) | Detect opportunities from board state |
| **Planner** | Claude Sonnet | Decide which actions to take |
| **Crews** | Claude Haiku/Sonnet | Execute actions, generate content |

---

## The Two-Tier Model System

### Claude Haiku (Fast & Cheap)

Used for routine operations:
- Simple status update comments
- Work log descriptions
- Basic progress updates
- Acknowledgment messages

**Characteristics:**
- ~10x faster than Sonnet
- ~10x cheaper than Sonnet
- Good for templated responses

### Claude Sonnet (Smart & Capable)

Used for complex decisions:
- Scenario planning (which actions to take)
- Story/epic creation
- Bug report generation
- Architectural discussions
- Code review feedback

**Characteristics:**
- Better reasoning
- More nuanced content
- Higher cost per call

### Cost Optimization Strategy

```
┌─────────────────────────────────────────────────────────────┐
│                    Per-Tick Cost Breakdown                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1 × Sonnet call (planning)        ≈ $0.02                 │
│  2-4 × Haiku calls (execution)     ≈ $0.004                │
│  Templates (no LLM)                ≈ $0.00                  │
│  ─────────────────────────────────────────                  │
│  Total per tick                    ≈ $0.025                │
│                                                             │
│  12 ticks/day × $0.025             ≈ $0.30/day             │
│  ~22 working days × $0.30          ≈ $6.60/month           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Decision Flow: Step by Step

### Step 1: Analyze (No LLM)

The Analyzer examines the Jira board using rules, not AI:

```python
# Pseudocode - what the analyzer does
def analyze(board_state):
    opportunities = []

    # Check if scenarios are ready to advance
    for scenario in active_scenarios:
        if scenario.time_in_phase > minimum_time:
            opportunities.append(AdvanceScenario(scenario))

    # Check if we need more blockers (target: 15%)
    if blocker_rate < 0.15:
        for ticket in in_progress_tickets:
            if random() < 0.15:
                opportunities.append(InjectBlocker(ticket))

    # Check if developers have capacity
    for developer in developers:
        if developer.workload < max_workload:
            opportunities.append(PickUpTask(developer))

    return opportunities
```

**Why no LLM?** Pattern detection is deterministic - we don't need AI to count tickets or check time thresholds.

### Step 2: Plan (Sonnet LLM)

The Planner receives opportunities and decides what to do:

**Input to LLM:**
- Current board state (tickets by status)
- Active scenarios (type, phase, age)
- Detected opportunities (prioritized)
- Recent actions (avoid repetition)
- Sprint context (day 1-14)
- Target scenario distribution

**Prompt excerpt:**
```
You are the Scenario Orchestrator for a Jira team simulation.
Your job is to plan realistic team activity.

## Current Board State
Backlog: PROJ-45, PROJ-46, PROJ-47
In Progress: PROJ-42 (Elena), PROJ-43 (James)
Code Review: PROJ-40 (Marcus reviewing)
Testing: PROJ-38 (Priya)

## Detected Opportunities
HIGH: Advance PROJ-38 (ready for QA decision)
HIGH: Advance PROJ-40 (review complete)
MEDIUM: Pick up PROJ-45 (Tyler available)

## Your Task
Plan 3 actions for this tick. Consider:
- Priority order (advance ready scenarios first)
- Realism (don't rush tickets)
- Variety (mix action types)

Return JSON:
{
  "reasoning": "Brief explanation",
  "actions": [
    {"type": "qa_approve", "ticket_key": "PROJ-38", "agent_id": "alpha_qa"},
    ...
  ]
}
```

**Output from LLM:**
```json
{
  "reasoning": "Two scenarios ready to advance. Tyler has capacity for new work.",
  "actions": [
    {
      "type": "qa_approve",
      "ticket_key": "PROJ-38",
      "agent_id": "alpha_qa",
      "details": "Clean implementation, all tests pass"
    },
    {
      "type": "progress_to_review",
      "ticket_key": "PROJ-40",
      "agent_id": "alpha_dev_senior"
    },
    {
      "type": "pick_up_task",
      "ticket_key": "PROJ-45",
      "agent_id": "beta_dev_junior"
    }
  ]
}
```

### Step 3: Execute (CrewAI + Haiku/Sonnet)

Each planned action is executed by a CrewAI crew:

```
Action: qa_approve for PROJ-38 by Priya

CrewAI creates:
├── Agent: Priya Sharma (QA Engineer)
│   ├── Persona: "Detail-oriented, thorough test scenarios..."
│   ├── Goal: "Ensure quality of Team Alpha's deliverables"
│   └── Tools: [transition, comment, log_work]
│
└── Task: "Test PROJ-38 against acceptance criteria"
    ├── Step 1: Get issue details
    ├── Step 2: Add approval comment
    └── Step 3: Transition to Done
```

**Comment generation uses the agent's persona:**
```
Prompt to Haiku:
"You are Priya Sharma, a QA Engineer.
Your style: Detail-oriented, thorough test scenarios, focuses on edge cases.

Write a QA approval comment for PROJ-38: 'Add date range filter to search'

Keep it brief (1-3 sentences), professional, no AI-speak."

Output:
"✅ Verified against all acceptance criteria. Date picker works correctly
including edge cases (same day, year boundaries). Ready to ship."
```

---

## Prompt Types

### 1. Scenario Planning Prompt

**When:** Once per tick
**Model:** Sonnet (complex reasoning needed)
**Purpose:** Decide which actions to take

**Key elements:**
- Full board context
- Active scenario status
- Prioritized opportunities
- Sprint timing
- Distribution targets

### 2. Comment Generation Prompt

**When:** For each Jira comment
**Model:** Haiku (routine) or Sonnet (technical)
**Purpose:** Generate realistic comments

**Key elements:**
- Agent persona and style
- Ticket context (summary, description)
- Recent conversation (last 3 comments)
- Action context (what they're doing)

**Anti-patterns enforced:**
```
Do NOT use phrases like:
- "I hope this helps"
- "Let me know if you have questions"
- "Happy to help"
- Any emoji
```

### 3. Story Creation Prompt

**When:** PM creates new work
**Model:** Sonnet (creative, structured)
**Purpose:** Generate realistic user stories

**Output format:**
```json
{
  "summary": "As a user, I want to...",
  "description": "Detailed description with acceptance criteria",
  "issue_type": "Story",
  "priority": "Medium"
}
```

**Context provided:**
- Team's focus area
- Existing epics (to fit theme)
- Recent stories (avoid duplicates)

### 4. Bug Report Prompt

**When:** QA finds issues
**Model:** Sonnet (detailed, structured)
**Purpose:** Generate realistic bug reports

**Output format:**
```json
{
  "summary": "Bug: Brief description",
  "description": "## Description\n...\n## Steps to Reproduce\n...",
  "issue_type": "Bug",
  "priority": "High"
}
```

### 5. Technical Comment Prompt

**When:** Code review, architecture discussions
**Model:** Sonnet (technical depth)
**Purpose:** Generate meaningful technical feedback

**Types:**
- `architectural` - Design trade-offs and concerns
- `code_review` - Implementation feedback
- `blocker` - Technical blockers
- `design` - Design alternatives

---

## Persona Integration

### How Personas Affect Output

Every agent has a persona defined in `config/personas.yaml`:

```yaml
alpha_dev_senior:
  display_name: "Elena Rodriguez"
  persona: |
    10 years experience, values clean maintainable code.
    Fast executor who prefers action over lengthy discussion.
    Communication style: Brief, technical, to the point.
```

This persona is injected into every prompt:

```
You are Elena Rodriguez, a Senior Developer.

Your personality and communication style:
10 years experience, values clean maintainable code.
Fast executor who prefers action over lengthy discussion.
Communication style: Brief, technical, to the point.

Write a progress comment...
```

### Persona Impact Examples

**Same action, different personas:**

**Elena (Senior):**
> "Auth module refactored. Tests updated."

**Tyler (Junior):**
> "I've been working on the auth changes. Had some questions about the error handling approach - should I follow the pattern in UserService or create a new one? Want to make sure I'm doing this right."

**Marcus (Tech Lead):**
> "Reviewed the auth refactor. Clean separation of concerns. One suggestion: consider extracting the retry logic into a shared utility since we use this pattern in several places."

---

## Template System

### When Templates Are Used

For routine actions, pre-written templates avoid LLM calls:

```yaml
# config/templates.yaml

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

qa_actions:
  approval_prefix:
    - "✅ Verified:"
    - "✅ All tests pass."
    - "✅ QA approved."
```

### Template vs LLM Decision

```
Action Type                    → Uses
─────────────────────────────────────────
Status transition comment      → Template
Simple acknowledgment          → Template
Work log description          → Template
─────────────────────────────────────────
Story/epic creation           → Sonnet
Bug report                    → Sonnet
Code review feedback          → Sonnet
Architectural discussion      → Sonnet
Blocker explanation           → Sonnet
Progress with context         → Haiku
QA rejection with reasons     → Haiku
```

---

## Complex Actions List

Actions that always use Sonnet (defined in `settings.yaml`):

```yaml
llm:
  complex_actions:
    - scenario_planning
    - create_story
    - create_epic
    - architectural_comment
    - design_discussion
    - blocker_analysis
    - dependency_identification
```

All other actions use Haiku or templates.

---

## CrewAI Agent Definitions

Each role has specific goals and backstory:

### Product Manager Agent

```python
role = "Product Manager"
goal = """Drive product development by:
- Creating clear, well-defined user stories
- Prioritizing backlog based on business value
- Ensuring requirements are understood
- Tracking progress and removing blockers"""

backstory = """You are {name}, a Product Manager.
{persona}
Focus on user value and business outcomes."""
```

### Developer Agent

```python
role = "Software Developer ({seniority})"
goal = """Execute development work by:
- Picking up appropriate tasks
- Transitioning tickets accurately
- Providing clear progress updates
- Asking clarifying questions when needed"""

backstory = """You are {name}, a {seniority} developer.
{persona}
{seniority_context}  # Varies by level
Your comments should be brief and technical."""
```

**Seniority context:**
- **Junior:** "Still learning, may need guidance, occasionally needs rework"
- **Mid:** "Solid experience, works independently, good documentation"
- **Senior:** "Highly experienced, efficient, proactively identifies risks"

### QA Agent

```python
role = "QA Engineer"
goal = """Ensure quality by:
- Testing against acceptance criteria
- Approving work that meets standards
- Rejecting with actionable feedback
- Creating detailed bug reports"""

backstory = """You are {name}, a QA Engineer.
{persona}
Be thorough but not a gatekeeper."""
```

### Tech Lead Agent

```python
role = "Tech Lead"
goal = """Provide technical leadership by:
- Reviewing code constructively
- Offering architectural guidance
- Identifying risks early
- Mentoring through comments"""

backstory = """You are {name}, Tech Lead.
{persona}
Balance quality with pragmatism."""
```

---

## Tools Available to Agents

CrewAI agents have role-specific tools:

| Tool | PM | Dev | QA | TL |
|------|:--:|:---:|:--:|:--:|
| Search Issues | ✓ | ✓ | ✓ | ✓ |
| Get Issue Details | ✓ | ✓ | ✓ | ✓ |
| Add Comment | ✓ | ✓ | ✓ | ✓ |
| Transition Status | | ✓ | ✓ | ✓ |
| Assign Issue | | ✓ | | |
| Log Work | | ✓ | ✓ | |
| Create Issue | ✓ | | ✓ | |
| Link Issues | | | ✓ | |
| View Backlog | ✓ | ✓ | | ✓ |
| View In Progress | ✓ | ✓ | | ✓ |
| View QA Queue | | | ✓ | ✓ |

---

## Error Handling & Fallbacks

### LLM Failure Handling

If the Planner LLM fails:
1. Parse error → Try to extract JSON from response
2. Still fails → Use fallback plan from opportunities

**Fallback plan:**
```python
# If LLM fails, use top opportunities directly
fallback_actions = [
    opportunity.to_action()
    for opportunity in high_priority_opportunities[:target_count]
]
```

### Invalid Action Handling

Actions are validated before execution:
- Must have required fields (type, agent_id)
- Agent can only appear once per tick
- Scenario ID must exist if provided

Invalid actions are skipped; valid ones continue.

### Tool Failure Handling

If a Jira tool call fails:
- Error is logged
- Action is marked as failed
- Execution continues with next action
- State is not updated for failed actions

---

## Monitoring & Debugging

### LLM Call Logging

All LLM calls are logged to `data/logs.db`:

```sql
-- Query recent LLM calls
SELECT timestamp, model, agent_id, action_type,
       prompt_tokens, response_tokens
FROM llm_calls
ORDER BY timestamp DESC
LIMIT 20;
```

### Viewing Prompts and Responses

API endpoint for debugging:

```bash
# Get conversation log for a session
curl http://localhost:8000/logs/sessions/{session_id}/conversation
```

Returns full prompts and responses for analysis.

### Cost Tracking

```bash
# Get LLM usage stats
curl http://localhost:8000/logs/llm-calls?model=claude-sonnet-4
```

Includes token counts for cost calculation.
