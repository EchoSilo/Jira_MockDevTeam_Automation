# Technology Stack

**Analysis Date:** 2026-01-27

## Languages

**Primary:**
- Python 3.11 - Backend orchestration, agent logic, Jira integration
- TypeScript 5.9.3 - Frontend type-safe development
- JavaScript - Frontend build tooling and node runtime

**Secondary:**
- YAML - Configuration files (`config/settings.yaml`, `config/personas.yaml`)
- JSON - State persistence, API responses

## Runtime

**Environment:**
- Python 3.11-slim (Docker image)
- Node.js 20-slim (Docker image for frontend build)
- Browser runtime (React 19.2.0)

**Package Manager:**
- Python: pip
- Node/Frontend: npm
- Lockfile: `package-lock.json` (frontend), `requirements.txt` (backend)

## Frameworks

**Core (Backend):**
- FastAPI 0.109.0+ - REST API and server framework
- Uvicorn 0.27.0+ - ASGI server
- Pydantic 2.6.1+ - Data validation and settings management
- Pydantic Settings 2.1.0+ - Configuration management

**Agent Orchestration:**
- CrewAI 0.80.0+ - Multi-agent orchestration framework
- CrewAI Tools 0.14.0+ - Agent tooling and capabilities

**LLM Integration:**
- Anthropic 0.40.0+ - Claude API client (native)
- LiteLLM 1.0.0+ - Multi-provider LLM routing (abstracts Anthropic, OpenAI, OpenRouter, Gemini)

**Frontend:**
- React 19.2.0 - UI framework
- Vite 7.2.4 - Frontend bundler and dev server
- React Router 7.11.0 - Client-side routing
- Zustand 5.0.9 - State management
- Recharts 3.6.0 - Data visualization (charts/graphs)

**UI & Styling (Frontend):**
- TailwindCSS 3.4.17 - Utility-first CSS
- Radix UI - Accessible component library (`@radix-ui/react-*` packages)
- class-variance-authority 0.7.1 - Component variant management
- Lucide React 0.561.0 - Icon library
- clsx 2.1.1 - CSS class composition

**Testing/Quality (Frontend):**
- ESLint 9.39.1 - JavaScript linting
- TypeScript ESLint 8.46.4 - TypeScript linting rules
- Autoprefixer 10.4.23 - CSS vendor prefixing
- PostCSS 8.5.6 - CSS transformation

## Key Dependencies

**Critical (Backend):**
- jira 3.6.0 - Jira Python API client
- httpx 0.26.0 - Async HTTP client for external requests
- python-dotenv 1.0.0 - Environment variable loading
- PyYAML 6.0.1 - YAML parsing for configuration

**Document Generation:**
- python-docx 0.8.11 - Word document (.docx) generation
- python-pptx 0.6.21 - PowerPoint presentation (.pptx) generation

**Frontend:**
- react-markdown 10.1.0 - Markdown rendering in React
- react-masonry-css 1.0.16 - Masonry layout for dashboard cards
- @types/react 19.2.5, @types/react-dom 19.2.3 - TypeScript definitions
- @vitejs/plugin-react 5.1.1 - Vite React plugin

## Configuration

**Environment:**
- Configuration via `.env` file (see `.env.example`)
- Environment variables for Jira, LLM providers, and project settings
- Loaded by `python-dotenv` before application startup

**Build:**
- `frontend/tsconfig.json` - TypeScript compiler config
- `frontend/vite.config.ts` - Vite bundler configuration
- `tailwind.config.js` - TailwindCSS configuration
- `.eslintrc.json` - ESLint rules
- `docker-compose.yml` - Multi-stage Docker build with frontend compilation

**Application Config Files:**
- `config/settings.yaml` - Simulation parameters, LLM models, cycle times, sprint config, agent workload limits
- `config/personas.yaml` - Agent definitions with Jira account IDs, personas, team assignments
- `config/templates.yaml` - Comment templates for routine actions (reduces LLM token usage)

## Platform Requirements

**Development:**
- Python 3.11+
- Node.js 20+
- pip package manager
- npm package manager
- Docker (optional, for containerized deployment)

**Production:**
- Docker image (Python 3.11-slim + Node.js build artifacts)
- Deployment target: Any Docker-compatible host or orchestration platform
- External: Jira instance (Cloud or Server) with API token auth
- External: LLM API (Anthropic, OpenAI, OpenRouter, or Google Gemini via LiteLLM)

## Database & Persistence

**State Storage:**
- `data/state.json` - JSON file containing simulation state, agent workloads, active scenarios
- In-memory caching for Jira status and dashboard queries

**Logging Storage:**
- `data/logs.db` - SQLite database for audit trail, LLM call logs, Jira API logs, agent decisions
- No external database required; SQLite embedded

## Deployment Architecture

**Docker Image:**
- Multi-stage build: Frontend built in Node.js container, artifacts copied to Python container
- Frontend: Vite-compiled to `frontend/dist`, served by FastAPI static file handler
- Backend: Python uvicorn server at `0.0.0.0:8000`
- Volumes: `./data` (state and logs), `./config` (settings)
- Network: Connects to `n8n_default` network for n8n integration

---

*Stack analysis: 2026-01-27*
