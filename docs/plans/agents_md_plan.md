# Plan: Creation of AGENTS.md Files

**Date:** 2026-01-24
**Goal:** Create concise `AGENTS.md` files to assist AI agents in navigating and modifying the Jira Team Simulator codebase.

## 1. Root `AGENTS.md` (Backend & General)

**Location:** `./AGENTS.md`
**Scope:** Backend (Python/FastAPI), Orchestration, Agent Logic, Docker, General Project Structure.

**Content Outline:**
*   **Project Context**: Brief summary of the Jira Team Simulator.
*   **Tech Stack**:
    *   Python 3.12+, FastAPI, Uvicorn.
    *   CrewAI (Agents), Anthropic LLM (Haiku/Sonnet).
    *   Docker & Docker Compose.
*   **Key Commands**:
    *   `docker-compose up --build` (Primary run command).
    *   `pip install -r requirements.txt` (Local setup).
    *   `uvicorn src.main:app --reload` (Local run).
    *   `pytest tests/` (Testing).
*   **Core Architecture**:
    *   **Trigger Flow**: `n8n` -> `/trigger` -> `Orchestrator` -> `Agents` -> `Jira`/`State`.
    *   **State Management**: `data/state.json` is the source of truth; synced with Jira.
    *   **Agents**: Inherit from `BaseAgent`, use `act()` method.
*   **Critical Patterns**:
    *   **Simulation Loop**: Day advancement, Sprint lifecycle logic.
    *   **LLM Integration**: `LLMService` handles prompts and routing.
*   **Code Conventions**:
    *   Pydantic models for data structures.
    *   Type hinting required.

## 2. Frontend `AGENTS.md`

**Location:** `frontend/AGENTS.md`
**Scope:** Frontend (React), UI Components, State Management.

**Content Outline:**
*   **Tech Stack**:
    *   React 19, Vite, TypeScript.
    *   TailwindCSS, Radix UI.
    *   Zustand (State), Recharts (Viz).
*   **Key Commands**:
    *   `npm install`
    *   `npm run dev`
    *   `npm run build`
    *   `npm run lint`
*   **Architecture**:
    *   **Dashboard**: `DashboardPage.tsx` consumes API data.
    *   **Real-time Updates**: Polling (15s) + WebSocket (Chat).
    *   **Component Structure**: `components/dashboard/`, `components/chat/`, `components/common/`.
*   **Critical Patterns**:
    *   **Data Fetching**: Custom hooks in `src/hooks/`.
    *   **Mock Data**: `src/lib/mockData.ts` for fallback.
*   **Code Conventions**:
    *   Functional Components.
    *   Tailwind utility classes.
    *   Strict TypeScript.

## Execution Steps

1.  Create `./AGENTS.md` with the content defined above.
2.  Create `frontend/AGENTS.md` with the content defined above.
3.  Verify files are correctly placed and formatted.
