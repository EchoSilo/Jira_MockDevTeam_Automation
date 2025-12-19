"""
Query interface for log database.

Provides methods to query and retrieve log entries for the viewer UI.
"""

import sqlite3
import json
from datetime import datetime
from typing import Optional, List
from pathlib import Path

from .models import (
    SessionLog,
    LLMCallLog,
    JiraAPILog,
    AgentDecisionLog,
    OrchestratorLog,
)


class LogQueryService:
    """Service for querying log entries."""

    # Timestamp fields that need UTC 'Z' suffix for JavaScript
    _TIMESTAMP_FIELDS = {"timestamp", "started_at", "ended_at"}

    def __init__(self, db_path: str = "data/logs.db"):
        self._db_path = Path(db_path)
        self._ensure_schema()

    def _ensure_utc_suffix(self, data: dict) -> dict:
        """Ensure timestamp fields have 'Z' suffix so JS interprets as UTC."""
        for field in self._TIMESTAMP_FIELDS:
            if field in data and data[field]:
                ts = data[field]
                if isinstance(ts, str) and not ts.endswith("Z"):
                    data[field] = ts + "Z"
        return data

    def _ensure_schema(self):
        """Create database tables if they don't exist."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        from .database import LogDatabase
        LogDatabase(str(self._db_path))

    def _get_connection(self):
        """Get a database connection."""
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def get_sessions(
        self,
        limit: int = 50,
        offset: int = 0,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[dict]:
        """Get session list with pagination, aggregating token counts from llm_calls."""
        conn = self._get_connection()
        try:
            # Join with llm_calls to get actual token counts
            query = """
                SELECT
                    s.*,
                    COALESCE(SUM(l.input_tokens), 0) as computed_input_tokens,
                    COALESCE(SUM(l.output_tokens), 0) as computed_output_tokens,
                    COUNT(l.id) as computed_llm_calls,
                    COALESCE(SUM(CASE WHEN l.is_complex = 1 THEN l.input_tokens ELSE 0 END), 0) as complex_input_tokens,
                    COALESCE(SUM(CASE WHEN l.is_complex = 1 THEN l.output_tokens ELSE 0 END), 0) as complex_output_tokens,
                    COALESCE(SUM(CASE WHEN l.is_complex = 0 THEN l.input_tokens ELSE 0 END), 0) as routine_input_tokens,
                    COALESCE(SUM(CASE WHEN l.is_complex = 0 THEN l.output_tokens ELSE 0 END), 0) as routine_output_tokens
                FROM sessions s
                LEFT JOIN llm_calls l ON s.session_id = l.session_id
                WHERE 1=1
            """
            params = []

            if start_date:
                query += " AND s.started_at >= ?"
                params.append(start_date.isoformat())

            if end_date:
                query += " AND s.started_at <= ?"
                params.append(end_date.isoformat())

            query += " GROUP BY s.session_id ORDER BY s.started_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

            results = []
            for row in rows:
                entry = dict(row)
                # Use computed values instead of stored values (which may be 0)
                entry["total_input_tokens"] = entry.pop("computed_input_tokens", 0)
                entry["total_output_tokens"] = entry.pop("computed_output_tokens", 0)
                entry["llm_calls"] = entry.pop("computed_llm_calls", 0)
                self._ensure_utc_suffix(entry)
                results.append(entry)

            return results
        finally:
            conn.close()

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get a single session by ID."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            if row:
                entry = dict(row)
                return self._ensure_utc_suffix(entry)
            return None
        finally:
            conn.close()

    def get_session_timeline(self, session_id: str) -> List[dict]:
        """
        Get all log entries for a session in chronological order.
        Returns unified list with entry_type field.
        """
        conn = self._get_connection()
        try:
            timeline = []

            # Get LLM calls
            cursor = conn.execute(
                """SELECT *, 'llm_call' as entry_type FROM llm_calls
                   WHERE session_id = ? ORDER BY timestamp""",
                (session_id,),
            )
            for row in cursor.fetchall():
                entry = dict(row)
                self._ensure_utc_suffix(entry)
                timeline.append(entry)

            # Get Jira calls
            cursor = conn.execute(
                """SELECT *, 'jira_call' as entry_type FROM jira_calls
                   WHERE session_id = ? ORDER BY timestamp""",
                (session_id,),
            )
            for row in cursor.fetchall():
                entry = dict(row)
                if entry.get("parameters"):
                    entry["parameters"] = json.loads(entry["parameters"])
                self._ensure_utc_suffix(entry)
                timeline.append(entry)

            # Get orchestrator logs
            cursor = conn.execute(
                """SELECT *, 'orchestrator' as entry_type FROM orchestrator_logs
                   WHERE session_id = ? ORDER BY timestamp""",
                (session_id,),
            )
            for row in cursor.fetchall():
                entry = dict(row)
                if entry.get("analysis_summary"):
                    entry["analysis_summary"] = json.loads(entry["analysis_summary"])
                if entry.get("planned_actions"):
                    entry["planned_actions"] = json.loads(entry["planned_actions"])
                if entry.get("action_result"):
                    entry["action_result"] = json.loads(entry["action_result"])
                self._ensure_utc_suffix(entry)
                timeline.append(entry)

            # Get agent decisions
            cursor = conn.execute(
                """SELECT *, 'agent_decision' as entry_type FROM agent_decisions
                   WHERE session_id = ? ORDER BY timestamp""",
                (session_id,),
            )
            for row in cursor.fetchall():
                entry = dict(row)
                if entry.get("alternatives_considered"):
                    entry["alternatives_considered"] = json.loads(
                        entry["alternatives_considered"]
                    )
                self._ensure_utc_suffix(entry)
                timeline.append(entry)

            # Sort all entries by timestamp
            timeline.sort(key=lambda x: x.get("timestamp", ""))

            return timeline

        finally:
            conn.close()

    def get_conversation_view(self, session_id: str) -> List[dict]:
        """
        Get LLM calls formatted as conversation view.
        Shows prompt/response pairs in sequence.
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """SELECT
                    id, timestamp, model, action_type, is_complex,
                    prompt, response, max_tokens, input_tokens, output_tokens,
                    total_tokens, agent_id, agent_name, ticket_key, scenario_id,
                    duration_ms, error, success, stop_reason
                FROM llm_calls
                WHERE session_id = ?
                ORDER BY timestamp""",
                (session_id,),
            )

            conversations = []
            for row in cursor.fetchall():
                entry = dict(row)
                entry["is_complex"] = bool(entry.get("is_complex"))
                entry["success"] = bool(entry.get("success"))
                self._ensure_utc_suffix(entry)
                conversations.append(entry)

            return conversations

        finally:
            conn.close()

    def get_session_errors(self, session_id: str) -> List[dict]:
        """
        Get all errors for a session from all log tables.
        Aggregates errors from sessions, llm_calls, jira_calls, and orchestrator_logs.
        """
        conn = self._get_connection()
        try:
            errors = []

            # Session-level error summary
            cursor = conn.execute(
                "SELECT error_summary, errors FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            if row and row["error_summary"]:
                errors.append({
                    "source": "session",
                    "timestamp": None,
                    "error": row["error_summary"],
                    "context": f"{row['errors']} total errors in session",
                })

            # LLM call errors
            cursor = conn.execute(
                """SELECT timestamp, action_type, agent_name, ticket_key, error
                   FROM llm_calls
                   WHERE session_id = ? AND error IS NOT NULL AND error != ''
                   ORDER BY timestamp""",
                (session_id,),
            )
            for row in cursor.fetchall():
                entry = dict(row)
                entry["source"] = "llm_call"
                self._ensure_utc_suffix(entry)
                errors.append(entry)

            # Jira call errors
            cursor = conn.execute(
                """SELECT timestamp, method, ticket_key, error
                   FROM jira_calls
                   WHERE session_id = ? AND (error IS NOT NULL AND error != '')
                   ORDER BY timestamp""",
                (session_id,),
            )
            for row in cursor.fetchall():
                entry = dict(row)
                entry["source"] = "jira_call"
                self._ensure_utc_suffix(entry)
                errors.append(entry)

            # Orchestrator errors
            cursor = conn.execute(
                """SELECT timestamp, phase, action_type, ticket_key, error
                   FROM orchestrator_logs
                   WHERE session_id = ? AND error IS NOT NULL AND error != ''
                   ORDER BY timestamp""",
                (session_id,),
            )
            for row in cursor.fetchall():
                entry = dict(row)
                entry["source"] = "orchestrator"
                self._ensure_utc_suffix(entry)
                errors.append(entry)

            # Sort all errors by timestamp (session-level errors without timestamp go first)
            errors.sort(key=lambda x: x.get("timestamp") or "")

            return errors

        finally:
            conn.close()

    def get_llm_calls(
        self,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        ticket_key: Optional[str] = None,
        model: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[dict]:
        """Query LLM calls with filters."""
        conn = self._get_connection()
        try:
            query = "SELECT * FROM llm_calls WHERE 1=1"
            params = []

            if session_id:
                query += " AND session_id = ?"
                params.append(session_id)

            if agent_id:
                query += " AND agent_id = ?"
                params.append(agent_id)

            if ticket_key:
                query += " AND ticket_key = ?"
                params.append(ticket_key)

            if model:
                query += " AND model = ?"
                params.append(model)

            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

            results = []
            for row in rows:
                entry = dict(row)
                entry["is_complex"] = bool(entry.get("is_complex"))
                entry["success"] = bool(entry.get("success"))
                self._ensure_utc_suffix(entry)
                results.append(entry)

            return results

        finally:
            conn.close()

    def get_jira_calls(
        self,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        ticket_key: Optional[str] = None,
        method: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[dict]:
        """Query Jira API calls with filters."""
        conn = self._get_connection()
        try:
            query = "SELECT * FROM jira_calls WHERE 1=1"
            params = []

            if session_id:
                query += " AND session_id = ?"
                params.append(session_id)

            if agent_id:
                query += " AND agent_id = ?"
                params.append(agent_id)

            if ticket_key:
                query += " AND ticket_key = ?"
                params.append(ticket_key)

            if method:
                query += " AND method = ?"
                params.append(method)

            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

            results = []
            for row in rows:
                entry = dict(row)
                if entry.get("parameters"):
                    entry["parameters"] = json.loads(entry["parameters"])
                entry["success"] = bool(entry.get("success"))
                self._ensure_utc_suffix(entry)
                results.append(entry)

            return results

        finally:
            conn.close()

    def get_token_usage_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        """Get token usage statistics."""
        conn = self._get_connection()
        try:
            query = """
                SELECT
                    COUNT(*) as total_calls,
                    SUM(input_tokens) as total_input_tokens,
                    SUM(output_tokens) as total_output_tokens,
                    SUM(total_tokens) as total_tokens,
                    AVG(duration_ms) as avg_duration_ms,
                    SUM(CASE WHEN is_complex = 1 THEN 1 ELSE 0 END) as complex_calls,
                    SUM(CASE WHEN is_complex = 0 THEN 1 ELSE 0 END) as routine_calls,
                    SUM(CASE WHEN is_complex = 1 THEN input_tokens ELSE 0 END) as complex_input_tokens,
                    SUM(CASE WHEN is_complex = 1 THEN output_tokens ELSE 0 END) as complex_output_tokens,
                    SUM(CASE WHEN is_complex = 0 THEN input_tokens ELSE 0 END) as routine_input_tokens,
                    SUM(CASE WHEN is_complex = 0 THEN output_tokens ELSE 0 END) as routine_output_tokens
                FROM llm_calls
                WHERE 1=1
            """
            params = []

            if start_date:
                query += " AND timestamp >= ?"
                params.append(start_date.isoformat())

            if end_date:
                query += " AND timestamp <= ?"
                params.append(end_date.isoformat())

            cursor = conn.execute(query, params)
            row = cursor.fetchone()

            if row:
                return {
                    "total_calls": row["total_calls"] or 0,
                    "total_input_tokens": row["total_input_tokens"] or 0,
                    "total_output_tokens": row["total_output_tokens"] or 0,
                    "total_tokens": row["total_tokens"] or 0,
                    "avg_duration_ms": round(row["avg_duration_ms"] or 0, 2),
                    "complex_calls": row["complex_calls"] or 0,
                    "routine_calls": row["routine_calls"] or 0,
                    "complex_input_tokens": row["complex_input_tokens"] or 0,
                    "complex_output_tokens": row["complex_output_tokens"] or 0,
                    "routine_input_tokens": row["routine_input_tokens"] or 0,
                    "routine_output_tokens": row["routine_output_tokens"] or 0,
                }

            return {
                "total_calls": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_tokens": 0,
                "avg_duration_ms": 0,
                "complex_calls": 0,
                "routine_calls": 0,
                "complex_input_tokens": 0,
                "complex_output_tokens": 0,
                "routine_input_tokens": 0,
                "routine_output_tokens": 0,
            }

        finally:
            conn.close()

    def get_session_count(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        """Get total session count for pagination."""
        conn = self._get_connection()
        try:
            query = "SELECT COUNT(*) as count FROM sessions WHERE 1=1"
            params = []

            if start_date:
                query += " AND started_at >= ?"
                params.append(start_date.isoformat())

            if end_date:
                query += " AND started_at <= ?"
                params.append(end_date.isoformat())

            cursor = conn.execute(query, params)
            row = cursor.fetchone()

            return row["count"] if row else 0

        finally:
            conn.close()
