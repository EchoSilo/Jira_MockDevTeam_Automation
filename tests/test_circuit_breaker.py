"""Tests for circuit breaker behavior.

Tests cover:
1. Circuit opens after fail_max consecutive failures
2. CircuitBreakerError raised when circuit is open
3. Circuit enters half-open state after timeout
4. Success in half-open state closes the circuit
5. Read and write breakers are independent

Note: pybreaker's default behavior (throw_new_error_on_trip=True) means the
call that trips the circuit raises CircuitBreakerError, not the original error.
"""

import time
from unittest.mock import Mock

import pytest
from pybreaker import CircuitBreakerError

from src.reconciliation.circuit_breaker import (
    ResilientJiraClient,
    jira_read_breaker,
    jira_write_breaker,
)


@pytest.fixture(autouse=True)
def reset_breakers():
    """Reset both circuit breakers before each test.

    This prevents test pollution from previous test failures
    affecting subsequent tests.
    """
    jira_read_breaker.close()
    jira_write_breaker.close()
    yield
    # Also reset after test
    jira_read_breaker.close()
    jira_write_breaker.close()


class TestCircuitBreakerOpensAfterFailures:
    """Test that circuit opens after fail_max consecutive failures."""

    def test_read_breaker_opens_after_5_failures(self):
        """Read circuit opens after 5 consecutive failures.

        pybreaker's throw_new_error_on_trip=True means the 5th call
        (which trips the breaker) raises CircuitBreakerError.
        """
        mock_client = Mock()
        mock_client.get_issue.side_effect = Exception("Connection refused")
        resilient = ResilientJiraClient(mock_client)

        # First 4 failures raise the original exception
        for _ in range(4):
            with pytest.raises(Exception, match="Connection refused"):
                resilient.get_issue("TEST-1")

        # 5th call trips the circuit - raises CircuitBreakerError
        with pytest.raises(CircuitBreakerError):
            resilient.get_issue("TEST-1")

        # Circuit is now open
        assert jira_read_breaker.current_state == "open"

        # 6th call should also raise CircuitBreakerError (circuit is open)
        with pytest.raises(CircuitBreakerError):
            resilient.get_issue("TEST-1")

    def test_write_breaker_opens_after_3_failures(self):
        """Write circuit opens after 3 consecutive failures."""
        mock_client = Mock()
        mock_client.transition_issue.side_effect = Exception("Server error")
        resilient = ResilientJiraClient(mock_client)

        # First 2 failures raise the original exception
        for _ in range(2):
            with pytest.raises(Exception, match="Server error"):
                resilient.transition_issue("TEST-1", "In Progress")

        # 3rd call trips the circuit - raises CircuitBreakerError
        with pytest.raises(CircuitBreakerError):
            resilient.transition_issue("TEST-1", "In Progress")

        # Circuit is now open
        assert jira_write_breaker.current_state == "open"

        # 4th call should also raise CircuitBreakerError (circuit is open)
        with pytest.raises(CircuitBreakerError):
            resilient.transition_issue("TEST-1", "In Progress")


class TestCircuitBreakerErrorRaised:
    """Test that CircuitBreakerError is raised when circuit is open."""

    def test_circuit_breaker_error_is_distinguishable(self):
        """CircuitBreakerError can be caught separately from other errors."""
        mock_client = Mock()
        mock_client.get_issue.side_effect = ValueError("Test error")
        resilient = ResilientJiraClient(mock_client)

        # Trip the circuit with failures (first 4 raise ValueError)
        for _ in range(4):
            with pytest.raises(ValueError):
                resilient.get_issue("TEST-1")

        # 5th call trips circuit - should raise CircuitBreakerError, not ValueError
        try:
            resilient.get_issue("TEST-1")
            pytest.fail("Expected CircuitBreakerError")
        except CircuitBreakerError:
            pass  # Expected - circuit was tripped
        except ValueError:
            pytest.fail("Got ValueError instead of CircuitBreakerError")

    def test_circuit_breaker_error_not_raised_when_closed(self):
        """Normal errors pass through when circuit is closed."""
        mock_client = Mock()
        mock_client.get_issue.side_effect = ValueError("Test error")
        resilient = ResilientJiraClient(mock_client)

        # First failure should raise ValueError, not CircuitBreakerError
        with pytest.raises(ValueError, match="Test error"):
            resilient.get_issue("TEST-1")


