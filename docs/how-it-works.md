# How It Works

This guide explains how the Jira Team Simulator creates realistic development team activity without requiring you to read any code.

---

## What It Does

The simulator creates activity that looks like a real 9-person development team:

- **Status transitions** - Tickets move through your workflow naturally
- **Comments** - AI-generated contextual discussions
- **Work logging** - Time tracked against tickets
- **Story creation** - PMs create new work items
- **Bug reports** - QA files issues during testing
- **Team dynamics** - Blockers, rejections, dependencies

The goal is realistic patterns that can be used to test productivity analytics, dashboards, and workflow automation.

---

## The Simulated Team

### Team Structure

```
┌─────────────────────────────────────────────────────────────┐
│                    Jira Team Simulator                      │
├────────────────────────────┬────────────────────────────────┤
│         Team Alpha         │          Team Beta             │
│      (Core Platform)       │       (User Features)          │
├────────────────────────────┼────────────────────────────────┤
│                            │                                │
│  Sarah Chen                │  David Kim                     │
│  Product Manager           │  Product Manager               │
│  • Creates stories/epics   │  • Creates stories/epics       │
│  • Prioritizes backlog     │  • Prioritizes backlog         │
│                            │                                │
│  Marcus Johnson            │                                │
│  Tech Lead                 │                                │
│  • Code reviews            │                                │
│  • Architecture guidance   │                                │
│                            │                                │
│  Elena Rodriguez           │  Ana Costa                     │
│  Senior Developer          │  Mid Developer                 │
│  • Complex tasks           │  • General development         │
│  • Fast execution          │  • Steady progress             │
│                            │                                │
│  James Park                │  Tyler Brooks                  │
│  Mid Developer             │  Junior Developer              │
│  • General development     │  • Learning tasks              │
│  • Collaboration           │  • Sometimes needs rework      │
│                            │                                │
│  Priya Sharma              │  Rachel Green                  │
│  QA Engineer               │  QA Engineer                   │
│  • Testing & approval      │  • Testing & approval          │
│  • Bug reporting           │  • Bug reporting               │
│                            │                                │
└────────────────────────────┴────────────────────────────────┘
```

### Agent Personalities

Each agent has a unique persona that affects their communication style:

| Agent | Communication Style |
|-------|---------------------|
| **Sarah Chen** (PM) | Strategic, user-focused, asks clarifying questions |
| **Marcus Johnson** (TL) | Technical depth, mentoring tone, raises concerns early |
| **Elena Rodriguez** (Sr Dev) | Brief, technical, action-oriented |
| **James Park** (Mid Dev) | Collaborative, clear status updates |
| **Priya Sharma** (QA) | Detail-oriented, thorough test scenarios |
| **David Kim** (PM) | Data-driven, metrics-focused |
| **Ana Costa** (Mid Dev) | Thoughtful, good documentation |
| **Tyler Brooks** (Jr Dev) | Asks questions, grateful for guidance |
| **Rachel Green** (QA) | Systematic, edge-case focused |

---

## Agent Behaviors

### Product Managers (Sarah, David)

**What they do:**
- Create new user stories when backlog runs low
- Add acceptance criteria to stories
- Comment on progress and priorities
- Prioritize backlog items

**Example actions:**
```
Sarah Chen created story PROJ-52: "As a user, I want to filter search results by date"
David Kim added acceptance criteria to PROJ-48
Sarah Chen commented on PROJ-45: "Let's prioritize this for the current sprint"
```

### Developers (Elena, James, Ana, Tyler)

**What they do:**
- Pick up tasks from backlog
- Transition tickets through workflow (In Progress → Code Review)
- Add progress comments
- Log work time
- Ask clarifying questions (especially juniors)

**Example actions:**
```
Elena Rodriguez moved PROJ-42 to "In Progress"
James Park logged 2h 30m on PROJ-38
Tyler Brooks commented: "Should this use the existing validation library?"
Ana Costa moved PROJ-44 to "Code Review"
```

**Seniority matters:**
- **Senior** (Elena): Faster completion, handles complex tasks, rarely needs rework
- **Mid** (James, Ana): Steady progress, good documentation
- **Junior** (Tyler): Longer cycle times, sometimes needs rework, asks more questions

### QA Engineers (Priya, Rachel)

**What they do:**
- Test tickets in QA/Testing status
- Approve work (move to Done) - ~75% of the time
- Reject work (back to In Progress) - ~25% of the time
- Add test scenarios and findings
- Create bug reports during testing

**Example actions:**
```
Priya Sharma approved PROJ-38: "Verified against all acceptance criteria. LGTM."
Rachel Green rejected PROJ-41: "❌ QA Failed: Form validation not working for empty email"
Priya Sharma created bug PROJ-53: "Search results don't paginate correctly"
```

### Tech Lead (Marcus)

**What they do:**
- Review code (approve ~85%, request changes ~15%)
- Add architectural guidance
- Flag potential blockers
- Mentor through technical comments

**Example actions:**
```
Marcus Johnson approved PROJ-42: "Clean implementation. Good test coverage."
Marcus Johnson commented: "Consider extracting this into a shared utility"
Marcus Johnson flagged blocker on PROJ-45: "Blocked on API rate limiting discussion"
```

---

## Scenario Types

The simulator doesn't just move tickets linearly. It creates realistic patterns through different scenarios:

### Normal Flow (60% of tickets)

Standard development workflow:

```
Backlog → In Progress → Code Review → Testing → Done
```

**Timeline:** 3-7 days for stories, 1-3 days for bugs

