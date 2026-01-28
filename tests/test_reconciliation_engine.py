"""Unit tests for ReconciliationEngine and adaptation strategies.

Tests cover:
- Status progression (forward, backward, terminal)
- Sprint membership changes
- Various API failure types
- Tombstone reasons populated correctly
- Edge cases (unknown statuses, None values)
"""
import pytest
from src.reconciliation import (
    ReconciliationEngine,
    ReconciliationResult,
    AdaptationStrategy,
)


class TestAdaptationStrategy:
    """Tests for AdaptationStrategy enum."""

    def test_strategy_values(self):
        """AdaptationStrategy has expected values."""
        assert AdaptationStrategy.CANCEL.value == "cancel"
        assert AdaptationStrategy.RECALCULATE.value == "recalculate"
        assert AdaptationStrategy.RESCHEDULE.value == "reschedule"
        assert AdaptationStrategy.PROCEED.value == "proceed"
        assert AdaptationStrategy.SKIP.value == "skip"

    def test_strategy_is_string_enum(self):
        """AdaptationStrategy values are strings for JSON serialization."""
        assert isinstance(AdaptationStrategy.CANCEL.value, str)
        assert str(AdaptationStrategy.CANCEL) == "AdaptationStrategy.CANCEL"


class TestReconciliationResult:
    """Tests for ReconciliationResult dataclass."""

    def test_result_with_strategy_and_reason(self):
        """ReconciliationResult requires strategy and reason."""
        result = ReconciliationResult(
            strategy=AdaptationStrategy.CANCEL,
            reason="Ticket completed externally"
        )
        assert result.strategy == AdaptationStrategy.CANCEL
        assert result.reason == "Ticket completed externally"
        assert result.tombstone_reason is None
        assert result.new_plan is None

    def test_result_with_tombstone_reason(self):
        """ReconciliationResult can include tombstone_reason."""
        result = ReconciliationResult(
            strategy=AdaptationStrategy.CANCEL,
            reason="Ticket moved to Done",
            tombstone_reason="User completed ticket manually (Done)"
        )
        assert result.tombstone_reason == "User completed ticket manually (Done)"

    def test_result_with_new_plan(self):
        """ReconciliationResult can include new_plan for recalculation."""
        new_plan = [{"action": "transition", "to": "Code Review"}]
        result = ReconciliationResult(
            strategy=AdaptationStrategy.RECALCULATE,
            reason="Ticket regressed, recalculating",
            new_plan=new_plan
        )
        assert result.new_plan == new_plan


