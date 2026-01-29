"""Tests for async action executor with timeout enforcement."""

import pytest
import asyncio
import time
from src.orchestrator.async_executor import (
    AsyncActionExecutor,
    ActionResult,
    execute_actions_async,
    is_in_async_context,
)


@pytest.mark.asyncio
async def test_concurrent_execution():
    """Multiple actions execute concurrently, not sequentially."""
    start_times = []

    async def slow_action(action: dict) -> dict:
        """Action that tracks when it starts."""
        start_times.append(time.perf_counter())
        await asyncio.sleep(0.2)  # Simulate work
        return {"status": "done", "action_id": action["action_id"]}

    actions = [
        {"action_id": f"action-{i}"}
        for i in range(3)
    ]

    executor = AsyncActionExecutor(max_action_time=5.0)
    overall_start = time.perf_counter()
    successful, failed = await executor.execute_all(actions, slow_action)
    overall_duration = time.perf_counter() - overall_start

    # All actions should succeed
    assert len(successful) == 3
    assert len(failed) == 0

    # All actions should start within ~100ms of each other (concurrent)
    assert len(start_times) == 3
    time_spread = max(start_times) - min(start_times)
    assert time_spread < 0.15, f"Actions didn't start concurrently (spread: {time_spread}s)"

    # Total time should be ~0.2s (concurrent), not ~0.6s (sequential)
    assert overall_duration < 0.5, f"Actions ran sequentially? Duration: {overall_duration}s"


@pytest.mark.asyncio
async def test_single_action_timeout_no_cascade():
    """One slow action doesn't cancel other actions."""

    async def executor_func(action: dict) -> dict:
        """Variable-duration action."""
        duration = action.get("duration", 0.1)
        await asyncio.sleep(duration)
        return {"status": "done", "action_id": action["action_id"]}

    actions = [
        {"action_id": "fast-1", "duration": 0.1},
        {"action_id": "slow", "duration": 15.0},  # Will timeout at 2s
        {"action_id": "fast-2", "duration": 0.1},
    ]

    executor = AsyncActionExecutor(max_action_time=2.0, max_total_time=30.0)
    successful, failed = await executor.execute_all(actions, executor_func)

    # Two fast actions should succeed
    assert len(successful) == 2
    assert {r.action_id for r in successful} == {"fast-1", "fast-2"}

    # One slow action should timeout
    assert len(failed) == 1
    failed_action = failed[0]
    assert failed_action.action_id == "slow"
    assert failed_action.timed_out is True
    assert "timed out" in failed_action.error.lower()


@pytest.mark.asyncio
async def test_global_timeout_stops_all():
    """Global timeout stops all actions if tick budget exceeded."""

    async def slow_action(action: dict) -> dict:
        """Each action takes 2s (longer than global timeout)."""
        await asyncio.sleep(2.0)
        return {"status": "done"}

    actions = [
        {"action_id": f"action-{i}"}
        for i in range(5)  # 5 actions each taking 2s, but global timeout is 1s
    ]

    executor = AsyncActionExecutor(max_action_time=10.0, max_total_time=1.0)
    start = time.perf_counter()
    successful, failed = await executor.execute_all(actions, slow_action)
    duration = time.perf_counter() - start

    # Should stop around 1.0s, not run full 2.0s
    assert duration < 1.5, f"Global timeout didn't stop execution (duration: {duration}s)"

    # All actions should be marked as failed due to global timeout
    assert len(successful) == 0
    assert len(failed) == 5

    # All should have timeout error
    for result in failed:
        assert result.timed_out is True
        assert "global timeout" in result.error.lower()


@pytest.mark.asyncio
async def test_execution_time_tracked():
    """Each action tracks its execution time."""

    async def timed_action(action: dict) -> dict:
        """Action with known duration."""
        duration = action.get("duration", 0.1)
        await asyncio.sleep(duration)
        return {"status": "done"}

    actions = [
        {"action_id": "short", "duration": 0.1},
        {"action_id": "medium", "duration": 0.3},
    ]

    executor = AsyncActionExecutor()
    successful, failed = await executor.execute_all(actions, timed_action)

    assert len(successful) == 2
    assert len(failed) == 0

    # Check execution times are tracked and reasonable
    short_result = next(r for r in successful if r.action_id == "short")
    medium_result = next(r for r in successful if r.action_id == "medium")

    # Should be roughly 100ms and 300ms (in milliseconds)
    assert 80 < short_result.execution_time_ms < 200
    assert 280 < medium_result.execution_time_ms < 400

    # Medium should take longer than short
    assert medium_result.execution_time_ms > short_result.execution_time_ms


@pytest.mark.asyncio
async def test_exception_in_action_captured():
    """Exception in one action doesn't crash others."""

    async def failing_action(action: dict) -> dict:
        """Action that may fail."""
        if action["action_id"] == "will-fail":
            raise ValueError("Simulated failure")
        await asyncio.sleep(0.1)
        return {"status": "done"}

    actions = [
        {"action_id": "normal-1"},
        {"action_id": "will-fail"},
        {"action_id": "normal-2"},
    ]

    executor = AsyncActionExecutor()
    successful, failed = await executor.execute_all(actions, failing_action)

    # Two normal actions should succeed
    assert len(successful) == 2
    assert {r.action_id for r in successful} == {"normal-1", "normal-2"}

    # One action should fail with exception
    assert len(failed) == 1
    failed_action = failed[0]
    assert failed_action.action_id == "will-fail"
    assert failed_action.success is False
    assert failed_action.timed_out is False
    assert "Simulated failure" in failed_action.error


@pytest.mark.asyncio
async def test_empty_action_list():
    """Empty action list returns empty results."""

    async def dummy_action(action: dict) -> dict:
        return {"status": "done"}

    executor = AsyncActionExecutor()
    successful, failed = await executor.execute_all([], dummy_action)

    assert successful == []
    assert failed == []


@pytest.mark.asyncio
async def test_convenience_function():
    """execute_actions_async convenience function works."""

    async def simple_action(action: dict) -> dict:
        return {"status": "done", "action_id": action["action_id"]}

    actions = [
        {"action_id": "test-1"},
        {"action_id": "test-2"},
    ]

    successful, failed = await execute_actions_async(
        actions,
        simple_action,
        max_action_time=5.0,
        max_total_time=30.0,
    )

    assert len(successful) == 2
    assert len(failed) == 0
    assert {r.action_id for r in successful} == {"test-1", "test-2"}


def test_is_in_async_context():
    """is_in_async_context detects async context correctly."""
    # Outside async context
    assert is_in_async_context() is False

    # Will test inside async context in async test
    async def check_inside():
        return is_in_async_context()

    result = asyncio.run(check_inside())
    assert result is True


@pytest.mark.asyncio
async def test_action_result_dataclass():
    """ActionResult dataclass has expected fields."""
    result = ActionResult(
        action_id="test-action",
        success=True,
        result={"key": "value"},
        error=None,
        timed_out=False,
        execution_time_ms=123.45,
    )

    assert result.action_id == "test-action"
    assert result.success is True
    assert result.result == {"key": "value"}
    assert result.error is None
    assert result.timed_out is False
    assert result.execution_time_ms == 123.45

    # Test default factory
    result_defaults = ActionResult(
        action_id="test",
        success=False,
    )
    assert result_defaults.result == {}
    assert result_defaults.error is None
