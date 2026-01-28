# Coding Conventions

**Analysis Date:** 2026-01-27

## Naming Patterns

**Files:**
- Python: snake_case (e.g., `base_agent.py`, `jira_client.py`, `simulation_state.py`)
- TypeScript/TSX: camelCase for utility files (e.g., `useApi.ts`, `dashboardStore.ts`) and PascalCase for components (e.g., `SprintStatusCard.tsx`, `ChatContainer.tsx`)
- Directories: snake_case (e.g., `src/services/`, `src/crews/`, `src/agents/`)

**Functions:**
- Python: snake_case functions throughout (e.g., `get_agent_state()`, `record_action()`, `get_all_statuses()`)
- TypeScript: camelCase for all functions (e.g., `useDashboardData()`, `transformSprint()`, `handleGenerateNotes()`)
- React hooks: camelCase prefixed with `use` (e.g., `useApi()`, `useDashboardStore()`, `useQuery()`)

**Variables:**
- Python: snake_case for module-level and class variables (e.g., `agent_id`, `jira_client`, `_status_cache`)
- TypeScript: camelCase for all variables (e.g., `selectedTeam`, `isLoading`, `onSuccessRef`)
- React state: camelCase with semantic prefixes (e.g., `isLoading`, `hasError`, `selectedTeam`)

**Types:**
- Python: PascalCase for classes (e.g., `BaseAgent`, `JiraClient`, `SimulationState`)
- Python: UPPER_SNAKE_CASE for constants (e.g., `BOARD_ID`, `ISSUE_TYPE_TO_COMPLEXITY`, `CYCLE_TIME_RANGES`)
- Python: PascalCase for Enum classes (e.g., `ScenarioType`, `ScenarioPhase`, `TicketComplexity`)
- TypeScript: PascalCase for interfaces and types (e.g., `DashboardState`, `Sprint`, `Agent`)
- TypeScript: UPPER_SNAKE_CASE for constants (e.g., `API_BASE_URL`)

## Code Style

**Formatting:**
- Python: Black-style formatting (inferred from codebase patterns)
- TypeScript: ESLint configured, follows ESLint 9.39.1 standards
- Line length: Flexible, no strict limit observed

**Linting:**
- Python: No linter explicitly configured in project
- TypeScript: ESLint 9.39.1 with:
  - TypeScript ESLint strict config (`tseslint.configs.recommended`)
  - React Hooks plugin (`reactHooks.configs.flat.recommended`)
  - React Refresh plugin for Vite (`reactRefresh.configs.vite`)
  - ESLint JS recommended config
  - See: `frontend/eslint.config.js`

**Language Versions:**
- Python: 3.x (FastAPI, Pydantic v2)
- TypeScript: 5.9.3
- Node: Inferred from package.json (no explicit version specified)

## Import Organization

**Python Order:**
1. Standard library imports (`import logging`, `import os`, `from datetime import...`)
2. Third-party imports (`from fastapi import`, `from pydantic import`, `import yaml`)
3. Local imports (`from ..services import`, `from ..state import`)
4. TYPE_CHECKING imports for forward references (at end of imports block)

Example from `src/orchestrator/orchestrator.py`:
```python
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Optional, TYPE_CHECKING

from ..services.jira_client import JiraClient
from ..services.llm_service import LLMService
from ..tools.jira_tools import JiraTools
from ..state import SimulationState, ActiveScenario, ScenarioType

if TYPE_CHECKING:
    from ..logging import AsyncLogWriter
```

**TypeScript Order:**
1. React imports (`import { useState } from 'react'`)
2. Third-party UI/utility imports (`import { AlertTriangle } from 'lucide-react'`)
3. Local imports with `@` alias (`import { Header } from '@/components/common'`)
4. Type imports (`import type { Sprint } from '@/types'`)

Example from `frontend/src/pages/DashboardPage.tsx`:
```typescript
import { useState } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { Header, Tabs } from '@/components/common';
import { useDashboardStore } from '@/store';
import type { OutputFormat } from '@/lib/api';
```

**Path Aliases:**
- TypeScript: `@` alias maps to `frontend/src/` (configured in `vite.config.ts`)
- Use for: All local imports across components, stores, hooks, types, lib

## Error Handling

**Python Patterns:**

Use try-except blocks with logging for API operations and I/O:
```python
try:
    statuses = self._client.statuses()
    self._status_cache = [...]
    return self._status_cache
except Exception as e:
    logger.error(f"Failed to fetch statuses: {e}")
    return []
```

Graceful degradation: Return sensible defaults (empty list, None, False) rather than raising to caller when appropriate for non-critical operations. Critical operations in orchestrator log and propagate exceptions.

**TypeScript Patterns:**

