"""Integration tests for orchestrator reconciliation functionality.

Tests the integration of reconciliation components (validators, reconciler,
execution tracker, circuit breaker) into the ScenarioOrchestrator.

Requirements covered:
- RECON-01: Pre-execution validation checks Jira ticket state
- RECON-04: Idempotency checks using execution IDs
- RECON-08: Circuit breaker protection and reconciliation metrics visibility
"""

import pytest
import pytest_asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pybreaker import CircuitBreakerError

# Configure pytest-asyncio
pytestmark = pytest.mark.asyncio(loop_scope="function")

from src.orchestrator.orchestrator import ScenarioOrchestrator
from src.state import SimulationState
from src.state.models import ActiveScenario, TicketComplexity, ScenarioPhase
from src.reconciliation import AdaptationStrategy


@pytest.fixture
def mock_jira():
    """Create a mock JiraClient for testing."""
    jira = Mock()
    jira.get_active_sprint.return_value = {"id": 1, "name": "Sprint 1"}
    jira.is_issue_in_active_sprint.return_value = True
    return jira


@pytest.fixture
def mock_llm():
    """Create a mock LLMService."""
    return Mock()


@pytest.fixture
def personas():
    """Create test personas configuration."""
    return {
        "agents": {
            "dev_alice": {
                "role": "developer",
                "display_name": "Alice",
                "team": "alpha",
                "jira_account_id": "alice-123",
            },
            "qa_bob": {
                "role": "qa",
                "display_name": "Bob",
                "team": "alpha",
                "jira_account_id": "bob-456",
            },
        }
    }


@pytest.fixture
def orchestrator(mock_jira, mock_llm, personas):
    """Create a ScenarioOrchestrator with mocked dependencies."""
    templates = {}
    settings = {"llm": {}}
    orch = ScenarioOrchestrator(mock_jira, mock_llm, personas, templates, settings)
    return orch


class TestPreExecutionValidation:
    """Tests for pre-execution validation (RECON-01)."""

    @pytest.mark.asyncio
    async def test_validation_failure_triggers_skip_when_ahead(self, orchestrator):
        """When ticket status is ahead of expected, action should be skipped."""
        state = SimulationState()
        scenario = ActiveScenario.create_normal_flow(
            "TEST-1", TicketComplexity.STORY, "dev_alice"
        )
        state.add_scenario(scenario)

        action = {
            "type": "pick_up_task",
            "ticket_key": "TEST-1",
            "agent_id": "dev_alice",
        }

        # Mock validator to return status ahead (In Progress instead of To Do)
        with patch.object(orchestrator.validator, "validate_status") as mock_validate:
            mock_validate.return_value = Mock(
                valid=False,
                actual_state={"status": "In Progress"},  # Already picked up
                reason="Status mismatch",
            )
            result = await orchestrator._execute_action(action, state)

        assert result["skipped"] is True
        # Should be skipped because status is ahead
        assert result.get("reason") == "skipped"
        assert "already progressed" in result.get("reconciliation_reason", "").lower()

    @pytest.mark.asyncio
    async def test_validation_failure_triggers_cancel_when_done(self, orchestrator):
        """When ticket is already Done, scenario should be cancelled."""
        state = SimulationState()
        scenario = ActiveScenario.create_normal_flow(
            "TEST-1", TicketComplexity.STORY, "dev_alice"
        )
        state.add_scenario(scenario)

        action = {
            "type": "pick_up_task",
            "ticket_key": "TEST-1",
            "agent_id": "dev_alice",
        }

        # Mock validator to return terminal status (Done)
        with patch.object(orchestrator.validator, "validate_status") as mock_validate:
            mock_validate.return_value = Mock(
                valid=False,
                actual_state={"status": "Done"},  # Already completed
                reason="Status mismatch",
            )
            result = await orchestrator._execute_action(action, state)

        assert result["skipped"] is True
        assert result.get("reason") == "cancelled"
        assert result.get("tombstone") is not None

    @pytest.mark.asyncio
    async def test_validation_success_marks_scenario_validated(self, orchestrator):
        """When validation passes, scenario should be marked as validated."""
        state = SimulationState()
        scenario = ActiveScenario.create_normal_flow(
            "TEST-1", TicketComplexity.STORY, "dev_alice"
        )
        scenario.validation_tick_count = 2  # Simulate some missed validations
        state.add_scenario(scenario)

        action = {
            "type": "pick_up_task",
            "ticket_key": "TEST-1",
            "agent_id": "dev_alice",
        }

        # Mock validation success and lifecycle crew
        with patch.object(orchestrator.validator, "validate_status") as mock_validate:
            mock_validate.return_value = Mock(valid=True)
            with patch.object(
                orchestrator.lifecycle_crew, "pick_up_from_backlog"
            ) as mock_pickup:
                mock_pickup.return_value = {"success": True, "jira_success": True}
                result = await orchestrator._execute_action(action, state)

        # Scenario should be marked validated (tick count reset)
        assert scenario.validation_tick_count == 0


