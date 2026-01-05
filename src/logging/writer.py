"""
Async log writer with queue-based non-blocking writes.

Uses a background thread to write logs to SQLite without blocking
the main simulation loop.
"""

import atexit
from datetime import datetime
from queue import Queue, Empty
from threading import Thread, Event
from typing import Optional
import uuid

from .models import (
    LogEntry,
    LogCategory,
    LLMCallLog,
    JiraAPILog,
    AgentDecisionLog,
    OrchestratorLog,
    SessionLog,
)
from .database import LogDatabase


class AsyncLogWriter:
    """
    Non-blocking log writer using a queue and background thread.
    Ensures logging doesn't slow down the main simulation.
    """

    def __init__(self, db_path: str = "data/logs.db"):
        self._db_path = db_path
        self._queue: Queue = Queue()
        self._stop_event = Event()
        self._worker_thread: Optional[Thread] = None
        self._db: Optional[LogDatabase] = None

        # Current session tracking
        self._current_session: Optional[SessionLog] = None

    def start(self) -> None:
        """Start the background writer thread."""
        if self._worker_thread is not None and self._worker_thread.is_alive():
            return  # Already running

        self._stop_event.clear()
        self._db = LogDatabase(self._db_path)
        self._worker_thread = Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

        # Ensure proper shutdown
        atexit.register(self.stop)

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the writer and flush remaining logs."""
        if self._worker_thread is None:
            return

        self._stop_event.set()
        self._worker_thread.join(timeout=timeout)
        self._worker_thread = None

    def log(self, entry: LogEntry) -> None:
        """Queue a log entry for async writing."""
        self._queue.put(entry)

    def start_session(
        self,
        intensity: str,
        simulation_day: int,
        sprint_day: int,
        sprint_number: int,
    ) -> SessionLog:
        """
        Start a new session/tick.

        Creates a SessionLog entry and returns it for use by other components.
        The session_id and tick_id can be used to correlate all logs from this tick.
        """
        session = SessionLog(
            session_id=str(uuid.uuid4()),
            tick_id=str(uuid.uuid4()),
            intensity=intensity,
            simulation_day=simulation_day,
            sprint_day=sprint_day,
            sprint_number=sprint_number,
            started_at=datetime.utcnow(),
        )
        self._current_session = session
        self.log(session)
        return session

    def end_session(
        self,
        success: bool = True,
        error_summary: Optional[str] = None,
        llm_calls: int = 0,
        jira_calls: int = 0,
        actions_planned: int = 0,
        actions_completed: int = 0,
        errors: int = 0,
        total_input_tokens: int = 0,
        total_output_tokens: int = 0,
    ) -> None:
        """
        End the current session with final statistics.
        """
        if self._current_session is None:
            return

        self._current_session.ended_at = datetime.utcnow()
        self._current_session.success = success
        self._current_session.error_summary = error_summary
        self._current_session.llm_calls = llm_calls
        self._current_session.jira_calls = jira_calls
        self._current_session.actions_planned = actions_planned
        self._current_session.actions_completed = actions_completed
        self._current_session.errors = errors
        self._current_session.total_input_tokens = total_input_tokens
        self._current_session.total_output_tokens = total_output_tokens

        # Queue update
        self._queue.put(("update_session", self._current_session))
        self._current_session = None

    def get_current_session(self) -> Optional[SessionLog]:
        """Get the current session if one is active."""
        return self._current_session

    def log_llm_call(
        self,
        model: str,
        action_type: str,
        prompt: str,
        response: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        duration_ms: int = 0,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        ticket_key: Optional[str] = None,
        scenario_id: Optional[str] = None,
        error: Optional[str] = None,
        is_complex: bool = False,
        max_tokens: int = 0,
        stop_reason: Optional[str] = None,
    ) -> None:
        """Convenience method to log an LLM call."""
        if self._current_session is None:
            return

        entry = LLMCallLog(
            session_id=self._current_session.session_id,
            tick_id=self._current_session.tick_id,
            model=model,
            action_type=action_type,
            is_complex=is_complex,
            prompt=prompt,
            response=response,
            max_tokens=max_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            stop_reason=stop_reason,
            agent_id=agent_id,
            agent_name=agent_name,
            ticket_key=ticket_key,
            scenario_id=scenario_id,
            duration_ms=duration_ms,
            error=error,
            success=error is None,
        )
        self.log(entry)

    def log_jira_call(
        self,
        method: str,
        ticket_key: Optional[str] = None,
        parameters: Optional[dict] = None,
        status_code: Optional[int] = None,
        response_summary: Optional[str] = None,
        duration_ms: int = 0,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        scenario_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Convenience method to log a Jira API call."""
        if self._current_session is None:
            return

        entry = JiraAPILog(
            session_id=self._current_session.session_id,
            tick_id=self._current_session.tick_id,
            method=method,
            ticket_key=ticket_key,
            parameters=parameters or {},
            status_code=status_code,
            response_summary=response_summary,
            agent_id=agent_id,
            agent_name=agent_name,
            scenario_id=scenario_id,
            duration_ms=duration_ms,
            error=error,
            success=error is None,
        )
        self.log(entry)

    def log_orchestrator_event(
        self,
        phase: str,
        intensity: Optional[str] = None,
        analysis_summary: Optional[dict] = None,
        planned_actions: Optional[list] = None,
        planning_reasoning: Optional[str] = None,
        action_type: Optional[str] = None,
        action_result: Optional[dict] = None,
        ticket_key: Optional[str] = None,
        scenario_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        error: Optional[str] = None,
        coordination_summary: Optional[dict] = None,
    ) -> None:
        """Convenience method to log an orchestrator event."""
        if self._current_session is None:
            return

        entry = OrchestratorLog(
            session_id=self._current_session.session_id,
            tick_id=self._current_session.tick_id,
            phase=phase,
            intensity=intensity,
            analysis_summary=analysis_summary,
            planned_actions=planned_actions,
            planning_reasoning=planning_reasoning,
            action_type=action_type,
            action_result=action_result,
            ticket_key=ticket_key,
            scenario_id=scenario_id,
            agent_id=agent_id,
            error=error,
            success=error is None,
            coordination_summary=coordination_summary,
        )
        self.log(entry)

    def log_agent_decision(
        self,
        agent_id: str,
        agent_name: str,
        agent_role: str,
        team: str,
        decision_type: str,
        action_selected: Optional[str] = None,
        alternatives_considered: Optional[list] = None,
        reasoning: Optional[str] = None,
        ticket_key: Optional[str] = None,
        scenario_id: Optional[str] = None,
        scenario_phase: Optional[str] = None,
    ) -> None:
        """Convenience method to log an agent decision."""
        if self._current_session is None:
            return

        entry = AgentDecisionLog(
            session_id=self._current_session.session_id,
            tick_id=self._current_session.tick_id,
            agent_id=agent_id,
            agent_name=agent_name,
            agent_role=agent_role,
            team=team,
            decision_type=decision_type,
            action_selected=action_selected,
            alternatives_considered=alternatives_considered or [],
            reasoning=reasoning,
            ticket_key=ticket_key,
            scenario_id=scenario_id,
            scenario_phase=scenario_phase,
        )
        self.log(entry)

    def _worker_loop(self) -> None:
        """Background worker that writes logs to database."""
        while not self._stop_event.is_set():
            try:
                # Get item with timeout so we can check stop_event periodically
                item = self._queue.get(timeout=0.5)

                if item is None:
                    continue

                # Handle session update specially
                if isinstance(item, tuple) and item[0] == "update_session":
                    self._db.update_session(item[1])
                else:
                    self._db.insert_log_entry(item)

                self._queue.task_done()

            except Empty:
                continue
            except Exception as e:
                # Log errors to stderr but don't crash
                import sys

                print(f"Log writer error: {e}", file=sys.stderr)

        # Drain remaining items on shutdown
        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
                if isinstance(item, tuple) and item[0] == "update_session":
                    self._db.update_session(item[1])
                else:
                    self._db.insert_log_entry(item)
            except Empty:
                break
            except Exception as e:
                import sys
                print(f"Warning: Failed to flush log entry on shutdown: {e}", file=sys.stderr)
