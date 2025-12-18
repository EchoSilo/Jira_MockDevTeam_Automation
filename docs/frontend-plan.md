# Jira Team Simulator - Frontend Application Plan

## Status: Ready for Implementation

## Overview
Transform the Jira Team Simulator from a headless API into a full-fledged application with:
1. **Interactive PM Chat** - Natural language chat with PM agents (Sarah Chen, David Kim)
2. **Real-time Dashboard** - Modern UI with sprint progress, developer workload, historical trends
3. **Live WebSocket Updates** - Real-time activity feed and state changes

## Technology Stack
- **Frontend**: React 18 + TypeScript + Vite
- **Styling**: Tailwind CSS + Material UI (MUI)
- **Charts**: Recharts (React-native, TypeScript-friendly)
- **State**: Zustand (client) + React Query (server state)
- **Real-time**: WebSocket for live updates
- **Deployment**: Single container (FastAPI serves React build)

---

## Project Structure

```
jira-team-simulator/
├── frontend/                        # NEW: React application
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── index.css
│       ├── components/
│       │   ├── common/              # Layout, Header, Sidebar, ThemeToggle
│       │   ├── chat/                # ChatContainer, ChatMessage, PMSelector
│       │   └── dashboard/           # Cards, Charts, ActivityFeed
│       ├── hooks/                   # useWebSocket, useTheme, useDashboardData
│       ├── services/                # API client, WebSocket client
│       ├── store/                   # Zustand stores
│       ├── types/                   # TypeScript interfaces
│       └── pages/                   # DashboardPage, ChatPage
│
├── src/                             # Existing FastAPI backend
│   ├── api/                         # NEW: API module
│   │   ├── __init__.py
│   │   ├── chat.py                  # PM chat endpoints
│   │   ├── dashboard.py             # Dashboard data endpoints
│   │   └── websocket.py             # WebSocket handler
│   └── ... (existing files)
│
└── Dockerfile                       # Updated for multi-stage build
```

---

## Backend API Changes

### New Endpoints

#### PM Chat API (`src/api/chat.py`)
```
POST /api/chat/message
  - pm_id: "alpha_pm" | "beta_pm"
  - message: string
  - conversation_id: optional string
  → Returns PM response with context

GET /api/chat/history/{conversation_id}
  → Returns conversation messages
```

#### Dashboard API (`src/api/dashboard.py`)
```
GET /api/dashboard/snapshot?team=all|alpha|beta
  → Sprint status, status breakdown, agent workloads, scenarios

GET /api/dashboard/metrics/velocity?sprints=5
  → Historical velocity data for charts

GET /api/dashboard/metrics/burndown?sprint=current
  → Burndown data for current sprint

GET /api/dashboard/activity?limit=50&team=all
  → Recent activity feed
```

#### WebSocket (`src/api/websocket.py`)
```
WS /api/ws/updates
  → Broadcasts: tick_complete, action_taken, state_change events
```

### Database Schema Additions (`src/logging/database.py`)
```sql
-- Sprint metrics for velocity charts
CREATE TABLE sprint_metrics (
    sprint_number INTEGER, items_completed INTEGER, ...
);

-- Daily snapshots for burndown
CREATE TABLE daily_snapshots (
    snapshot_date TEXT, remaining_items INTEGER, ...
);

-- Chat persistence
CREATE TABLE chat_conversations (...);
CREATE TABLE chat_messages (...);
```

### Modified Files
- [src/main.py](src/main.py) - Add static file serving, mount API routers, WebSocket support
- [src/logging/database.py](src/logging/database.py) - Add new tables
- [src/services/llm_service.py](src/services/llm_service.py) - Add PM chat method
- [Dockerfile](Dockerfile) - Multi-stage build with Node.js

---

## Implementation Phases

### Phase 1: Foundation
**Goal**: React project setup + basic FastAPI integration

**Backend**:
- Create `src/api/` module structure
- Add `/api/dashboard/snapshot` endpoint (refactor from `/state`)
- Configure CORS for development
- Update `main.py` to serve static files from `frontend/dist`

**Frontend**:
- Initialize Vite + React + TypeScript project
- Configure Tailwind CSS + MUI
- Create Layout with dark/light theme toggle
- Build basic DashboardPage with mock data

**Files to create/modify**:
- `frontend/` (entire new directory)
- `src/api/__init__.py`, `src/api/dashboard.py`
- `src/main.py` (add static serving + new router)