class TestReconcileStatusMismatch:
    """Tests for ReconciliationEngine.reconcile_status_mismatch()."""

    @pytest.fixture
    def engine(self):
        """Create ReconciliationEngine instance."""
        return ReconciliationEngine()

    # Terminal status tests (CANCEL with tombstone)

    def test_terminal_status_done_cancels_with_tombstone(self, engine):
        """Moving to 'Done' triggers CANCEL with tombstone."""
        result = engine.reconcile_status_mismatch(
            ticket_key="ESCRUM-123",
            expected_status="In Progress",
            actual_status="Done",
            action_type="transition"
        )
        assert result.strategy == AdaptationStrategy.CANCEL
        assert "Done" in result.reason
        assert result.tombstone_reason is not None
        assert "manually" in result.tombstone_reason.lower() or "Done" in result.tombstone_reason

    def test_terminal_status_closed_cancels_with_tombstone(self, engine):
        """Moving to 'Closed' triggers CANCEL with tombstone."""
        result = engine.reconcile_status_mismatch(
            ticket_key="ESCRUM-123",
            expected_status="In Progress",
            actual_status="Closed",
            action_type="transition"
        )
        assert result.strategy == AdaptationStrategy.CANCEL
        assert result.tombstone_reason is not None
        assert "Closed" in result.tombstone_reason or "manually" in result.tombstone_reason.lower()

    def test_terminal_status_resolved_cancels_with_tombstone(self, engine):
        """Moving to 'Resolved' triggers CANCEL with tombstone."""
        result = engine.reconcile_status_mismatch(
            ticket_key="ESCRUM-123",
            expected_status="Code Review",
            actual_status="Resolved",
            action_type="transition"
        )
        assert result.strategy == AdaptationStrategy.CANCEL
        assert result.tombstone_reason is not None

    # Forward progression tests (SKIP)

    def test_progressed_ahead_skips(self, engine):
        """Ticket progressed ahead triggers SKIP."""
        result = engine.reconcile_status_mismatch(
            ticket_key="ESCRUM-123",
            expected_status="In Progress",
            actual_status="Code Review",
            action_type="transition"
        )
        assert result.strategy == AdaptationStrategy.SKIP
        assert "Code Review" in result.reason
        assert "progressed" in result.reason.lower() or "already" in result.reason.lower()

    def test_todo_to_in_progress_externally_skips(self, engine):
        """'To Do' -> 'In Progress' externally triggers SKIP."""
        result = engine.reconcile_status_mismatch(
            ticket_key="ESCRUM-123",
            expected_status="To Do",
            actual_status="In Progress",
            action_type="transition"
        )
        assert result.strategy == AdaptationStrategy.SKIP

    def test_in_progress_to_ready_for_qa_skips(self, engine):
        """'In Progress' -> 'Ready for QA' externally triggers SKIP."""
        result = engine.reconcile_status_mismatch(
            ticket_key="ESCRUM-123",
            expected_status="In Progress",
            actual_status="Ready for QA",
            action_type="transition"
        )
        assert result.strategy == AdaptationStrategy.SKIP

    # Backward regression tests (RECALCULATE)

    def test_regressed_backward_recalculates(self, engine):
        """Ticket regressed backward triggers RECALCULATE."""
        result = engine.reconcile_status_mismatch(
            ticket_key="ESCRUM-123",
            expected_status="Code Review",
            actual_status="In Progress",
            action_type="transition"
        )
        assert result.strategy == AdaptationStrategy.RECALCULATE
        assert "regressed" in result.reason.lower() or "In Progress" in result.reason

    def test_ready_for_qa_to_in_progress_recalculates(self, engine):
        """'Ready for QA' -> 'In Progress' triggers RECALCULATE."""
        result = engine.reconcile_status_mismatch(
            ticket_key="ESCRUM-123",
            expected_status="Ready for QA",
            actual_status="In Progress",
            action_type="transition"
        )
        assert result.strategy == AdaptationStrategy.RECALCULATE

    def test_testing_to_code_review_recalculates(self, engine):
        """'Testing' -> 'Code Review' triggers RECALCULATE."""
        result = engine.reconcile_status_mismatch(
            ticket_key="ESCRUM-123",
            expected_status="Testing",
            actual_status="Code Review",
            action_type="transition"
        )
        assert result.strategy == AdaptationStrategy.RECALCULATE

    # Unknown status tests (PROCEED)

    def test_unknown_expected_status_proceeds(self, engine):
        """Unknown expected status triggers PROCEED."""
        result = engine.reconcile_status_mismatch(
            ticket_key="ESCRUM-123",
            expected_status="Custom Status XYZ",
            actual_status="In Progress",
            action_type="transition"
        )
        assert result.strategy == AdaptationStrategy.PROCEED

    def test_unknown_actual_status_proceeds(self, engine):
        """Unknown actual status triggers PROCEED."""
        result = engine.reconcile_status_mismatch(
            ticket_key="ESCRUM-123",
            expected_status="In Progress",
            actual_status="Custom Status ABC",
            action_type="transition"
        )
        assert result.strategy == AdaptationStrategy.PROCEED

    def test_both_unknown_statuses_proceeds(self, engine):
        """Both unknown statuses trigger PROCEED."""
        result = engine.reconcile_status_mismatch(
            ticket_key="ESCRUM-123",
            expected_status="Custom A",
            actual_status="Custom B",
            action_type="transition"
        )
        assert result.strategy == AdaptationStrategy.PROCEED

    # Alternative status names (same rank)

    def test_in_review_equals_code_review(self, engine):
        """'In Review' and 'Code Review' are same rank."""
        # Same rank means no progression or regression
        result = engine.reconcile_status_mismatch(
            ticket_key="ESCRUM-123",
            expected_status="Code Review",
            actual_status="In Review",
            action_type="transition"
        )
        # Same rank should not be CANCEL/SKIP/RECALCULATE
        assert result.strategy in [AdaptationStrategy.PROCEED, AdaptationStrategy.SKIP]

    def test_testing_equals_ready_for_qa(self, engine):
        """'Testing' and 'Ready for QA' are same rank."""
        result = engine.reconcile_status_mismatch(
            ticket_key="ESCRUM-123",
            expected_status="Ready for QA",
            actual_status="Testing",
            action_type="transition"
        )
        assert result.strategy in [AdaptationStrategy.PROCEED, AdaptationStrategy.SKIP]


