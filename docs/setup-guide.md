# Setup Guide

Detailed installation, deployment, and troubleshooting instructions.

---

## Table of Contents

- [Local Development](#local-development)
- [Docker Deployment](#docker-deployment)
- [n8n Integration](#n8n-integration)
- [Jira Preparation](#jira-preparation)
- [Troubleshooting](#troubleshooting)

---

## Local Development

### Prerequisites

- Python 3.11 or higher
- pip (Python package manager)
- Git
- Access to Jira Cloud
- Anthropic API key

### Step 1: Clone and Install

```bash
# Clone the repository
git clone <repository-url>
cd Jira_MockDevTeam_Automation

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Configure Environment

Create `.env` from the example:

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

### Step 3: Configure Agents

Edit `config/personas.yaml` to map agents to your Jira accounts.

See [Jira Preparation](#jira-preparation) for details on getting account IDs.

### Step 4: Run the Server

```bash
uvicorn src.main:app --reload
```

The API will be available at `http://localhost:8000`

### Step 5: Test

```bash
# Health check
curl http://localhost:8000/health

# Trigger simulation
curl -X POST http://localhost:8000/trigger

# View API docs
open http://localhost:8000/docs
```

---

## Docker Deployment

### Prerequisites

- Docker
- Docker Compose
- Configured `.env` file

### Step 1: Build and Run

```bash
# Build and start
docker-compose up --build

# Run in background
docker-compose up -d --build
```

### Step 2: Verify

```bash
# Check container status
docker-compose ps

# View logs
docker-compose logs -f

# Test endpoint
curl http://localhost:8000/health
```

### Docker Configuration

**Dockerfile:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
COPY config/ ./config/
RUN mkdir -p /app/data
EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**docker-compose.yml:**
```yaml
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
      - PROJECT_KEY=${PROJECT_KEY}
    volumes:
      - ./data:/app/data      # Persist state
      - ./config:/app/config  # Allow config changes
    networks:
      - n8n_default           # For n8n integration
    restart: unless-stopped

networks:
  n8n_default:
    external: true
```

### Volume Mounts

| Volume | Purpose |
|--------|---------|
| `./data:/app/data` | Persists state.json and logs.db |
| `./config:/app/config` | Allows config changes without rebuild |

### Updating

```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose down
docker-compose up --build -d
```

---

## n8n Integration

### Option 1: Import Workflow

A pre-built workflow is included at `n8n/workflows/jira-simulator-scheduler.json`.

**To import:**

1. Open n8n
2. Go to **Workflows** → **Import from File**
3. Select `jira-simulator-scheduler.json`
4. Activate the workflow

### Option 2: Create Manually

**Step 1: Add Schedule Trigger**

1. Add a **Schedule Trigger** node
2. Set the cron expression: `0 */45 9-17 * * 1-5`

This runs every 45 minutes, Monday-Friday, 9 AM - 5 PM.

**Step 2: Add HTTP Request**

1. Add an **HTTP Request** node
2. Configure:
   - **Method:** POST
   - **URL:** `http://jira-simulator:8000/trigger`

**Step 3: Connect and Activate**

1. Connect Schedule Trigger → HTTP Request
2. Save the workflow
3. Toggle **Active** to enable

### Network Configuration

For n8n to reach the simulator, both must be on the same Docker network.

**If using Docker n8n:**

The `docker-compose.yml` already references `n8n_default` network:

```yaml
networks:
  n8n_default:
    external: true
```

**Create the network if needed:**

```bash
docker network create n8n_default
```

**If n8n is external:**

Use the host machine's IP or hostname instead of `jira-simulator`:

```
http://192.168.1.100:8000/trigger
```

### Cron Expression Reference

| Expression | Meaning |
|------------|---------|
| `0 */45 9-17 * * 1-5` | Every 45 min, 9-5, Mon-Fri |
| `0 */30 9-17 * * 1-5` | Every 30 min, 9-5, Mon-Fri |
| `0 0 10,14 * * 1-5` | 10 AM and 2 PM, Mon-Fri |
| `0 */60 * * * *` | Every hour, all days |

### Workflow JSON

```json
{
  "name": "Jira Simulator Scheduler",
  "nodes": [
    {
      "parameters": {
        "rule": {
          "interval": [
            {
              "field": "cronExpression",
              "expression": "0 */45 9-17 * * 1-5"
            }
          ]
        }
      },
      "type": "n8n-nodes-base.scheduleTrigger",
      "name": "Schedule Trigger"
    },
    {
      "parameters": {
        "method": "POST",
        "url": "http://jira-simulator:8000/trigger",
        "options": {}
      },
      "type": "n8n-nodes-base.httpRequest",
      "name": "HTTP Request"
    }
  ],
  "connections": {
    "Schedule Trigger": {
      "main": [[{"node": "HTTP Request", "type": "main", "index": 0}]]
    }
  }
}
```

---

## Jira Preparation

### Create User Accounts

You need 9 Jira user accounts for the simulated team:

| Agent | Suggested Email |
|-------|-----------------|
| Sarah Chen (PM) | sarah.chen@yourcompany.com |
| Marcus Johnson (TL) | marcus.johnson@yourcompany.com |
| Elena Rodriguez (Dev) | elena.rodriguez@yourcompany.com |
| James Park (Dev) | james.park@yourcompany.com |
| Priya Sharma (QA) | priya.sharma@yourcompany.com |
| David Kim (PM) | david.kim@yourcompany.com |
| Ana Costa (Dev) | ana.costa@yourcompany.com |
| Tyler Brooks (Dev) | tyler.brooks@yourcompany.com |
| Rachel Green (QA) | rachel.green@yourcompany.com |

**Jira Cloud Free Tier:** Supports up to 10 users.

### Get Account IDs

Each agent needs a `jira_account_id` in `personas.yaml`.

**Method 1: From Profile URL**

1. Go to Jira
2. Click on a user's name/avatar
3. View their profile
4. The URL contains the account ID:
   ```
   https://yoursite.atlassian.net/jira/people/712020:abc12345-1234-5678-9abc-def012345678
   ```
5. The account ID is: `712020:abc12345-1234-5678-9abc-def012345678`

**Method 2: API Query**

```bash
curl -u your-email@domain.com:your-api-token \
  "https://yoursite.atlassian.net/rest/api/3/users/search?query=sarah"
```

Response:
```json
[
  {
    "accountId": "712020:abc12345-1234-5678-9abc-def012345678",
    "displayName": "Sarah Chen",
    "emailAddress": "sarah.chen@yourcompany.com"
  }
]
```

### Configure Workflow

The simulator expects these Jira statuses:

| Status | Category |
|--------|----------|
| Backlog | To Do |
| To Do | To Do |
| In Progress | In Progress |
| Code Review | In Progress |
| Testing / QA | In Progress |
| Done | Done |

**To check your workflow:**

1. Go to **Project Settings** → **Workflow**
2. Verify status names match or update `config/settings.yaml`

### Create Initial Tickets

The simulator works best with existing tickets to act on.

**Seed your backlog with:**
- 5-10 stories in "Backlog" or "To Do"
- 2-3 bugs
- At least 1 epic

The simulator will add more over time.

### API Token Setup

1. Go to [https://id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click **Create API token**
3. Give it a name (e.g., "Jira Simulator")
4. Copy the token immediately (it won't be shown again)
5. Add to `.env` as `JIRA_API_TOKEN`

---

## Troubleshooting

### Connection Issues

#### "Jira connection failed"

**Symptoms:**
- Health check shows `jira_connected: false`
- 500 errors on `/trigger`

**Causes & Solutions:**

| Cause | Solution |
|-------|----------|
| Invalid URL | Remove trailing slash from `JIRA_URL` |
| Wrong credentials | Verify email and API token |
| Token expired | Create new API token |
| Network issue | Check firewall/proxy settings |

**Debug command:**
```bash
curl -u your-email@domain.com:your-api-token \
  "https://yoursite.atlassian.net/rest/api/3/myself"
```

Should return your user info.

---

#### "Agent account not found"

**Symptoms:**
- Actions fail with "user not found"
- Assignments don't work

**Causes & Solutions:**

| Cause | Solution |
|-------|----------|
| Wrong account ID | Re-copy from profile URL |
| Typo in format | Must be `712020:uuid-format` |
| User not in project | Add user to project |

---

### Simulation Issues

#### "No actions taken"

**Symptoms:**
- `/trigger` returns `actions_taken: 0`
- Board unchanged

**Causes & Solutions:**

| Cause | Solution |
|-------|----------|
| Empty board | Add tickets to Jira backlog |
| All agents at limit | Wait for daily reset |
| Wrong project key | Check `PROJECT_KEY` in `.env` |

---

#### "Actions planned but not executed"

**Symptoms:**
- `actions_planned > actions_taken`
- Errors in response

**Check the errors array:**
```json
{
  "errors": [
    {
      "action": "qa_approve",
      "ticket": "PROJ-42",
      "error": "Transition not allowed"
    }
  ]
}
```

**Common causes:**

| Error | Solution |
|-------|----------|
| Transition not allowed | Check Jira workflow allows the transition |
| Permission denied | Verify user has project permissions |
| Ticket not found | Ticket may have been deleted |

---

### LLM Issues

#### "Anthropic rate limit"

**Symptoms:**
- 429 errors
- Planning fails

**Solutions:**
- Wait a few minutes and retry
- Reduce tick frequency
- Check Anthropic usage dashboard

---

#### "Invalid API key"

**Symptoms:**
- 401 errors from Anthropic
- All LLM calls fail

**Solutions:**
- Verify `ANTHROPIC_API_KEY` in `.env`
- Check key hasn't been revoked
- Ensure no extra whitespace

---

### State Issues

#### "State file corrupt"

**Symptoms:**
- JSON parse errors on startup
- `/state` returns error

**Solution:**
```bash
# Reset state
curl -X POST http://localhost:8000/reset

# Or delete manually
rm data/state.json
```

---

#### "Scenarios stuck"

**Symptoms:**
- Same scenarios never complete
- Tickets don't progress

**Possible causes:**
- Jira workflow blocking transitions
- Agent at daily limit

**Debug:**
```bash
# Check active scenarios
curl http://localhost:8000/scenarios

# Check agent state
curl http://localhost:8000/agents
```

---

### Docker Issues

#### "Container keeps restarting"

**Check logs:**
```bash
docker-compose logs jira-simulator
```

**Common causes:**

| Error | Solution |
|-------|----------|
| Missing env var | Check `.env` file exists |
| Port in use | Change port in docker-compose.yml |
| Config parse error | Validate YAML syntax |

---

#### "n8n can't reach simulator"

**Symptoms:**
- n8n HTTP request fails
- "Connection refused"

**Solutions:**

1. Verify both on same network:
   ```bash
   docker network inspect n8n_default
   ```

2. Check container name matches URL:
   - URL should be `http://jira-simulator:8000/trigger`
   - Container name in docker-compose is `jira-simulator`

3. Create network if missing:
   ```bash
   docker network create n8n_default
   ```

---

### Getting Help

#### Check Logs

```bash
# Docker logs
docker-compose logs -f

# State and scenarios
curl http://localhost:8000/state
curl http://localhost:8000/scenarios

# Recent sessions
curl http://localhost:8000/logs/sessions?limit=5
```

#### Debug Mode

Run locally with verbose output:

```bash
LOG_LEVEL=DEBUG uvicorn src.main:app --reload
```

#### Reset Everything

```bash
# Stop containers
docker-compose down

# Clear state
rm data/state.json
rm data/logs.db

# Restart
docker-compose up --build
```