class TestCircuitBreakerHalfOpenState:
    """Test half-open state behavior."""

    def test_circuit_enters_half_open_after_timeout(self):
        """Circuit enters half-open state after reset_timeout expires."""
        # Use a shorter timeout for testing
        original_timeout = jira_read_breaker._reset_timeout
        jira_read_breaker._reset_timeout = 0.1  # 100ms for test

        try:
            mock_client = Mock()
            mock_client.get_issue.side_effect = Exception("Connection refused")
            resilient = ResilientJiraClient(mock_client)

            # Trip the circuit
            for _ in range(5):
                try:
                    resilient.get_issue("TEST-1")
                except Exception:
                    pass

            # Verify circuit is open
            assert jira_read_breaker.current_state == "open"

            # Wait for timeout
            time.sleep(0.15)

            # Circuit should now be half-open
            # (pybreaker transitions to half-open on next call attempt)
            mock_client.get_issue.side_effect = None
            mock_client.get_issue.return_value = {"key": "TEST-1"}

            # This call should succeed and close the circuit
            result = resilient.get_issue("TEST-1")
            assert result == {"key": "TEST-1"}
            assert jira_read_breaker.current_state == "closed"

        finally:
            jira_read_breaker._reset_timeout = original_timeout

    def test_failure_in_half_open_reopens_circuit(self):
        """Failure in half-open state reopens the circuit."""
        original_timeout = jira_read_breaker._reset_timeout
        jira_read_breaker._reset_timeout = 0.1  # 100ms for test

        try:
            mock_client = Mock()
            mock_client.get_issue.side_effect = Exception("Connection refused")
            resilient = ResilientJiraClient(mock_client)

            # Trip the circuit
            for _ in range(5):
                try:
                    resilient.get_issue("TEST-1")
                except Exception:
                    pass

            # Wait for timeout
            time.sleep(0.15)

            # Try again with failure - should reopen circuit
            # In half-open state, a failure raises CircuitBreakerError
            with pytest.raises(CircuitBreakerError):
                resilient.get_issue("TEST-1")

            # Circuit should be open again
            assert jira_read_breaker.current_state == "open"

        finally:
            jira_read_breaker._reset_timeout = original_timeout


class TestCircuitBreakerSuccessCloses:
    """Test that success in half-open state closes the circuit."""

    def test_success_in_half_open_closes_circuit(self):
        """Successful call in half-open state closes the circuit."""
        original_timeout = jira_read_breaker._reset_timeout
        jira_read_breaker._reset_timeout = 0.1  # 100ms for test

        try:
            mock_client = Mock()
            resilient = ResilientJiraClient(mock_client)

            # Trip the circuit with failures
            mock_client.get_issue.side_effect = Exception("Connection refused")
            for _ in range(5):
                try:
                    resilient.get_issue("TEST-1")
                except Exception:
                    pass

            assert jira_read_breaker.current_state == "open"

            # Wait for timeout
            time.sleep(0.15)

            # Now succeed
            mock_client.get_issue.side_effect = None
            mock_client.get_issue.return_value = {"key": "TEST-1"}

            result = resilient.get_issue("TEST-1")
            assert result == {"key": "TEST-1"}

            # Circuit should be closed
            assert jira_read_breaker.current_state == "closed"

        finally:
            jira_read_breaker._reset_timeout = original_timeout


class TestReadWriteBreakersIndependent:
    """Test that read and write breakers operate independently."""

    def test_read_failures_do_not_affect_write_breaker(self):
        """Read breaker failures don't open write breaker."""
        mock_client = Mock()
        mock_client.get_issue.side_effect = Exception("Read failed")
        mock_client.add_comment.return_value = None
        resilient = ResilientJiraClient(mock_client)

        # Trip the read breaker
        for _ in range(5):
            try:
                resilient.get_issue("TEST-1")
            except Exception:
                pass

        # Read breaker should be open
        assert jira_read_breaker.current_state == "open"

        # Write breaker should still be closed
        assert jira_write_breaker.current_state == "closed"

        # Write operations should still work
        resilient.add_comment("TEST-1", "Comment")
        mock_client.add_comment.assert_called_once_with("TEST-1", "Comment")

    def test_write_failures_do_not_affect_read_breaker(self):
        """Write breaker failures don't open read breaker."""
        mock_client = Mock()
        mock_client.transition_issue.side_effect = Exception("Write failed")
        mock_client.get_issue.return_value = {"key": "TEST-1"}
        resilient = ResilientJiraClient(mock_client)

        # Trip the write breaker
        for _ in range(3):
            try:
                resilient.transition_issue("TEST-1", "Done")
            except Exception:
                pass

        # Write breaker should be open
        assert jira_write_breaker.current_state == "open"

        # Read breaker should still be closed
        assert jira_read_breaker.current_state == "closed"

        # Read operations should still work
        result = resilient.get_issue("TEST-1")
        assert result == {"key": "TEST-1"}


