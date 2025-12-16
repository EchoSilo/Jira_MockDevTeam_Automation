# Getting Started

Get the Jira Team Simulator running in under 15 minutes.

## Prerequisites

Before you begin, ensure you have:

- **Python 3.11+** installed
- **Jira Cloud account** with admin access to create API tokens
- **9 Jira user accounts** (can use free tier - supports up to 10 users)
- **Anthropic API key** from [console.anthropic.com](https://console.anthropic.com)

## Quick Setup

### Step 1: Install Dependencies

```bash
# Clone the repository
git clone <repository-url>
cd Jira_MockDevTeam_Automation

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Configure Environment

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```ini
# Jira Configuration
JIRA_URL=https://yoursite.atlassian.net
JIRA_EMAIL=your-email@domain.com
JIRA_API_TOKEN=your-api-token

# Jira Project
PROJECT_KEY=YOUR_PROJECT_KEY

# Anthropic API
ANTHROPIC_API_KEY=your-anthropic-api-key
```

**How to get these values:**

| Variable | Where to find it |
|----------|------------------|
| `JIRA_URL` | Your Atlassian site URL (e.g., `https://mycompany.atlassian.net`) |
| `JIRA_EMAIL` | Email of the account that will make API calls |
| `JIRA_API_TOKEN` | [Create API token](https://id.atlassian.com/manage-profile/security/api-tokens) |
| `PROJECT_KEY` | The prefix of your Jira tickets (e.g., `PROJ` for `PROJ-123`) |
| `ANTHROPIC_API_KEY` | [Get from Anthropic Console](https://console.anthropic.com/settings/keys) |

### Step 3: Map Jira Accounts

Edit `config/personas.yaml` to map each simulated agent to a real Jira account.

For each agent, update the `jira_account_id` field:

```yaml
alpha_pm:
  jira_account_id: "712020:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"  # Replace with real ID
  jira_email: "sarah.chen@yourcompany.com"
  display_name: "Sarah Chen"
  # ... rest of config
```

**How to find Jira Account IDs:**

1. Go to your Jira project
2. Click on a user's avatar/name to view their profile
3. The account ID is in the URL: `https://yoursite.atlassian.net/jira/people/712020:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`

Alternatively, use the Jira API:
```bash
curl -u your-email@domain.com:your-api-token \
  "https://yoursite.atlassian.net/rest/api/3/users/search?query=sarah"
```

### Step 4: Run Your First Simulation

Start the server:

```bash
uvicorn src.main:app --reload
```

The API is now running at `http://localhost:8000`

Trigger a simulation tick:

```bash
curl -X POST http://localhost:8000/trigger
```

Or open in browser: `http://localhost:8000/docs` for the interactive API docs.

### Step 5: Verify in Jira

Go to your Jira project and you should see:
- New comments on existing tickets
- Status transitions
- Work logged
- Possibly new stories or bugs created

Check the response from `/trigger` to see what actions were taken.

---

## What Just Happened?

When you triggered the simulation, here's what occurred:

```
1. System loaded current state from data/state.json
2. Determined random intensity (light/normal/busy)
3. Analyzed your Jira board for opportunities
4. AI planned 2-6 realistic actions
5. Agents executed actions via Jira API
6. State was updated and saved
```

**Example response:**
```json
{
  "success": true,
  "actions_taken": 3,
  "intensity": "normal",
  "actions": [
    {
      "agent": "Elena Rodriguez",
      "action": "progress_to_review",
      "ticket": "PROJ-42"
    },
    {
      "agent": "Priya Sharma",
      "action": "qa_approve",
      "ticket": "PROJ-38"
    },
    {
      "agent": "James Park",
      "action": "pick_up_task",
      "ticket": "PROJ-45"
    }
  ]
}
```

---

## Next Steps

### Set Up Automated Scheduling

For realistic simulation, set up n8n to trigger automatically:

1. Install [n8n](https://n8n.io/) (or use n8n Cloud)
2. Create a workflow with:
   - **Schedule Trigger**: `0 */45 9-17 * * 1-5` (every 45 min, weekdays 9-5)
   - **HTTP Request**: POST to `http://localhost:8000/trigger`

See [Setup Guide](setup-guide.md) for detailed n8n configuration.

### Explore the Documentation

| Document | Description |
|----------|-------------|
| [How It Works](how-it-works.md) | Understand the simulation mechanics |
| [AI Architecture](ai-architecture.md) | Learn how AI decisions are made |
| [Flow Diagrams](flow-diagrams.md) | Visual system diagrams |
| [Technical Reference](technical-reference.md) | API and configuration details |
| [Setup Guide](setup-guide.md) | Detailed deployment options |

### Useful Commands

```bash
# Check system health
curl http://localhost:8000/health

# View current state
curl http://localhost:8000/state

# View active scenarios
curl http://localhost:8000/scenarios

# List agents
curl http://localhost:8000/agents

# Reset simulation (start fresh)
curl -X POST http://localhost:8000/reset
```

---

## Troubleshooting

### "Jira connection failed"

- Verify `JIRA_URL` doesn't have a trailing slash
- Check API token is valid (try in Postman/curl first)
- Ensure the email matches the account that created the token

### "Agent account not found"

- Verify `jira_account_id` in `personas.yaml` is correct
- Account IDs look like: `712020:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`

### "No actions taken"

- Check your Jira board has tickets in various states
- The simulation needs existing tickets to act on
- Create a few stories manually to seed the board

### Need more help?

See the full [Troubleshooting section](setup-guide.md#troubleshooting) in the Setup Guide.