class TestReconcileSprintMismatch:
    """Tests for ReconciliationEngine.reconcile_sprint_mismatch()."""

    @pytest.fixture
    def engine(self):
        """Create ReconciliationEngine instance."""
        return ReconciliationEngine()

    def test_removed_from_sprint_cancels_with_tombstone(self, engine):
        """Expected in sprint but not in sprint triggers CANCEL with tombstone."""
        result = engine.reconcile_sprint_mismatch(
            ticket_key="ESCRUM-123",
            expected_in_sprint=True,
            actual_in_sprint=False
        )
        assert result.strategy == AdaptationStrategy.CANCEL
        assert result.tombstone_reason is not None
        assert "sprint" in result.tombstone_reason.lower() or "removed" in result.tombstone_reason.lower()

    def test_added_to_sprint_proceeds(self, engine):
        """Not expected in sprint but in sprint triggers PROCEED."""
        result = engine.reconcile_sprint_mismatch(
            ticket_key="ESCRUM-123",
            expected_in_sprint=False,
            actual_in_sprint=True
        )
        assert result.strategy == AdaptationStrategy.PROCEED
        assert "added" in result.reason.lower() or "sprint" in result.reason.lower()

    def test_expected_and_actual_both_true_proceeds(self, engine):
        """Both expected and actual in sprint matches - PROCEED."""
        result = engine.reconcile_sprint_mismatch(
            ticket_key="ESCRUM-123",
            expected_in_sprint=True,
            actual_in_sprint=True
        )
        assert result.strategy == AdaptationStrategy.PROCEED

    def test_expected_and_actual_both_false_proceeds(self, engine):
        """Both expected and actual not in sprint matches - PROCEED."""
        result = engine.reconcile_sprint_mismatch(
            ticket_key="ESCRUM-123",
            expected_in_sprint=False,
            actual_in_sprint=False
        )
        assert result.strategy == AdaptationStrategy.PROCEED