class TestResilientJiraClientWrapper:
    """Test the wrapper functionality."""

    def test_wrapper_passes_through_successful_calls(self):
        """Successful calls pass through unchanged."""
        mock_client = Mock()
        mock_client.get_issue.return_value = {"key": "TEST-1", "status": "To Do"}
        resilient = ResilientJiraClient(mock_client)

        result = resilient.get_issue("TEST-1")

        assert result == {"key": "TEST-1", "status": "To Do"}
        mock_client.get_issue.assert_called_once_with("TEST-1")

    def test_wrapper_passes_through_non_wrapped_methods(self):
        """Non-wrapped methods are accessible via __getattr__."""
        mock_client = Mock()
        mock_client.get_epic_children.return_value = ["CHILD-1", "CHILD-2"]
        resilient = ResilientJiraClient(mock_client)

        result = resilient.get_epic_children("EPIC-1")

        assert result == ["CHILD-1", "CHILD-2"]
        mock_client.get_epic_children.assert_called_once_with("EPIC-1")

    def test_get_breaker_state_returns_both_states(self):
        """get_breaker_state() returns state of both breakers."""
        mock_client = Mock()
        resilient = ResilientJiraClient(mock_client)

        state = resilient.get_breaker_state()

        assert "reads" in state
        assert "writes" in state
        assert state["reads"] == "closed"
        assert state["writes"] == "closed"

    def test_get_breaker_state_reflects_open_circuit(self):
        """get_breaker_state() reflects when circuit is open."""
        mock_client = Mock()
        mock_client.get_issue.side_effect = Exception("Failed")
        resilient = ResilientJiraClient(mock_client)

        # Trip the read breaker
        for _ in range(5):
            try:
                resilient.get_issue("TEST-1")
            except Exception:
                pass

        state = resilient.get_breaker_state()

        assert state["reads"] == "open"
        assert state["writes"] == "closed"


class TestCircuitBreakerWithDifferentExceptions:
    """Test circuit breaker behavior with various exception types."""

    def test_any_exception_counts_as_failure(self):
        """Any exception type counts toward failure threshold."""
        mock_client = Mock()
        exceptions = [
            ValueError("Bad value"),
            ConnectionError("Network error"),
            TimeoutError("Timeout"),
            RuntimeError("Runtime error"),
            Exception("Generic error"),
        ]
        mock_client.get_issue.side_effect = exceptions
        resilient = ResilientJiraClient(mock_client)

        # All 5 different exceptions should trip the breaker
        for exc in exceptions:
            try:
                resilient.get_issue("TEST-1")
            except Exception:
                pass

        # Circuit should now be open
        with pytest.raises(CircuitBreakerError):
            resilient.get_issue("TEST-1")

    def test_success_resets_failure_count(self):
        """Successful calls reset the failure count."""
        mock_client = Mock()
        resilient = ResilientJiraClient(mock_client)

        # 4 failures (not enough to open)
        mock_client.get_issue.side_effect = Exception("Failed")
        for _ in range(4):
            try:
                resilient.get_issue("TEST-1")
            except Exception:
                pass

        # 1 success
        mock_client.get_issue.side_effect = None
        mock_client.get_issue.return_value = {"key": "TEST-1"}
        resilient.get_issue("TEST-1")

        # 4 more failures (still not enough because count was reset)
        mock_client.get_issue.side_effect = Exception("Failed again")
        for _ in range(4):
            try:
                resilient.get_issue("TEST-1")
            except Exception:
                pass

        # Circuit should still be closed (not 5 consecutive)
        assert jira_read_breaker.current_state == "closed"