Wrap async operations in try-catch:
```typescript
try {
    setIsLoading(true);
    const result = await queryFnRef.current();
    if (mountedRef.current) {
        setData(result);
        setError(null);
        onSuccessRef.current?.(result);
    }
} catch (err) {
    if (mountedRef.current) {
        const apiError = err instanceof ApiError ? err : new ApiError(...);
        setError(apiError);
    }
}
```

Always check `mountedRef.current` before state updates in React hooks to prevent memory leaks from async operations.

Custom error class: `ApiError` from `src/lib/api.ts` wraps HTTP errors with status and message.

## Logging

**Framework:** Python `logging` module + FastAPI logging

**Patterns:**

Python:
```python
logger = logging.getLogger(__name__)

# In methods/functions
logger.error(f"Failed to fetch statuses: {e}")
logger.warning(f"Jira connectivity check failed: {e}")
```

Get logger at module level with `__name__` (standard Python practice).

TypeScript:
- Use `console.error()` for errors and warnings
- No structured logging framework detected in frontend
- Example from `DashboardPage.tsx`: `console.error('Failed to generate notes:', err)`

## Comments

**When to Comment:**
- Add docstrings to all classes and public methods (Python)
- Docstrings explain purpose, not implementation details
- Add inline comments for non-obvious logic (e.g., caching decisions, workflow rules)
- Explain the "why" not the "what"

**Python Docstrings:**
```python
def log_work_time(self, issue_key: str) -> Optional[dict]:
    """Log a random amount of work time."""
    # Random work time: 15m to 2h
    minutes = random.choice([15, 30, 45, 60, 90, 120])
```

Module-level docstrings at top:
```python
"""
Jira API client wrapper for the simulator.
Handles all Jira interactions with proper authentication per agent.
"""
```

**TypeScript Comments:**
- JSDoc for exported functions and components
- Inline comments sparingly for complex logic
- Example: `frontend/src/lib/api.ts` has inline comments explaining API base URL setup

## Function Design

**Size:**
- Python: Methods typically 20-50 lines (modest scope)
- TypeScript: Hooks and components typically 40-100 lines

**Parameters:**
- Python: Use explicit parameters, avoid huge config dicts where possible. Properties are accessed via self.
- TypeScript: Use object destructuring for multiple props in React components:
  ```typescript
  interface SprintStatusCardProps {
    sprint: Sprint;
  }
  export function SprintStatusCard({ sprint }: SprintStatusCardProps) { ... }
  ```

**Return Values:**
- Python: Explicit return types in signatures (e.g., `-> Optional[dict]`, `-> list[str]`)
- TypeScript: Use `type` keyword for exported types, explicit return types on functions
- Return `null` for missing data (not undefined)

## Module Design

**Exports:**

Python:
- Expose classes and key functions via `__init__.py` files
- Example: `src/services/__init__.py` exports `JiraClient`, `LLMService`
- Keep implementation details private (prefix with `_` if needed)

TypeScript:
- Use barrel exports for components: `frontend/src/components/common/index.ts` exports all common components
- Export types from same file as implementation
- Example: `ChatMessage` type and component exported together from `ChatMessage.tsx`

**Barrel Files:**
- Used extensively in frontend to simplify imports
- `frontend/src/store/index.ts`: exports all stores
- `frontend/src/components/dashboard/index.ts`: exports all dashboard components
- Reduces import paths: `import { useDashboardStore } from '@/store'` vs `import { useDashboardStore } from '@/store/dashboardStore'`

## Typing

**Python:**
- Use type hints on function signatures (seen in all files)
- Use `Optional[T]` for nullable types
- Use `list[T]` instead of `List[T]` (modern Python 3.9+)
- Use `TYPE_CHECKING` import guard for forward references to avoid circular imports:
  ```python
  if TYPE_CHECKING:
      from src.scenarios import SprintScenario
  ```

**TypeScript:**
- Strict typing enforced (tsconfig.json strict mode)
- Use `interface` for object shapes, `type` for unions/aliases
- Import types with `import type { Type }` to avoid runtime cost
- Generic types for reusable patterns (e.g., `useQuery<T>()`)

## Pydantic Models

**Patterns:**
- Use Pydantic v2 `BaseModel` for data validation
- Example models in `src/state/models.py`:
  ```python
  class ScenarioType(str, Enum):
      """Types of scenarios that can unfold on a ticket."""
      NORMAL_FLOW = "normal_flow"
      BLOCKER = "blocker"
  ```
- Use `Field()` for defaults and validation metadata
- Use `AliasChoices` for flexible JSON parsing: `field: type = Field(validation_alias=AliasChoices(...))`
- Use `PrivateAttr()` for non-serialized internal state

---

*Convention analysis: 2026-01-27*
