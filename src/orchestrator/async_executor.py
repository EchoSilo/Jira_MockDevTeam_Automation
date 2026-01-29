"""Async action executor with timeout enforcement.

Provides concurrent execution of independent Jira actions with:
- Per-action timeout (default 10s)
- Global tick timeout (default 45s)
- Cascade failure prevention via return_exceptions=True
"""

import asyncio
import logging
import time
from typing import Callable, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ActionResult:
    """Result of a single action execution."""
    action_id: str
    success: bool
    result: dict = field(default_factory=dict)
    error: str | None = None
    timed_out: bool = False
    execution_time_ms: float = 0.0


def is_in_async_context() -> bool:
    """Check if we're in an async context."""
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


class AsyncActionExecutor:
    """Execute multiple actions concurrently with timeout enforcement.

    Uses asyncio.timeout() (Python 3.11+) for per-action and global timeouts.
    Uses asyncio.gather(return_exceptions=True) to prevent cascade failures.
    """

    def __init__(
        self,
        max_action_time: float = 10.0,
        max_total_time: float = 45.0,
    ):
        """Initialize executor with timeout budgets.

        Args:
            max_action_time: Maximum time (seconds) for a single action
            max_total_time: Maximum time (seconds) for all actions combined
        """
        self.max_action_time = max_action_time
        self.max_total_time = max_total_time

    async def _execute_with_timeout(
        self,
        action: dict,
        executor: Callable[[dict], Any],
    ) -> ActionResult:
        """Execute single action with per-action timeout.

        Args:
            action: Action dict (must have 'action_id' key)
            executor: Async function to execute action

        Returns:
            ActionResult with success/failure/timeout status
        """
        action_id = action.get("action_id", "unknown")
        start_time = time.perf_counter()

        try:
            async with asyncio.timeout(self.max_action_time):
                result = await executor(action)
                execution_time = (time.perf_counter() - start_time) * 1000

                return ActionResult(
                    action_id=action_id,
                    success=True,
                    result=result if isinstance(result, dict) else {"value": result},
                    execution_time_ms=execution_time,
                )

        except asyncio.TimeoutError:
            execution_time = (time.perf_counter() - start_time) * 1000
            logger.warning(
                f"Action {action_id} timed out after {self.max_action_time}s"
            )
            return ActionResult(
                action_id=action_id,
                success=False,
                error=f"Action timed out after {self.max_action_time}s",
                timed_out=True,
                execution_time_ms=execution_time,
            )

        except Exception as e:
            execution_time = (time.perf_counter() - start_time) * 1000
            logger.error(f"Action {action_id} failed with error: {e}")
            return ActionResult(
                action_id=action_id,
                success=False,
                error=str(e),
                execution_time_ms=execution_time,
            )

    async def execute_all(
        self,
        actions: list[dict],
        executor: Callable[[dict], Any],
    ) -> tuple[list[ActionResult], list[ActionResult]]:
        """Execute all actions concurrently with timeouts.

        Args:
            actions: List of action dicts (must have 'action_id' key)
            executor: Async function to execute single action

        Returns:
            (successful_results, failed_results)
        """
        if not actions:
            return ([], [])

        try:
            # Global timeout wraps all action execution
            async with asyncio.timeout(self.max_total_time):
                # Create tasks for all actions
                tasks = [
                    self._execute_with_timeout(action, executor)
                    for action in actions
                ]

                # Execute concurrently with return_exceptions=True
                # This prevents one failure from canceling other tasks
                results = await asyncio.gather(*tasks, return_exceptions=True)

        except asyncio.TimeoutError:
            # Global timeout exceeded - mark all incomplete actions as failed
            logger.error(
                f"Global timeout of {self.max_total_time}s exceeded "
                f"while executing {len(actions)} actions"
            )
            # Any incomplete tasks will be cancelled by asyncio.timeout
            # Return empty results - all actions failed
            failed = [
                ActionResult(
                    action_id=action.get("action_id", "unknown"),
                    success=False,
                    error=f"Global timeout of {self.max_total_time}s exceeded",
                    timed_out=True,
                )
                for action in actions
            ]
            return ([], failed)

        # Separate successful from failed results
        successful = []
        failed = []

        for result in results:
            # Handle any exceptions that were returned by gather
            if isinstance(result, Exception):
                # This shouldn't happen since we handle exceptions in _execute_with_timeout
                # but included for safety
                logger.error(f"Unexpected exception in gather: {result}")
                failed.append(ActionResult(
                    action_id="unknown",
                    success=False,
                    error=str(result),
                ))
            elif isinstance(result, ActionResult):
                if result.success:
                    successful.append(result)
                else:
                    failed.append(result)
            else:
                logger.warning(f"Unexpected result type: {type(result)}")

        logger.info(
            f"Executed {len(actions)} actions: "
            f"{len(successful)} successful, {len(failed)} failed"
        )

        return (successful, failed)


async def execute_actions_async(
    actions: list[dict],
    executor: Callable[[dict], Any],
    max_action_time: float = 10.0,
    max_total_time: float = 45.0,
) -> tuple[list[ActionResult], list[ActionResult]]:
    """Convenience function for one-off execution.

    Args:
        actions: List of action dicts (must have 'action_id' key)
        executor: Async function to execute single action
        max_action_time: Maximum time (seconds) for a single action
        max_total_time: Maximum time (seconds) for all actions combined

    Returns:
        (successful_results, failed_results)
    """
    executor_instance = AsyncActionExecutor(max_action_time, max_total_time)
    return await executor_instance.execute_all(actions, executor)