class TestIdempotency:
    """Tests for idempotency checks (RECON-04)."""

    @pytest.mark.asyncio
    async def test_idempotency_prevents_duplicate_execution(self, orchestrator):
        """Same action should not execute twice (idempotency check)."""
        state = SimulationState()

        action = {
            "type": "pick_up_task",
            "ticket_key": "TEST-1",
            "agent_id": "dev_alice",
        }

        # Simulate already-executed action by mocking is_executed
        with patch.object(
            orchestrator.execution_tracker, "is_executed", return_value=True
        ):
            result = await orchestrator._execute_action(action, state)

        assert result["skipped"] is True
        assert result["reason"] == "idempotent_skip"
        assert orchestrator._tick_metrics["idempotent_skips"] == 1

    @pytest.mark.asyncio
    async def test_successful_execution_records_execution_id(self, orchestrator):
        """Successful execution should record execution ID for idempotency."""
        state = SimulationState()

        action = {
            "type": "pick_up_task",
            "ticket_key": "TEST-1",
            "agent_id": "dev_alice",
        }

        # Mock successful validation and execution
        with patch.object(orchestrator.validator, "validate_status") as mock_validate:
            mock_validate.return_value = Mock(valid=True)
            with patch.object(
                orchestrator.lifecycle_crew, "pick_up_from_backlog"
            ) as mock_pickup:
                mock_pickup.return_value = {"success": True, "jira_success": True}
                result = await orchestrator._execute_action(action, state)

        # Result should include execution_id for tracking
        assert "execution_id" in result
        assert result["execution_id"] is not None


