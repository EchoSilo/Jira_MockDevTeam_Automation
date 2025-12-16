"""
SQLite database layer for log storage.

Provides schema creation, connection management, and CRUD operations
for all log entry types.
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from .models import (
    LogEntry,
    LogCategory,
    LLMCallLog,
    JiraAPILog,
    AgentDecisionLog,
    OrchestratorLog,
    SessionLog,
)


class LogDatabase:
    """SQLite database for log storage."""

    def __init__(self, db_path: str = "data/logs.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        """Create database tables if they don't exist."""
        with self._get_connection() as conn:
            conn.executescript(
                """
                -- Sessions table
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    tick_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    intensity TEXT,
                    simulation_day INTEGER,
                    sprint_day INTEGER,
                    sprint_number INTEGER,
                    llm_calls INTEGER DEFAULT 0,
                    jira_calls INTEGER DEFAULT 0,
                    actions_planned INTEGER DEFAULT 0,
                    actions_completed INTEGER DEFAULT 0,
                    errors INTEGER DEFAULT 0,
                    total_input_tokens INTEGER DEFAULT 0,
                    total_output_tokens INTEGER DEFAULT 0,
                    success INTEGER DEFAULT 1,
                    error_summary TEXT
                );

                -- LLM calls table
                CREATE TABLE IF NOT EXISTS llm_calls (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    tick_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    is_complex INTEGER,
                    prompt TEXT NOT NULL,
                    response TEXT NOT NULL,
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    agent_id TEXT,
                    agent_name TEXT,
                    ticket_key TEXT,
                    scenario_id TEXT,
                    duration_ms INTEGER DEFAULT 0,
                    error TEXT,
                    success INTEGER DEFAULT 1
                );

                -- Jira API calls table
                CREATE TABLE IF NOT EXISTS jira_calls (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    tick_id TEXT NOT NULL,
                    method TEXT NOT NULL,
                    endpoint TEXT,
                    parameters TEXT,
                    ticket_key TEXT,
                    status_code INTEGER,
                    response_summary TEXT,
                    agent_id TEXT,
                    agent_name TEXT,
                    scenario_id TEXT,
                    duration_ms INTEGER DEFAULT 0,
                    error TEXT,
                    success INTEGER DEFAULT 1
                );

                -- Agent decisions table
                CREATE TABLE IF NOT EXISTS agent_decisions (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    tick_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    agent_role TEXT NOT NULL,
                    team TEXT NOT NULL,
                    decision_type TEXT NOT NULL,
                    action_selected TEXT,
                    alternatives_considered TEXT,
                    reasoning TEXT,
                    ticket_key TEXT,
                    scenario_id TEXT,
                    scenario_phase TEXT
                );

                -- Orchestrator logs table
                CREATE TABLE IF NOT EXISTS orchestrator_logs (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    tick_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    intensity TEXT,
                    analysis_summary TEXT,
                    planned_actions TEXT,
                    planning_reasoning TEXT,
                    action_type TEXT,
                    action_result TEXT,
                    ticket_key TEXT,
                    scenario_id TEXT,
                    agent_id TEXT,
                    error TEXT,
                    success INTEGER DEFAULT 1
                );

                -- Indexes for common queries
                CREATE INDEX IF NOT EXISTS idx_sessions_started_at ON sessions(started_at);
                CREATE INDEX IF NOT EXISTS idx_llm_calls_session ON llm_calls(session_id);
                CREATE INDEX IF NOT EXISTS idx_llm_calls_timestamp ON llm_calls(timestamp);
                CREATE INDEX IF NOT EXISTS idx_llm_calls_agent ON llm_calls(agent_id);
                CREATE INDEX IF NOT EXISTS idx_llm_calls_ticket ON llm_calls(ticket_key);
                CREATE INDEX IF NOT EXISTS idx_jira_calls_session ON jira_calls(session_id);
                CREATE INDEX IF NOT EXISTS idx_jira_calls_timestamp ON jira_calls(timestamp);
                CREATE INDEX IF NOT EXISTS idx_jira_calls_ticket ON jira_calls(ticket_key);
                CREATE INDEX IF NOT EXISTS idx_agent_decisions_session ON agent_decisions(session_id);
                CREATE INDEX IF NOT EXISTS idx_orchestrator_session ON orchestrator_logs(session_id);
            """
            )

    @contextmanager
    def _get_connection(self):
        """Get a database connection with proper cleanup."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def insert_session(self, session: SessionLog) -> None:
        """Insert a session log entry."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    id, session_id, tick_id, started_at, ended_at,
                    intensity, simulation_day, sprint_day, sprint_number,
                    llm_calls, jira_calls, actions_planned, actions_completed,
                    errors, total_input_tokens, total_output_tokens,
                    success, error_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    session.id,
                    session.session_id,
                    session.tick_id,
                    session.started_at.isoformat(),
                    session.ended_at.isoformat() if session.ended_at else None,
                    session.intensity,
                    session.simulation_day,
                    session.sprint_day,
                    session.sprint_number,
                    session.llm_calls,
                    session.jira_calls,
                    session.actions_planned,
                    session.actions_completed,
                    session.errors,
                    session.total_input_tokens,
                    session.total_output_tokens,
                    1 if session.success else 0,
                    session.error_summary,
                ),
            )

    def update_session(self, session: SessionLog) -> None:
        """Update a session log entry."""
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE sessions SET
                    ended_at = ?,
                    llm_calls = ?,
                    jira_calls = ?,
                    actions_planned = ?,
                    actions_completed = ?,
                    errors = ?,
                    total_input_tokens = ?,
                    total_output_tokens = ?,
                    success = ?,
                    error_summary = ?
                WHERE session_id = ?
            """,
                (
                    session.ended_at.isoformat() if session.ended_at else None,
                    session.llm_calls,
                    session.jira_calls,
                    session.actions_planned,
                    session.actions_completed,
                    session.errors,
                    session.total_input_tokens,
                    session.total_output_tokens,
                    1 if session.success else 0,
                    session.error_summary,
                    session.session_id,
                ),
            )

    def insert_llm_call(self, log: LLMCallLog) -> None:
        """Insert an LLM call log entry."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO llm_calls (
                    id, timestamp, session_id, tick_id, model, action_type,
                    is_complex, prompt, response, input_tokens, output_tokens,
                    total_tokens, agent_id, agent_name, ticket_key, scenario_id,
                    duration_ms, error, success
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    log.id,
                    log.timestamp.isoformat(),
                    log.session_id,
                    log.tick_id,
                    log.model,
                    log.action_type,
                    1 if log.is_complex else 0,
                    log.prompt,
                    log.response,
                    log.input_tokens,
                    log.output_tokens,
                    log.total_tokens,
                    log.agent_id,
                    log.agent_name,
                    log.ticket_key,
                    log.scenario_id,
                    log.duration_ms,
                    log.error,
                    1 if log.success else 0,
                ),
            )

    def insert_jira_call(self, log: JiraAPILog) -> None:
        """Insert a Jira API call log entry."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO jira_calls (
                    id, timestamp, session_id, tick_id, method, endpoint,
                    parameters, ticket_key, status_code, response_summary,
                    agent_id, agent_name, scenario_id, duration_ms, error, success
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    log.id,
                    log.timestamp.isoformat(),
                    log.session_id,
                    log.tick_id,
                    log.method,
                    log.endpoint,
                    json.dumps(log.parameters),
                    log.ticket_key,
                    log.status_code,
                    log.response_summary,
                    log.agent_id,
                    log.agent_name,
                    log.scenario_id,
                    log.duration_ms,
                    log.error,
                    1 if log.success else 0,
                ),
            )

    def insert_agent_decision(self, log: AgentDecisionLog) -> None:
        """Insert an agent decision log entry."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_decisions (
                    id, timestamp, session_id, tick_id, agent_id, agent_name,
                    agent_role, team, decision_type, action_selected,
                    alternatives_considered, reasoning, ticket_key,
                    scenario_id, scenario_phase
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    log.id,
                    log.timestamp.isoformat(),
                    log.session_id,
                    log.tick_id,
                    log.agent_id,
                    log.agent_name,
                    log.agent_role,
                    log.team,
                    log.decision_type,
                    log.action_selected,
                    json.dumps(log.alternatives_considered),
                    log.reasoning,
                    log.ticket_key,
                    log.scenario_id,
                    log.scenario_phase,
                ),
            )

    def insert_orchestrator_log(self, log: OrchestratorLog) -> None:
        """Insert an orchestrator log entry."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO orchestrator_logs (
                    id, timestamp, session_id, tick_id, phase, intensity,
                    analysis_summary, planned_actions, planning_reasoning,
                    action_type, action_result, ticket_key, scenario_id,
                    agent_id, error, success
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    log.id,
                    log.timestamp.isoformat(),
                    log.session_id,
                    log.tick_id,
                    log.phase,
                    log.intensity,
                    json.dumps(log.analysis_summary) if log.analysis_summary else None,
                    json.dumps(log.planned_actions) if log.planned_actions else None,
                    log.planning_reasoning,
                    log.action_type,
                    json.dumps(log.action_result) if log.action_result else None,
                    log.ticket_key,
                    log.scenario_id,
                    log.agent_id,
                    log.error,
                    1 if log.success else 0,
                ),
            )

    def insert_log_entry(self, entry: LogEntry) -> None:
        """Insert any log entry type - routes to appropriate method."""
        if isinstance(entry, SessionLog):
            self.insert_session(entry)
        elif isinstance(entry, LLMCallLog):
            self.insert_llm_call(entry)
        elif isinstance(entry, JiraAPILog):
            self.insert_jira_call(entry)
        elif isinstance(entry, AgentDecisionLog):
            self.insert_agent_decision(entry)
        elif isinstance(entry, OrchestratorLog):
            self.insert_orchestrator_log(entry)

    def cleanup_old_logs(self, retention_days: int = 30) -> int:
        """Delete logs older than retention period. Returns count deleted."""
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        cutoff_str = cutoff.isoformat()

        total_deleted = 0
        with self._get_connection() as conn:
            tables = [
                "sessions",
                "llm_calls",
                "jira_calls",
                "agent_decisions",
                "orchestrator_logs",
            ]

            for table in tables:
                timestamp_col = "started_at" if table == "sessions" else "timestamp"
                cursor = conn.execute(
                    f"DELETE FROM {table} WHERE {timestamp_col} < ?", (cutoff_str,)
                )
                total_deleted += cursor.rowcount

            # Reclaim space
            conn.execute("VACUUM")

        return total_deleted
