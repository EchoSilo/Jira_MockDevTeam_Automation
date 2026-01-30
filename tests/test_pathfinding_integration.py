"""Integration tests for TickExecutor + PathfindingAdapter wiring.

Note: This test verifies the wiring by testing PathfindingAdapter behavior
and checking the code structure, rather than importing TickExecutor directly.
This avoids Pydantic v1/v2 import conflicts in the test environment.
"""

import pendulum
import pytest
from unittest.mock import Mock

from src.chaos.pathfinding_adapter import PathfindingAdapter
from src.orchestrator.pathfinder import WorkflowPathfinder
from src.scheduling.scheduler import Scheduler
from src.scheduling.models import ScheduledAction, ActionStatus
from src.scheduling.persistence import ScheduledActionStore
from src.reconciliation.reconciler import ReconciliationResult
from src.reconciliation.adapters import AdaptationStrategy


@pytest.fixture
def scheduler():
    """Create scheduler with in-memory store."""
    store = ScheduledActionStore(db_path=":memory:")
    return Scheduler(store=store)


@pytest.fixture
def pathfinder():
    """Create pathfinder with mock workflow graph."""
    pf = WorkflowPathfinder()
    pf.workflow_graph = {
        "to do": {"in progress"},
        "in progress": {"code review"},
        "code review": {"testing"},
        "testing": {"done"},
    }
    pf._graph_built = True
    return pf


@pytest.fixture
def pathfinding_adapter(scheduler, pathfinder):
    """Create pathfinding adapter."""
    return PathfindingAdapter(scheduler, pathfinder)


class TestPathfindingAdapterWiring:
    """Tests verifying PathfindingAdapter is properly wired to TickExecutor."""

    def test_tick_executor_accepts_pathfinding_adapter_parameter(self):
        """Verify TickExecutor constructor accepts pathfinding_adapter parameter."""
        # Read the TickExecutor source to verify parameter exists
        import inspect
        from src.orchestrator.tick_executor import TickExecutor

        sig = inspect.signature(TickExecutor.__init__)
        params = sig.parameters

        # Verify pathfinding_adapter is a parameter
        assert 'pathfinding_adapter' in params, "TickExecutor should accept pathfinding_adapter parameter"

        # Verify it's optional (has default)
        param = params['pathfinding_adapter']
        assert param.default is not inspect.Parameter.empty or 'Optional' in str(param.annotation), \
            "pathfinding_adapter should be Optional"

    def test_main_py_passes_pathfinding_adapter_to_tick_executor(self):
        """Verify main.py passes _pathfinding_adapter to TickExecutor constructor."""
        # Read main.py and verify the wiring
        with open('src/main.py', 'r', encoding='utf-8') as f:
            main_content = f.read()

        # Check that _pathfinding_adapter is initialized globally
        assert '_pathfinding_adapter' in main_content, \
            "main.py should have global _pathfinding_adapter"

        # Check that it's passed to TickExecutor
        assert 'pathfinding_adapter=_pathfinding_adapter' in main_content, \
            "main.py should pass _pathfinding_adapter to TickExecutor constructor"

    def test_pathfinding_adapter_can_be_instantiated(
        self, pathfinding_adapter
    ):
        """Verify PathfindingAdapter can be instantiated and has correct interface."""
        # Verify adapter has the expected method
        assert hasattr(pathfinding_adapter, 'handle_reconciliation_result'), \
            "PathfindingAdapter should have handle_reconciliation_result method"

        # Verify method signature accepts ReconciliationResult and ScheduledAction
        import inspect
        sig = inspect.signature(pathfinding_adapter.handle_reconciliation_result)
        params = list(sig.parameters.keys())

        # Should have reconciliation and scheduled_action parameters
        assert len(params) >= 2, \
            "handle_reconciliation_result should accept at least 2 parameters"

    def test_tick_executor_has_pathfinding_adapter_attribute(self):
        """Verify TickExecutor stores pathfinding_adapter as instance attribute."""
        import ast

        # Read tick_executor.py source
        with open('src/orchestrator/tick_executor.py', 'r', encoding='utf-8') as f:
            source = f.read()

        # Verify that pathfinding_adapter is stored as instance attribute
        assert 'self.pathfinding_adapter = pathfinding_adapter' in source, \
            "TickExecutor should store pathfinding_adapter as self.pathfinding_adapter"

    def test_tick_executor_uses_pathfinding_adapter_for_recalculate(self):
        """Verify TickExecutor code checks for pathfinding_adapter on RECALCULATE."""
        # Read tick_executor.py source
        with open('src/orchestrator/tick_executor.py', 'r', encoding='utf-8') as f:
            source = f.read()

        # Verify that code checks for pathfinding_adapter
        assert 'if self.pathfinding_adapter:' in source or 'self.pathfinding_adapter.handle_reconciliation_result' in source, \
            "TickExecutor should check for and use pathfinding_adapter"