class TestReconcileApiFailure:
    """Tests for ReconciliationEngine.reconcile_api_failure()."""

    @pytest.fixture
    def engine(self):
        """Create ReconciliationEngine instance."""
        return ReconciliationEngine()

    # Transient errors (RESCHEDULE when retry_count < 3)

    def test_timeout_error_reschedules(self, engine):
        """Timeout error triggers RESCHEDULE."""
        result = engine.reconcile_api_failure(
            error="Connection timeout after 30s",
            retry_count=0
        )
        assert result.strategy == AdaptationStrategy.RESCHEDULE
        assert "retry" in result.reason.lower() or "transient" in result.reason.lower()

    def test_503_error_reschedules(self, engine):
        """503 Service Unavailable triggers RESCHEDULE."""
        result = engine.reconcile_api_failure(
            error="HTTP 503 Service Unavailable",
            retry_count=1
        )
        assert result.strategy == AdaptationStrategy.RESCHEDULE

    def test_429_rate_limit_reschedules(self, engine):
        """429 Rate Limit triggers RESCHEDULE."""
        result = engine.reconcile_api_failure(
            error="HTTP 429 Too Many Requests",
            retry_count=2
        )
        assert result.strategy == AdaptationStrategy.RESCHEDULE

    def test_connection_error_reschedules(self, engine):
        """Connection error triggers RESCHEDULE."""
        result = engine.reconcile_api_failure(
            error="ConnectionError: Failed to establish connection",
            retry_count=0
        )
        assert result.strategy == AdaptationStrategy.RESCHEDULE

    def test_transient_error_exceeds_retry_limit_skips(self, engine):
        """Transient error with retry_count >= 3 triggers SKIP (not RESCHEDULE)."""
        result = engine.reconcile_api_failure(
            error="Connection timeout after 30s",
            retry_count=3
        )
        # After 3 retries, should not continue rescheduling
        assert result.strategy != AdaptationStrategy.RESCHEDULE

    # 404 errors (CANCEL with tombstone)

    def test_404_error_cancels_with_tombstone(self, engine):
        """404 Not Found triggers CANCEL with tombstone."""
        result = engine.reconcile_api_failure(
            error="HTTP 404 Not Found",
            retry_count=0
        )
        assert result.strategy == AdaptationStrategy.CANCEL
        assert result.tombstone_reason is not None
        assert "deleted" in result.tombstone_reason.lower() or "not found" in result.tombstone_reason.lower()

    def test_not_found_error_cancels_with_tombstone(self, engine):
        """'not found' text triggers CANCEL with tombstone."""
        result = engine.reconcile_api_failure(
            error="Issue not found: ESCRUM-999",
            retry_count=0
        )
        assert result.strategy == AdaptationStrategy.CANCEL
        assert result.tombstone_reason is not None

    # Other errors (SKIP)

    def test_400_bad_request_skips(self, engine):
        """400 Bad Request triggers SKIP."""
        result = engine.reconcile_api_failure(
            error="HTTP 400 Bad Request: Invalid transition",
            retry_count=0
        )
        assert result.strategy == AdaptationStrategy.SKIP
        assert "error" in result.reason.lower() or "skip" in result.reason.lower()

    def test_401_unauthorized_skips(self, engine):
        """401 Unauthorized triggers SKIP."""
        result = engine.reconcile_api_failure(
            error="HTTP 401 Unauthorized",
            retry_count=0
        )
        assert result.strategy == AdaptationStrategy.SKIP

    def test_500_internal_server_error_skips(self, engine):
        """500 Internal Server Error (non-503) triggers SKIP."""
        result = engine.reconcile_api_failure(
            error="HTTP 500 Internal Server Error",
            retry_count=0
        )
        assert result.strategy == AdaptationStrategy.SKIP

    def test_unknown_exception_skips(self, engine):
        """Unknown exception triggers SKIP."""
        result = engine.reconcile_api_failure(
            error="SomeRandomException: Unknown error occurred",
            retry_count=0
        )
        assert result.strategy == AdaptationStrategy.SKIP

    # String and Exception input handling

    def test_handles_exception_object(self, engine):
        """Can handle Exception objects, not just strings."""
        exception = Exception("Connection refused")
        result = engine.reconcile_api_failure(
            error=exception,
            retry_count=0
        )
        # Should handle gracefully without crashing
        assert result.strategy in [
            AdaptationStrategy.RESCHEDULE,
            AdaptationStrategy.CANCEL,
            AdaptationStrategy.SKIP
        ]


