# Testing Patterns

**Analysis Date:** 2026-01-27

## Test Framework

**Runner:**
- pytest (inferred from imports in `tests/test_orchestrator.py`)
- No explicit pytest.ini or pyproject.toml config detected
- No test configuration override settings found

**Assertion Library:**
- pytest built-in assertions (standard `assert` statements)
- unittest.mock for mocking and patching

**Run Commands:**
```bash
pytest tests/ -v              # Run all tests with verbose output
pytest tests/test_orchestrator.py -v  # Run specific test file
pytest tests/ -k test_initial # Run tests matching pattern
```

## Test File Organization

**Location:**
- Co-located in separate `tests/` directory at project root
- Pattern: `tests/test_<module>.py` matches `src/<module>`

**Current Structure:**
```
tests/
├── __init__.py
└── test_orchestrator.py       # Tests for SimulationState and persistence
```

**Naming:**
- Test classes: `Test<ComponentName>` (e.g., `TestSimulationState`, `TestLoadSaveState`)
- Test methods: `test_<what_is_being_tested>` (e.g., `test_initial_state`, `test_record_action`)

## Test Structure

**Suite Organization:**

From `tests/test_orchestrator.py`:

```python
class TestSimulationState:
    """Tests for simulation state management."""

    def test_initial_state(self):
        """Test initial state has correct defaults."""
        state = SimulationState()
        assert state.simulation_day == 1
        assert state.last_run is None
        assert len(state.agents) == 0
```

**Patterns:**

1. **Setup:** Create object under test directly in test method (no complex setup)
2. **Action:** Call method being tested
3. **Assert:** Use simple pytest assertions (`assert <condition>`)
4. **Naming:** Docstring describes what is being tested

**Test Classes:**
- Group related tests by component/feature
- Use class organization for logical grouping, not shared state
- No setup/teardown fixtures currently used

## Mocking

**Framework:** `unittest.mock` (Mock, MagicMock, patch)

**Pattern Observed:**

From test header imports:
```python
from unittest.mock import Mock, MagicMock, patch
```

**Not heavily used in current test suite** - Most tests use real objects:
```python
def test_initial_state(self):
    """Test initial state has correct defaults."""
    state = SimulationState()  # Real object, not mocked
    assert state.simulation_day == 1
```

**When to Mock:**
- Database connections (not yet tested)
- Jira API calls (marked for future tests)
- External HTTP services
- Time-dependent behavior

**When NOT to Mock:**
- State model operations (test with real SimulationState instances)
- Pure computation logic (test directly)

## Fixtures and Factories

**Test Data:**

Not explicitly used yet. Current tests create minimal objects inline:
```python
def test_track_ticket(self):
    """Test ticket tracking."""
    state = SimulationState()
    state.track_ticket("PROJ-123", "In Progress", "dev_1")
    assert "PROJ-123" in state.active_tickets
```

**Future Pattern:**
If test complexity increases, extract shared setup to pytest fixtures:
```python
@pytest.fixture
def base_state():
    """Fixture providing a fresh SimulationState."""
    return SimulationState()

def test_something(base_state):
    base_state.record_action("agent_1", "comment")
    assert base_state.agents["agent_1"].actions_today == 1
```

**Location:**
- Currently tests use inline setup
- If added, conftest.py would go in `tests/conftest.py`

## Coverage

**Requirements:** Not enforced (no coverage config detected)

**View Coverage:**
```bash
pytest tests/ --cov=src --cov-report=html
pytest tests/ --cov=src --cov-report=term-missing
```

**Current State:**
- Only 2 test files with ~12 test methods
- Coverage is limited to SimulationState and state persistence
- No integration or orchestrator tests yet

## Test Types

**Unit Tests:**
- Scope: Individual methods and state operations
- Approach: Test with real dependencies (minimal mocking)
- Examples: `test_record_action()` tests SimulationState.record_action()
- Style: Arrange-Act-Assert (implicit)

