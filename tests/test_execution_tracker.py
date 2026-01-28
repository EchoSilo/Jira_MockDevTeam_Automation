"""Tests for ExecutionTracker - idempotency tracking for action execution.

Tests cover:
- Execution ID generation with deterministic prefix and unique suffix
- is_executed() returns False for new IDs
- is_executed() returns True after recording
- Automatic cleanup of old records
- Multiple executions with same parameters tracked separately
"""
import pytest
import pendulum

from src.time import FakeClock
from src.reconciliation import ExecutionTracker, ExecutionRecord


class TestExecutionIdGeneration:
    """Tests for generate_execution_id() method."""

    def test_generates_unique_ids_for_same_parameters(self):
        """Each call generates a unique ID even with identical parameters."""
        tracker = ExecutionTracker()

        id1 = tracker.generate_execution_id("transition", "ESCRUM-123", "dev_alice")
        id2 = tracker.generate_execution_id("transition", "ESCRUM-123", "dev_alice")

        assert id1 != id2

    def test_id_format_contains_all_components(self):
        """Execution ID format is {action}:{ticket}:{agent}:{uuid8}."""
        tracker = ExecutionTracker()

        exec_id = tracker.generate_execution_id("transition_to_in_progress", "ESCRUM-123", "dev_alice")

        parts = exec_id.split(":")
        assert len(parts) == 4
        assert parts[0] == "transition_to_in_progress"
        assert parts[1] == "ESCRUM-123"
        assert parts[2] == "dev_alice"
        assert len(parts[3]) == 8  # UUID prefix

    def test_deterministic_prefix_for_same_parameters(self):
        """Same parameters produce the same prefix (first 3 parts)."""
        tracker = ExecutionTracker()

        id1 = tracker.generate_execution_id("add_comment", "ESCRUM-456", "qa_bob")
        id2 = tracker.generate_execution_id("add_comment", "ESCRUM-456", "qa_bob")

        prefix1 = ":".join(id1.split(":")[:3])
        prefix2 = ":".join(id2.split(":")[:3])

        assert prefix1 == prefix2
        assert prefix1 == "add_comment:ESCRUM-456:qa_bob"


class TestIsExecuted:
    """Tests for is_executed() method."""

    def test_returns_false_for_new_id(self):
        """New execution ID has not been executed."""
        tracker = ExecutionTracker()

        exec_id = tracker.generate_execution_id("transition", "ESCRUM-123", "dev_alice")

        assert tracker.is_executed(exec_id) is False

    def test_returns_true_after_recording(self):
        """After recording, execution ID is marked as executed."""
        clock = FakeClock(pendulum.datetime(2026, 1, 28, 10, 0, tz="UTC"))
        tracker = ExecutionTracker(clock=clock)

        exec_id = tracker.generate_execution_id("transition", "ESCRUM-123", "dev_alice")
        tracker.record_execution(exec_id, "transition", "ESCRUM-123", "success")

        assert tracker.is_executed(exec_id) is True

    def test_different_ids_tracked_independently(self):
        """Multiple execution IDs are tracked independently."""
        clock = FakeClock(pendulum.datetime(2026, 1, 28, 10, 0, tz="UTC"))
        tracker = ExecutionTracker(clock=clock)

        id1 = tracker.generate_execution_id("transition", "ESCRUM-123", "dev_alice")
        id2 = tracker.generate_execution_id("transition", "ESCRUM-123", "dev_alice")

        tracker.record_execution(id1, "transition", "ESCRUM-123", "success")

        assert tracker.is_executed(id1) is True
        assert tracker.is_executed(id2) is False


class TestRecordExecution:
    """Tests for record_execution() method."""

    def test_records_execution_with_all_fields(self):
        """Recording stores all execution details."""
        clock = FakeClock(pendulum.datetime(2026, 1, 28, 10, 0, tz="UTC"))
        tracker = ExecutionTracker(clock=clock)

        exec_id = tracker.generate_execution_id("transition", "ESCRUM-123", "dev_alice")
        tracker.record_execution(exec_id, "transition", "ESCRUM-123", "success")

        record = tracker.get_record(exec_id)

        assert record is not None
        assert record.execution_id == exec_id
        assert record.action_type == "transition"
        assert record.ticket_key == "ESCRUM-123"
        assert record.result == "success"
        assert record.executed_at == clock.now()

    def test_records_failure_result(self):
        """Can record failed executions."""
        clock = FakeClock(pendulum.datetime(2026, 1, 28, 10, 0, tz="UTC"))
        tracker = ExecutionTracker(clock=clock)

        exec_id = tracker.generate_execution_id("transition", "ESCRUM-123", "dev_alice")
        tracker.record_execution(exec_id, "transition", "ESCRUM-123", "failure")

        record = tracker.get_record(exec_id)
        assert record.result == "failure"

    def test_records_skipped_result(self):
        """Can record skipped executions."""
        clock = FakeClock(pendulum.datetime(2026, 1, 28, 10, 0, tz="UTC"))
        tracker = ExecutionTracker(clock=clock)

        exec_id = tracker.generate_execution_id("transition", "ESCRUM-123", "dev_alice")
        tracker.record_execution(exec_id, "transition", "ESCRUM-123", "skipped")

        record = tracker.get_record(exec_id)
        assert record.result == "skipped"


