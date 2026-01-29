"""Tests for per-ticket circuit breaker."""

import pytest
import pendulum
from src.reconciliation.circuit_breaker import PerTicketCircuitBreaker, TicketHealth


class TestPerTicketCircuitBreaker:
    """Tests for PerTicketCircuitBreaker retry prevention."""

    def test_new_ticket_is_healthy(self):
        """Unknown tickets are considered healthy."""
        breaker = PerTicketCircuitBreaker()

        assert breaker.is_healthy("ESCRUM-999") is True

    def test_one_failure_stays_healthy(self):
        """Single failure doesn't open circuit."""
        breaker = PerTicketCircuitBreaker(failure_threshold=3)

        circuit_opened = breaker.record_failure("ESCRUM-123", "status mismatch")

        assert circuit_opened is False
        assert breaker.is_healthy("ESCRUM-123") is True

    def test_three_failures_opens_circuit(self):
        """Three consecutive failures opens circuit (PERF-06)."""
        breaker = PerTicketCircuitBreaker(failure_threshold=3)

        breaker.record_failure("ESCRUM-123", "failure 1")
        breaker.record_failure("ESCRUM-123", "failure 2")
        circuit_opened = breaker.record_failure("ESCRUM-123", "failure 3")

        assert circuit_opened is True
        assert breaker.is_healthy("ESCRUM-123") is False

    def test_other_tickets_unaffected(self):
        """Opening circuit for one ticket doesn't affect others."""
        breaker = PerTicketCircuitBreaker(failure_threshold=3)

        # Open circuit for ESCRUM-123
        for _ in range(3):
            breaker.record_failure("ESCRUM-123", "failure")

        # ESCRUM-456 should still be healthy
        assert breaker.is_healthy("ESCRUM-456") is True
        assert breaker.is_healthy("ESCRUM-123") is False

    def test_success_resets_failure_count(self):
        """Successful action resets consecutive failure count."""
        breaker = PerTicketCircuitBreaker(failure_threshold=3)

        breaker.record_failure("ESCRUM-123", "failure 1")
        breaker.record_failure("ESCRUM-123", "failure 2")
        breaker.record_success("ESCRUM-123")

        # Should be back to healthy with 0 failures
        health = breaker.get_ticket_health("ESCRUM-123")
        assert health.consecutive_failures == 0
        assert health.is_healthy is True

    def test_success_reopens_circuit(self):
        """Success after circuit open resets to healthy."""
        breaker = PerTicketCircuitBreaker(failure_threshold=3)

        # Open circuit
        for _ in range(3):
            breaker.record_failure("ESCRUM-123", "failure")
        assert breaker.is_healthy("ESCRUM-123") is False

        # Record success
        breaker.record_success("ESCRUM-123")

        assert breaker.is_healthy("ESCRUM-123") is True

    def test_timeout_resets_circuit(self):
        """Circuit auto-resets after timeout period."""
        breaker = PerTicketCircuitBreaker(
            failure_threshold=3,
            reset_timeout_hours=24.0
        )

        # Open circuit with old timestamp
        for _ in range(3):
            breaker.record_failure("ESCRUM-123", "failure")

        # Simulate time passing by manipulating last_failure_time
        health = breaker._ticket_health["ESCRUM-123"]
        health.last_failure_time = pendulum.now("UTC").subtract(hours=25)

        # Should be healthy again due to timeout
        assert breaker.is_healthy("ESCRUM-123") is True

    def test_get_unhealthy_tickets(self):
        """get_unhealthy_tickets returns list of open circuits."""
        breaker = PerTicketCircuitBreaker(failure_threshold=3)

        # Open circuit for two tickets
        for _ in range(3):
            breaker.record_failure("ESCRUM-111", "failure")
            breaker.record_failure("ESCRUM-222", "failure")

        unhealthy = breaker.get_unhealthy_tickets()

        assert "ESCRUM-111" in unhealthy
        assert "ESCRUM-222" in unhealthy
        assert len(unhealthy) == 2

    def test_manual_reset(self):
        """Manual reset clears ticket's circuit breaker."""
        breaker = PerTicketCircuitBreaker(failure_threshold=3)

        for _ in range(3):
            breaker.record_failure("ESCRUM-123", "failure")

        breaker.reset_ticket("ESCRUM-123")

        assert breaker.is_healthy("ESCRUM-123") is True
        assert breaker.get_ticket_health("ESCRUM-123") is None

    def test_get_stats(self):
        """get_stats returns circuit breaker statistics."""
        breaker = PerTicketCircuitBreaker(failure_threshold=3)

        for _ in range(3):
            breaker.record_failure("ESCRUM-123", "failure")
        breaker.record_failure("ESCRUM-456", "single failure")

        stats = breaker.get_stats()

        assert stats["total_tracked"] == 2
        assert stats["unhealthy_count"] == 1
        assert "ESCRUM-123" in stats["unhealthy_tickets"]

    def test_requirement_perf06_prevents_retry_loop(self):
        """PERF-06: Circuit breaker prevents unbounded retry loops.

        From requirements:
        'When same ticket fails precondition checks 3 times in a row,
        circuit breaker marks it unhealthy and skips future actions'
        """
        breaker = PerTicketCircuitBreaker(failure_threshold=3)

        # Simulate 3 precondition failures
        breaker.record_failure("ESCRUM-123", "precondition: status mismatch")
        breaker.record_failure("ESCRUM-123", "precondition: status mismatch")
        breaker.record_failure("ESCRUM-123", "precondition: status mismatch")

        # Ticket should now be unhealthy
        assert breaker.is_healthy("ESCRUM-123") is False

        # Future action attempts should be skipped (checked via is_healthy)
        # This is how TickExecutor would use it:
        if not breaker.is_healthy("ESCRUM-123"):
            # Skip this action
            skipped = True
        else:
            skipped = False

        assert skipped is True
