# 🎭 Jira Team Simulator

> Generate realistic development team activity in Jira for analytics testing and team dynamics simulation

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9+-green.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-00a393.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61dafb.svg)](https://react.dev)
[![Status](https://img.shields.io/badge/Status-Active-brightgreen.svg)](#)

---

## 🚀 What is This?

A multi-agent simulation that creates **9 realistic developers** across **2 teams** working on your Jira project. Perfect for testing productivity dashboards, analytics pipelines, and workflow automation without needing to manually create tickets.

**What gets generated:**
- ✅ Status transitions through your workflow
- 💬 AI-generated contextual comments
- 📝 New stories and bug reports
- ⏱️ Work time logs
- 🔗 Realistic team dynamics (blockers, rework, dependencies)

---

## 📊 Dashboard Preview

![Jira Simulator Dashboard](/docs/images/Jira_Sim_screenshot.png)

**Live visualization includes:**
- Real-time sprint progress and metrics
- Team workload distribution
- Active scenarios and blockers
- Velocity trends and burndown charts
- Interactive PM chat interface

---

## 🏗️ System Architecture

```
┌──────────────────┐
│  React Frontend  │ (Dashboard, Chat, Settings)
│   Port: 5173     │
└────────┬─────────┘
         │ HTTP
         ↓
┌──────────────────┐
│  FastAPI Backend │
│   Port: 8000     │
└────┬────────┬────┘
     │        │
     ↓        ↓
┌────────────────────┐
│ Orchestrator       │ ← Agents (PM, Dev, QA, TL)
│ State Management   │
└────────┬───────────┘
         │
         ↓
    Jira API
```

**Trigger Flow:** n8n → `/trigger` → Orchestrator → Agents → Jira

---

## ⚡ Quick Start

### 1️⃣ Prerequisites

- Docker & Docker Compose
- Jira Cloud account with API token
- Anthropic API key (for Claude LLM)

### 2️⃣ Configuration

```bash
# Copy and configure environment
cp .env.example .env
# Edit .env with your credentials:
# JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN, ANTHROPIC_API_KEY
```

### 3️⃣ Map Agent Accounts

Edit `config/personas.yaml` and add Jira account IDs for all 9 agents:

```yaml
agents:
  alpha_pm:
    jira_account_id: "557058:12a3b4c5-d6e7-4f8g-9h0i-1j2k3l4m5n6o"
    # ... more agents
```

### 4️⃣ Deploy

```bash
# Start the full stack (backend + frontend + database)
docker-compose up --build

# Backend: http://localhost:8000
# Frontend: http://localhost:5173
```

### 5️⃣ Configure Trigger (Optional)

Create an n8n workflow:
- **Trigger:** Cron `0 */45 9-17 * * 1-5` (every 45 min, M-F 9-5)
- **Action:** POST to `http://jira-simulator:8000/trigger`

---

## 🎮 Usage

### Via Frontend Dashboard

1. **Visit** `http://localhost:5173`
2. **View** real-time sprint metrics and team activity
3. **Filter** by team (Alpha/Beta)
4. **Chat** with PMs to query sprint activity
5. **Toggle** dark mode and theme

### Via API

```bash
# Trigger one simulation tick
curl -X POST http://localhost:8000/trigger \
  -H "Content-Type: application/json" \
  -d '{"intensity": "normal"}'

# View current state
curl http://localhost:8000/state

# Reset simulation
curl -X POST http://localhost:8000/reset
```

### API Intensity Levels

| Level | Actions/Tick | Probability | Use Case |
|-------|-------------|-------------|----------|
| **light** | 1-2 | 20% | Slow day, meetings |
| **normal** | 2-4 | 60% | Regular work day |
| **busy** | 4-6 | 20% | Sprint deadline |

---

## 👥 Team Structure

### Team Alpha
| Role | Agent |
|------|-------|
| 👔 Product Manager | Sarah Chen |
| 👨‍💼 Tech Lead | Marcus Johnson |
| 🚀 Senior Dev | Elena Rodriguez |
| 👨‍💻 Mid Dev | James Park |
| 🧪 QA Engineer | Priya Sharma |

### Team Beta
| Role | Agent |
|------|-------|
| 👔 Product Manager | David Kim |
| 👨‍💻 Senior Dev | Ana Costa |
| 🎓 Junior Dev | Tyler Brooks |
| 🧪 QA Engineer | Rachel Green |

---

## 📚 What's Simulated

### Normal Workflow (60%)
```
Backlog → In Progress → Code Review → Testing → Done
```
**Timeline:** 3-7 days for stories

### Blockers (15%)
```
In Progress → BLOCKED → Discussion → Unblocked → Continue
```
**Causes:** External API, design clarification, dependencies

### Rework (15%)
```
Testing → REJECTED → In Progress → Testing → Done
```
**Reason:** QA finds issues, especially with junior devs

### Sprint Planning & Scope Creep (10%)
```
Mid-sprint story creation → Team discussion → Added to sprint
```

---

## 🛠️ Development

### Backend

```bash
# Install dependencies
pip install -r requirements.txt

# Run with hot reload
uvicorn src.main:app --reload

# Run tests
pytest tests/ -v
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Development server
npm run dev

# Build for production
npm run build

# Lint and format
npm run lint
```

---

## 📋 Configuration Files

| File | Purpose |
|------|---------|
| `config/settings.yaml` | Simulation parameters, LLM models, cycle times |
| `config/personas.yaml` | Agent definitions and Jira account mappings |
| `config/templates.yaml` | Comment templates (reduces LLM costs) |
| `.env` | API keys and credentials |

---

## 💰 Cost Estimation

- **LLM:** ~$0.50-1.50/day (Haiku for routine, Sonnet for complex)
- **Jira:** Free tier (10 users)
- **Infrastructure:** Docker (local or cloud)

---

## 📖 Documentation

- **[How It Works](docs/how-it-works.md)** - Deep dive into agent behaviors and scenarios
- **[CLAUDE.md](CLAUDE.md)** - Development guidance and architecture details
- **[Frontend Plan](docs/frontend-plan.md)** - UI/UX design and features

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

---

## 📄 License

MIT - Use freely for testing and analytics

---

## 🎯 Next Steps

- Deploy frontend to production
- Add WebSocket support for real-time chat
- Integrate with more Jira projects
- Expand agent personalities and behaviors

