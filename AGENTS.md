# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## 🚀 Critical Project Constraints
- **Docker Rebuilds**: You MUST rebuild the container (`docker-compose up --build`) after ANY change to `src/`, `frontend/src/`, or `config/`. Hot-reloading only works for local `uvicorn` dev.
- **Board ID**: The Jira Board ID is HARDCODED as `4` in `src/services/jira_client.py`. Do not attempt to configure it via env vars without code changes.
- **Environment Loading**: `load_dotenv()` MUST be called before other imports in `src/main.py` or the app will fail to initialize.
- **Sprint Required**: Actions like `pick_up_task` in `src/orchestrator/orchestrator.py` explicitly check for sprint membership.

## 🧩 Non-Obvious Patterns
- **State Caching**: `SimulationState` is cached in memory for 5s (`CachedState` in `src/main.py`). Do not assume disk reads (`data/state.json`) are instant or perfectly authorized in high-frequency loops.
- **Jira Status Caching**: `JiraClient` caches workflow statuses for 1 hour. If you add a status in Jira, it won't appear in the sim until cache invalidation or restart.
- **LLM Routing**: The system splits logic between "Routine" (Haiku) and "Complex" (Sonnet) models. This is configured in `src/orchestrator/orchestrator.py` and `config/settings.yaml`.
- **Event-Driven**: The system is passive. It does NOTHING until `POST /trigger` is called (by n8n or manually).

## 🛠 Testing & Debugging
- **Logs**: `docker-compose logs -f jira-simulator` is your primary source of truth.
- **State Reset**: `POST /reset` clears `data/state.json`. Use this instead of manually deleting the file to ensure in-memory caches are cleared.