class TestTombstoneReasonPopulation:
    """Tests ensuring tombstone_reason is always populated for CANCEL decisions."""

    @pytest.fixture
    def engine(self):
        """Create ReconciliationEngine instance."""
        return ReconciliationEngine()

    def test_terminal_status_has_tombstone(self, engine):
        """Terminal status CANCEL has tombstone_reason."""
        result = engine.reconcile_status_mismatch(
            ticket_key="ESCRUM-123",
            expected_status="In Progress",
            actual_status="Done",
            action_type="transition"
        )
        assert result.strategy == AdaptationStrategy.CANCEL
        assert result.tombstone_reason is not None
        assert len(result.tombstone_reason) > 0

    def test_sprint_removal_has_tombstone(self, engine):
        """Sprint removal CANCEL has tombstone_reason."""
        result = engine.reconcile_sprint_mismatch(
            ticket_key="ESCRUM-123",
            expected_in_sprint=True,
            actual_in_sprint=False
        )
        assert result.strategy == AdaptationStrategy.CANCEL
        assert result.tombstone_reason is not None
        assert len(result.tombstone_reason) > 0

    def test_404_error_has_tombstone(self, engine):
        """404 error CANCEL has tombstone_reason."""
        result = engine.reconcile_api_failure(
            error="HTTP 404 Not Found",
            retry_count=0
        )
        assert result.strategy == AdaptationStrategy.CANCEL
        assert result.tombstone_reason is not None
        assert len(result.tombstone_reason) > 0

    def test_non_cancel_strategies_have_no_tombstone(self, engine):
        """Non-CANCEL strategies should not have tombstone_reason."""
        # SKIP case
        skip_result = engine.reconcile_status_mismatch(
            ticket_key="ESCRUM-123",
            expected_status="In Progress",
            actual_status="Code Review",
            action_type="transition"
        )
        assert skip_result.strategy == AdaptationStrategy.SKIP
        assert skip_result.tombstone_reason is None

        # RECALCULATE case
        recalc_result = engine.reconcile_status_mismatch(
            ticket_key="ESCRUM-123",
            expected_status="Code Review",
            actual_status="In Progress",
            action_type="transition"
        )
        assert recalc_result.strategy == AdaptationStrategy.RECALCULATE
        assert recalc_result.tombstone_reason is None

        # PROCEED case
        proceed_result = engine.reconcile_sprint_mismatch(
            ticket_key="ESCRUM-123",
            expected_in_sprint=False,
            actual_in_sprint=True
        )
        assert proceed_result.strategy == AdaptationStrategy.PROCEED
        assert proceed_result.tombstone_reason is None


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.fixture
    def engine(self):
        """Create ReconciliationEngine instance."""
        return ReconciliationEngine()

    def test_empty_error_string(self, engine):
        """Empty error string is handled gracefully."""
        result = engine.reconcile_api_failure(error="", retry_count=0)
        assert result.strategy == AdaptationStrategy.SKIP

    def test_none_error_handled(self, engine):
        """None error is handled gracefully."""
        # This should not crash
        try:
            result = engine.reconcile_api_failure(error=None, retry_count=0)
            assert result.strategy == AdaptationStrategy.SKIP
        except (TypeError, AttributeError):
            pytest.fail("reconcile_api_failure should handle None error gracefully")

    def test_negative_retry_count(self, engine):
        """Negative retry_count is handled (treated as 0)."""
        result = engine.reconcile_api_failure(
            error="Connection timeout",
            retry_count=-1
        )
        # Should still work, treating negative as < 3
        assert result.strategy == AdaptationStrategy.RESCHEDULE

    def test_large_retry_count(self, engine):
        """Large retry_count doesn't cause issues."""
        result = engine.reconcile_api_failure(
            error="Connection timeout",
            retry_count=1000
        )
        # Should not reschedule after many retries
        assert result.strategy != AdaptationStrategy.RESCHEDULE

    def test_case_insensitive_error_matching(self, engine):
        """Error matching should be case-insensitive."""
        # Uppercase
        result1 = engine.reconcile_api_failure(error="TIMEOUT", retry_count=0)
        assert result1.strategy == AdaptationStrategy.RESCHEDULE

        # Mixed case
        result2 = engine.reconcile_api_failure(error="TimeOut occurred", retry_count=0)
        assert result2.strategy == AdaptationStrategy.RESCHEDULE

        # Lowercase
        result3 = engine.reconcile_api_failure(error="connection reset", retry_count=0)
        assert result3.strategy == AdaptationStrategy.RESCHEDULE