class TestCircuitBreaker:
    """Tests for circuit breaker behavior (RECON-08)."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_triggers_reschedule(self, orchestrator):
        """When circuit breaker is open, action should be rescheduled."""
        state = SimulationState()

        action = {
            "type": "pick_up_task",
            "ticket_key": "TEST-1",
            "agent_id": "dev_alice",
        }

        # Mock circuit breaker open
        with patch.object(
            orchestrator.validator,
            "validate_status",
            side_effect=CircuitBreakerError("Circuit open"),
        ):
            result = await orchestrator._execute_action(action, state)

        assert result["skipped"] is True
        assert result["reason"] == "circuit_breaker_open"
        assert orchestrator._tick_metrics["rescheduled"] == 1


class TestReconciliationMetrics:
    """Tests for reconciliation metrics logging (RECON-08)."""

    @pytest.mark.asyncio
    async def test_tick_returns_reconciliation_metrics(self, orchestrator, mock_jira):
        """Tick should return reconciliation metrics in results."""
        state = SimulationState()

        # Mock analyzer and planner to return empty results
        with patch.object(
            orchestrator.analyzer, "analyze", return_value={"opportunities": [], "metrics": {}}
        ):
            with patch.object(orchestrator.planner, "plan_tick", return_value=[]):
                result = await orchestrator.run_tick(state, "light")

        assert "reconciliation_metrics" in result
        assert "validated" in result["reconciliation_metrics"]
        assert "executed" in result["reconciliation_metrics"]
        assert "skipped" in result["reconciliation_metrics"]
        assert "cancelled" in result["reconciliation_metrics"]
        assert "rescheduled" in result["reconciliation_metrics"]
        assert "idempotent_skips" in result["reconciliation_metrics"]

    @pytest.mark.asyncio
    async def test_metrics_reset_each_tick(self, orchestrator, mock_jira):
        """Metrics should reset at the start of each tick."""
        state = SimulationState()

        # Manually set some metrics
        orchestrator._tick_metrics["validated"] = 5
        orchestrator._tick_metrics["executed"] = 3

        # Mock analyzer and planner to return empty results
        with patch.object(
            orchestrator.analyzer, "analyze", return_value={"opportunities": [], "metrics": {}}
        ):
            with patch.object(orchestrator.planner, "plan_tick", return_value=[]):
                result = await orchestrator.run_tick(state, "light")

        # Metrics should be reset (no actions executed this tick)
        assert result["reconciliation_metrics"]["validated"] == 0
        assert result["reconciliation_metrics"]["executed"] == 0


class TestStalenessCleanup:
    """Tests for stale scenario cleanup (RECON-05)."""

    @pytest.mark.asyncio
    async def test_stale_scenarios_removed_at_tick_end(self, orchestrator, mock_jira):
        """Stale scenarios should be cleaned up at end of tick."""
        state = SimulationState()

        # Create a stale scenario (unvalidated for 5+ ticks)
        scenario = ActiveScenario.create_normal_flow(
            "STALE-1", TicketComplexity.STORY, "dev_alice"
        )
        scenario.validation_tick_count = 5  # Exceeds threshold of 4
        state.add_scenario(scenario)

        # Mock analyzer and planner to return empty results
        with patch.object(
            orchestrator.analyzer, "analyze", return_value={"opportunities": [], "metrics": {}}
        ):
            with patch.object(orchestrator.planner, "plan_tick", return_value=[]):
                result = await orchestrator.run_tick(state, "light")

        # Stale scenario should be removed
        assert "stale_scenarios_removed" in result
        assert result["stale_scenarios_removed"] == 1
        assert scenario.scenario_id not in state.active_scenarios

    @pytest.mark.asyncio
    async def test_non_stale_scenarios_preserved(self, orchestrator, mock_jira):
        """Non-stale scenarios should not be removed."""
        state = SimulationState()

        # Create a non-stale scenario (validated recently)
        scenario = ActiveScenario.create_normal_flow(
            "ACTIVE-1", TicketComplexity.STORY, "dev_alice"
        )
        scenario.validation_tick_count = 2  # Below threshold
        state.add_scenario(scenario)

        # Mock analyzer and planner to return empty results
        with patch.object(
            orchestrator.analyzer, "analyze", return_value={"opportunities": [], "metrics": {}}
        ):
            with patch.object(orchestrator.planner, "plan_tick", return_value=[]):
                result = await orchestrator.run_tick(state, "light")

        # Scenario should still exist
        assert scenario.scenario_id in state.active_scenarios


class TestAdaptationStrategies:
    """Tests for adaptation strategy application."""

    @pytest.mark.asyncio
    async def test_skip_strategy_logs_reason(self, orchestrator):
        """SKIP strategy should log reason and continue."""
        state = SimulationState()
        scenario = ActiveScenario.create_normal_flow(
            "TEST-1", TicketComplexity.STORY, "dev_alice"
        )
        state.add_scenario(scenario)

        action = {
            "type": "progress_to_review",
            "ticket_key": "TEST-1",
            "agent_id": "dev_alice",
        }

        # Mock validator to return status ahead (Code Review instead of In Progress)
        with patch.object(orchestrator.validator, "validate_status") as mock_validate:
            mock_validate.return_value = Mock(
                valid=False,
                actual_state={"status": "Code Review"},
                reason="Status mismatch",
            )
            result = await orchestrator._execute_action(action, state)

        assert result["skipped"] is True
        assert result.get("reason") == "skipped"
        assert "reconciliation_reason" in result
        assert orchestrator._tick_metrics["skipped"] == 1

    @pytest.mark.asyncio
    async def test_cancel_strategy_completes_scenario(self, orchestrator):
        """CANCEL strategy should complete scenario with tombstone."""
        state = SimulationState()
        scenario = ActiveScenario.create_normal_flow(
            "TEST-1", TicketComplexity.STORY, "dev_alice"
        )
        state.add_scenario(scenario)
        scenario_id = scenario.scenario_id

        action = {
            "type": "pick_up_task",
            "ticket_key": "TEST-1",
            "agent_id": "dev_alice",
        }

        # Mock validator to return terminal status
        with patch.object(orchestrator.validator, "validate_status") as mock_validate:
            mock_validate.return_value = Mock(
                valid=False,
                actual_state={"status": "Closed"},
                reason="Status mismatch",
            )
            result = await orchestrator._execute_action(action, state)

        assert result["skipped"] is True
        assert result["reason"] == "cancelled"
        # Scenario should be completed/removed
        assert scenario_id not in state.active_scenarios
        assert orchestrator._tick_metrics["cancelled"] == 1

    @pytest.mark.asyncio
    async def test_reschedule_does_not_record_execution(self, orchestrator):
        """RESCHEDULE strategy should not record execution (allows retry)."""
        state = SimulationState()
        initial_count = len(orchestrator.execution_tracker._executed)

        action = {
            "type": "pick_up_task",
            "ticket_key": "TEST-1",
            "agent_id": "dev_alice",
        }

        # Mock circuit breaker open to trigger reschedule
        with patch.object(
            orchestrator.validator,
            "validate_status",
            side_effect=CircuitBreakerError("Circuit open"),
        ):
            result = await orchestrator._execute_action(action, state)

        assert result["reason"] == "circuit_breaker_open"
        # Execution should NOT be recorded (so retry is possible)
        assert len(orchestrator.execution_tracker._executed) == initial_count