---

### Phase 2: Real-time Dashboard
**Goal**: Live dashboard with team filtering + WebSocket

**Backend**:
- Implement full `/api/dashboard/snapshot` with team filtering
- Add `/api/dashboard/activity` endpoint
- Create WebSocket endpoint `/api/ws/updates`
- Modify orchestrator to broadcast tick completions

**Frontend**:
- Build dashboard components:
  - SprintStatusCard (sprint name, day X/Y, progress bar)
  - StatusBreakdown (horizontal bar: Backlog → Done)
  - WorkloadCard with AgentCards (avatar, tickets, status)
  - ScenarioDistribution (pie chart)
  - ActivityFeed (auto-scrolling)
- Implement useWebSocket hook
- Add TeamFilter (All / Alpha / Beta)

**Files to create/modify**:
- `src/api/websocket.py`
- `src/orchestrator/orchestrator.py` (broadcast events)
- `frontend/src/components/dashboard/*`
- `frontend/src/hooks/useWebSocket.ts`

---

### Phase 3: Historical Charts
**Goal**: Velocity and burndown visualization

**Backend**:
- Add `sprint_metrics` and `daily_snapshots` tables
- Record snapshots after each tick
- Implement `/api/dashboard/metrics/velocity`
- Implement `/api/dashboard/metrics/burndown`

**Frontend**:
- VelocityChart (Recharts line chart, last 5 sprints)
- BurndownChart (Recharts area chart, current sprint)
- Date range selector for historical views

**Files to create/modify**:
- `src/logging/database.py` (add tables)
- `src/api/dashboard.py` (metrics endpoints)
- `frontend/src/components/dashboard/VelocityChart.tsx`
- `frontend/src/components/dashboard/BurndownChart.tsx`

---

### Phase 4: PM Chat Interface
**Goal**: Interactive chat with PM agents

**Backend**:
- Create `src/api/chat.py` router
- Implement PMChatService:
  - Uses LLMService with PM persona + board context
  - Stores conversation history in SQLite
- Add chat tables to database
- Parse commands (create story, check blockers, etc.)

**Frontend**:
- ChatPage layout
- PMSelector (Sarah Chen / David Kim tabs)
- ChatContainer with message list
- ChatMessage with Markdown + ticket link detection
- SuggestedQuestions ("Sprint status?", "Who's overloaded?")
- ChatInput with typing indicator

**Files to create/modify**:
- `src/api/chat.py`
- `src/services/pm_chat_service.py` (new)
- `src/logging/database.py` (chat tables)
- `frontend/src/pages/ChatPage.tsx`
- `frontend/src/components/chat/*`

---

### Phase 5: Polish & Deployment
**Goal**: Production-ready deployment

**Backend**:
- Health check updates
- Rate limiting for chat
- Environment configuration

**Frontend**:
- Error boundaries
- Loading skeletons
- Mobile responsive
- Accessibility (keyboard nav, ARIA)

**Deployment**:
- Update Dockerfile (multi-stage build)
- Test on Google Cloud Run

**Files to create/modify**:
- `Dockerfile` (multi-stage)
- `frontend/src/components/common/ErrorBoundary.tsx`

---

## Dockerfile (Multi-Stage Build)

```dockerfile
# Stage 1: Build React frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend with static files
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
COPY config/ ./config/
COPY --from=frontend-builder /app/frontend/dist ./static
RUN mkdir -p /app/data
EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Key Integration Points

### PM Chat Context Injection
The chat service will inject:
- PM persona from `config/personas.yaml`
- Board snapshot from `ScenarioAnalyzer.get_board_snapshot()`
- Current sprint state from `SimulationState`
- Conversation history for continuity

### WebSocket Event Broadcasting
After `orchestrator.run_tick()` completes:
1. Serialize tick summary (actions, state changes)
2. Broadcast to all connected WebSocket clients
3. Frontend updates dashboard store reactively

### Static File Serving
In `main.py`, after API routes:
```python
app.mount("/assets", StaticFiles(directory="static/assets"))

@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    # Serve index.html for SPA routing (non-API routes)
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| WebSocket complexity | Implement polling fallback (10s) |
| SQLite write contention | Use existing AsyncLogWriter queue |
| Chat latency | Show typing indicator |
| Missing historical data | "Gathering data..." until sufficient |