### Blockers (15% of tickets)

Something blocks progress:

```
In Progress → BLOCKED → Discussion → Unblocked → Continue
```

**What causes blockers:**
- Waiting on external API/service
- Need design clarification
- Dependency on another team
- Environment issues

**Example:**
```
Day 1: Elena picks up PROJ-42
Day 2: Elena flags blocker: "Waiting on auth service deployment"
Day 3: Marcus comments: "Auth team deploying tomorrow"
Day 4: Elena unblocks and continues
```

### Rework (15% of tickets)

QA finds issues, work returns to developer:

```
Testing → REJECTED → In Progress (fixing) → Testing → Done
```

**Why rework happens:**
- Missing acceptance criteria
- Edge cases not handled
- Junior developer learning curve
- Scope misunderstanding

**Example:**
```
Day 3: Priya tests PROJ-38
Day 3: Priya rejects: "Password validation not matching requirements"
Day 4: James fixes the issue
Day 5: Priya re-tests and approves
```

### Scope Creep (5% of tickets)

Mid-sprint additions (only happens days 4-10 of sprint):

```
PM creates new story mid-sprint → Team discussion → Added to sprint
```

**Example:**
```
Day 6: Sarah creates urgent story PROJ-54: "Critical: Fix payment timeout"
Day 6: Marcus comments: "We can squeeze this in if we defer PROJ-51"
```

### Dependencies (5% of tickets)

Cross-team waiting:

```
In Progress → Waiting on Dependency → Dependency Resolved → Continue
```

**Example:**
```
Day 2: Ana comments: "Need Team Alpha to complete the API endpoint first"
Day 2: Ticket marked as dependent on PROJ-42
Day 4: PROJ-42 completes, dependency resolved
Day 4: Ana continues work
```

---

## Intensity Levels

Each simulation tick randomly selects an intensity level:

| Intensity | Actions/Tick | Probability | Typical Day |
|-----------|--------------|-------------|-------------|
| **Light** | 1-2 | 20% | Slow morning, meetings day |
| **Normal** | 2-4 | 60% | Regular working day |
| **Busy** | 4-6 | 20% | Sprint deadline, incident |

This creates natural variation - not every tick produces the same activity level.

---

## Sprint Simulation

The simulator understands sprint cycles:

### 14-Day Sprints

```
Day 1-3:   Sprint start - lots of task pickup
Day 4-7:   Mid-sprint - steady progress, some blockers emerge
Day 8-10:  Late sprint - push to completion, scope discussions
Day 11-13: Sprint end - QA focus, bug fixes
Day 14:    Sprint close - wrap up, retrospective
```

### Daily Patterns

The simulator respects working hours:
- **Active hours:** 9 AM - 5 PM (configurable)
- **Peak activity:** Mid-morning and early afternoon
- **Quiet periods:** Early morning, lunch, evening

### Daily Limits

Agents have realistic daily action limits:

| Role | Max Actions/Day |
|------|-----------------|
| PM | 12 |
| Developer | 8 |
| QA | 10 |
| Tech Lead | 6 |

---

## Why It Looks Realistic

Several factors combine to create believable activity:

### 1. Persona-Driven Comments

Each agent has a distinct voice:

**Elena (Senior Dev):**
> "Refactored auth module. Updated tests."

**Tyler (Junior Dev):**
> "Working through the login form implementation. Quick question - should I use the existing validation helpers or create new ones?"

### 2. Contextual Awareness

Comments reference actual ticket content:

> "Based on the acceptance criteria, I've implemented the date range filter. Edge case handling for invalid dates included."

### 3. Realistic Timing

- 20-minute minimum between same agent's actions
- Cycle times vary by ticket complexity
- Sprint phase affects behavior

### 4. Team Dynamics

- Junior devs have higher rework rates
- Tech leads focus on reviews
- QA maintains quality standards
- PMs react to backlog size

### 5. Error Injection

Intentional "mistakes" that real teams make:
- Tyler's code sometimes needs fixes (15% error rate)
- QA catches issues (25% rejection rate)
- Blockers emerge unexpectedly

---

## What Gets Created in Jira

### Comments

AI-generated based on persona and context. Examples:

**Status Update:**
> "Starting work on the search filter component. Should have a PR up by tomorrow."

**Code Review:**
> "Looks good overall. One suggestion: consider memoizing the filter function since it's called frequently during re-renders."

**QA Feedback:**
> "✅ Verified: Date picker works correctly. Tested with various date ranges including edge cases (same day, year boundary). All acceptance criteria met."

### Transitions

Standard workflow transitions:
- Backlog → In Progress
- In Progress → Code Review
- Code Review → Testing
- Testing → Done
- (And reverse for rejections/blockers)

### Work Logs

Time logged against tickets:
- Realistic durations (15m to 4h per log)
- Descriptions like "Implementation", "Bug fix", "Code review"

### New Issues

PMs create stories:
- User story format with acceptance criteria
- Linked to existing epics
- Appropriate priority levels

QA creates bugs:
- Detailed reproduction steps
- Linked to parent tickets
- High priority by default

---

## State Persistence

The simulator maintains state between runs:

**What's tracked:**
- Last run timestamp
- Current sprint day (1-14)
- Active scenarios (in-flight tickets)
- Per-agent activity counts
- Recent actions history

**Where it's stored:**
- `data/state.json`

**Automatic resets:**
- Daily counters reset each new day
- Sprint advances after day 14
- Completed scenarios are archived

This ensures continuity - a ticket started on Monday continues its journey on Tuesday.