class TestAutomaticCleanup:
    """Tests for automatic cleanup of old records."""

    def test_cleanup_removes_old_records(self):
        """Records older than cleanup_age_hours are removed."""
        clock = FakeClock(pendulum.datetime(2026, 1, 28, 10, 0, tz="UTC"))
        tracker = ExecutionTracker(clock=clock, cleanup_age_hours=48)

        # Record an execution
        old_id = tracker.generate_execution_id("transition", "ESCRUM-123", "dev_alice")
        tracker.record_execution(old_id, "transition", "ESCRUM-123", "success")

        assert tracker.is_executed(old_id) is True

        # Advance time past cleanup threshold
        clock.advance(hours=49)

        # Record a new execution to trigger cleanup
        new_id = tracker.generate_execution_id("transition", "ESCRUM-456", "dev_alice")
        tracker.record_execution(new_id, "transition", "ESCRUM-456", "success")

        # Old record should be cleaned up
        assert tracker.is_executed(old_id) is False
        assert tracker.is_executed(new_id) is True

    def test_cleanup_keeps_recent_records(self):
        """Records younger than cleanup_age_hours are kept."""
        clock = FakeClock(pendulum.datetime(2026, 1, 28, 10, 0, tz="UTC"))
        tracker = ExecutionTracker(clock=clock, cleanup_age_hours=48)

        # Record an execution
        recent_id = tracker.generate_execution_id("transition", "ESCRUM-123", "dev_alice")
        tracker.record_execution(recent_id, "transition", "ESCRUM-123", "success")

        # Advance time but stay under threshold
        clock.advance(hours=47)

        # Record another execution to trigger cleanup
        new_id = tracker.generate_execution_id("transition", "ESCRUM-456", "dev_alice")
        tracker.record_execution(new_id, "transition", "ESCRUM-456", "success")

        # Recent record should still exist
        assert tracker.is_executed(recent_id) is True
        assert tracker.is_executed(new_id) is True

    def test_custom_cleanup_age(self):
        """Custom cleanup age is respected."""
        clock = FakeClock(pendulum.datetime(2026, 1, 28, 10, 0, tz="UTC"))
        tracker = ExecutionTracker(clock=clock, cleanup_age_hours=24)  # 24 hours instead of 48

        # Record an execution
        old_id = tracker.generate_execution_id("transition", "ESCRUM-123", "dev_alice")
        tracker.record_execution(old_id, "transition", "ESCRUM-123", "success")

        # Advance 25 hours (past 24h threshold but under 48h)
        clock.advance(hours=25)

        # Trigger cleanup
        new_id = tracker.generate_execution_id("transition", "ESCRUM-456", "dev_alice")
        tracker.record_execution(new_id, "transition", "ESCRUM-456", "success")

        # Old record should be cleaned up with 24h threshold
        assert tracker.is_executed(old_id) is False

    def test_cleanup_runs_on_each_record(self):
        """Cleanup runs on each record_execution() call (piggyback pattern)."""
        clock = FakeClock(pendulum.datetime(2026, 1, 28, 10, 0, tz="UTC"))
        tracker = ExecutionTracker(clock=clock, cleanup_age_hours=1)

        # Record multiple executions over time
        # Timeline: record at 10:00, 10:30, 11:00, 11:30, 12:00
        # Clock advances AFTER each record, ending at 12:30
        ids = []
        for i in range(5):
            exec_id = tracker.generate_execution_id("transition", f"ESCRUM-{i}", "dev_alice")
            tracker.record_execution(exec_id, "transition", f"ESCRUM-{i}", "success")
            ids.append(exec_id)
            clock.advance(minutes=30)

        # Final record at 12:30, cleanup threshold is 11:30
        # Records with executed_at > 11:30 are kept (strictly greater)
        final_id = tracker.generate_execution_id("transition", "ESCRUM-999", "dev_alice")
        tracker.record_execution(final_id, "transition", "ESCRUM-999", "success")

        # Records at 10:00, 10:30, 11:00, 11:30 - all <= 11:30, cleaned up
        assert tracker.is_executed(ids[0]) is False  # 10:00 - cleaned
        assert tracker.is_executed(ids[1]) is False  # 10:30 - cleaned
        assert tracker.is_executed(ids[2]) is False  # 11:00 - cleaned
        assert tracker.is_executed(ids[3]) is False  # 11:30 - exactly at cutoff, cleaned
        # Record at 12:00 - strictly > 11:30, kept
        assert tracker.is_executed(ids[4]) is True   # 12:00 - kept
        # Final record at 12:30 - kept
        assert tracker.is_executed(final_id) is True


class TestExecutionRecord:
    """Tests for ExecutionRecord dataclass."""

    def test_record_is_dataclass(self):
        """ExecutionRecord is a dataclass with expected fields."""
        record = ExecutionRecord(
            execution_id="test:ESCRUM-1:agent:abc12345",
            action_type="test",
            ticket_key="ESCRUM-1",
            executed_at=pendulum.datetime(2026, 1, 28, 10, 0, tz="UTC"),
            result="success"
        )

        assert record.execution_id == "test:ESCRUM-1:agent:abc12345"
        assert record.action_type == "test"
        assert record.ticket_key == "ESCRUM-1"
        assert record.result == "success"
        assert isinstance(record.executed_at, pendulum.DateTime)