```python
def test_record_action(self):
    """Test recording an action updates state correctly."""
    state = SimulationState()  # Arrange
    state.record_action("test_agent", "comment", "PROJ-123")  # Act

    agent = state.agents["test_agent"]  # Assert
    assert agent.actions_today == 1
    assert agent.last_action is not None
```

**Integration Tests:**
- Not yet implemented
- Would test: State persistence (save/load), Jira API interactions, Crew orchestration
- See `TestLoadSaveState` which tests save/load cycle with file I/O:

```python
def test_save_and_load_state(self, tmp_path):
    """Test state can be saved and loaded."""
    state_file = tmp_path / "test_state.json"

    state = SimulationState()
    state.record_action("test_agent", "comment", "PROJ-1")
    state.track_ticket("PROJ-1", "In Progress")

    save_state(state, str(state_file))
    loaded = load_state(str(state_file))

    assert loaded.simulation_day == state.simulation_day
    assert "test_agent" in loaded.agents
```

**E2E Tests:**
- Not used
- Would require Jira instance and n8n setup
- Manual testing via `/trigger` endpoint or Docker deployment

## Common Patterns

**Async Testing:**

Not currently tested (no async test examples found). For future async Jira/LLM operations:
```python
@pytest.mark.asyncio
async def test_async_operation():
    result = await some_async_function()
    assert result is not None
```

**Error Testing:**

Not explicitly tested yet. Pattern for testing error conditions:
```python
def test_invalid_state_raises_error(self):
    """Test that invalid state raises appropriate error."""
    state = SimulationState()

    # Some invalid operation
    with pytest.raises(ValueError, match="Expected error message"):
        state.some_invalid_operation()
```

**Parametrized Tests:**

Not used yet. Pattern for testing multiple inputs:
```python
@pytest.mark.parametrize("input,expected", [
    ("high", 0.7),
    ("medium", 0.5),
    ("low", 0.3),
])
def test_activity_probability(input, expected):
    agent = BaseAgent(config={"activity_level": input})
    assert agent.get_activity_probability() == expected
```

## Testing Strategy

**What IS Tested:**
- SimulationState core operations (record_action, track_ticket, advance_sprint_day)
- State persistence (save to JSON, load from JSON)
- State initialization and defaults
- Daily counter reset
- New day detection

**What's NOT Tested (Coverage Gaps):**
- Agent classes (BaseAgent, PMAgent, DeveloperAgent, etc.)
- Orchestrator coordination logic
- Jira API client methods (complex due to external dependency)
- LLM Service integration
- Crew execution and planning
- Scenario detection and lifecycle

**Testing Best Practices Observed:**
- Descriptive test names and docstrings
- Single assertion focus (though some tests check multiple related assertions)
- No test interdependencies (each test is independent)
- Use of fixtures for file paths (tmp_path)

**Testing Best Practices to Add:**
- Mock external dependencies (Jira API) rather than skip testing
- Add parametrized tests for behavior variations
- Test error conditions explicitly
- Add integration tests for state + Jira sync
- Add tests for each Agent type's action selection

## Test Execution Notes

**System Path Setup:**
Current tests manually add src to path:
```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
```

This should be removed - pytest automatically adds the root directory to sys.path.

**PyTest Invocation:**
```python
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

This allows running tests as standalone script, but prefer pytest CLI.

## Frontend Testing

**Status:** No tests detected in frontend codebase

**Tools Available:**
- Vitest (inferred from tool ecosystem, not configured)
- React Testing Library (not in dependencies)
- Jest (not configured)

**Future Testing Approach for Frontend:**
If testing is added, use React + TypeScript conventions:
```typescript
import { render, screen } from '@testing-library/react';
import { SprintStatusCard } from '@/components/dashboard/SprintStatusCard';

describe('SprintStatusCard', () => {
  it('should display sprint progress', () => {
    const sprint = { name: 'Sprint 1', day: 3, totalDays: 14 };
    render(<SprintStatusCard sprint={sprint} />);

    expect(screen.getByText('Day 3 of 14')).toBeInTheDocument();
  });
});
```

---

*Testing analysis: 2026-01-27*
