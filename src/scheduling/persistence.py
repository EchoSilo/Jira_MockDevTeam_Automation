"""SQLite persistence for scheduled actions."""

import json
import sqlite3
from pathlib import Path
from typing import List, Optional

import pendulum

from .models import ActionStatus, ScheduledAction


class ScheduledActionStore:
    """
    SQLite-backed storage for scheduled actions.

    Provides CRUD operations and status filtering for the event scheduler.
    """

    def __init__(self, db_path: str = "data/scheduler.db"):
        """
        Initialize the store and create schema if needed.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

        # Ensure parent directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self._create_table()

    def _create_table(self) -> None:
        """Create scheduled_actions table and indexes if not exists."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Create table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_actions (
                    action_id TEXT PRIMARY KEY,
                    scheduled_time TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    ticket_key TEXT NOT NULL,
                    scenario_id TEXT,
                    window_minutes INTEGER DEFAULT 30,
                    expected_status TEXT,
                    expected_assignee TEXT,
                    status TEXT DEFAULT 'pending',
                    params TEXT,
                    created_at TEXT NOT NULL,
                    executed_at TEXT,
                    result TEXT
                )
                """
            )

            # Create indexes
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_scheduled_time
                ON scheduled_actions(scheduled_time)
                """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_status
                ON scheduled_actions(status)
                """
            )

            conn.commit()

    def save_action(self, action: ScheduledAction) -> None:
        """
        Save or update a scheduled action.

        Args:
            action: The action to persist
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT OR REPLACE INTO scheduled_actions (
                    action_id, scheduled_time, action_type, agent_id, ticket_key,
                    scenario_id, window_minutes, expected_status, expected_assignee,
                    status, params, created_at, executed_at, result
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action.action_id,
                    action.scheduled_time.isoformat(),
                    action.action_type,
                    action.agent_id,
                    action.ticket_key,
                    action.scenario_id,
                    action.window_minutes,
                    action.expected_status,
                    action.expected_assignee,
                    action.status.value,
                    json.dumps(action.params) if action.params else None,
                    action.created_at.isoformat(),
                    action.executed_at.isoformat() if action.executed_at else None,
                    json.dumps(action.result) if action.result else None,
                ),
            )

            conn.commit()

    def load_pending_actions(self) -> List[ScheduledAction]:
        """
        Load all pending actions, sorted by scheduled_time.

        Returns:
            List of pending actions in chronological order
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT * FROM scheduled_actions
                WHERE status = 'pending'
                ORDER BY scheduled_time ASC
                """
            )

            rows = cursor.fetchall()
            return [self._row_to_action(row) for row in rows]

    def update_status(
        self,
        action_id: str,
        status: ActionStatus,
        result: Optional[dict] = None,
        executed_at: Optional[pendulum.DateTime] = None,
    ) -> None:
        """
        Update action status and optional result/executed_at.

        Args:
            action_id: ID of the action to update
            status: New status
            result: Optional result data
            executed_at: Optional execution timestamp
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE scheduled_actions
                SET status = ?, result = ?, executed_at = ?
                WHERE action_id = ?
                """,
                (
                    status.value,
                    json.dumps(result) if result else None,
                    executed_at.isoformat() if executed_at else None,
                    action_id,
                ),
            )

            conn.commit()

    def cleanup_old_actions(self, max_age_hours: int = 48) -> int:
        """
        Delete old completed/skipped actions.

        Args:
            max_age_hours: Maximum age in hours for completed actions

        Returns:
            Number of actions deleted
        """
        cutoff = pendulum.now("UTC").subtract(hours=max_age_hours)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                DELETE FROM scheduled_actions
                WHERE status IN ('completed', 'skipped')
                AND executed_at < ?
                """,
                (cutoff.isoformat(),),
            )

            deleted = cursor.rowcount
            conn.commit()

        return deleted

    def get_action(self, action_id: str) -> Optional[ScheduledAction]:
        """
        Retrieve a specific action by ID.

        Args:
            action_id: ID of the action to retrieve

        Returns:
            The action if found, None otherwise
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT * FROM scheduled_actions
                WHERE action_id = ?
                """,
                (action_id,),
            )

            row = cursor.fetchone()
            return self._row_to_action(row) if row else None

    def _row_to_action(self, row: sqlite3.Row) -> ScheduledAction:
        """
        Convert a database row to a ScheduledAction.

        Args:
            row: SQLite row object

        Returns:
            ScheduledAction instance
        """
        return ScheduledAction(
            action_id=row["action_id"],
            scheduled_time=pendulum.parse(row["scheduled_time"]),
            action_type=row["action_type"],
            agent_id=row["agent_id"],
            ticket_key=row["ticket_key"],
            scenario_id=row["scenario_id"],
            window_minutes=row["window_minutes"],
            expected_status=row["expected_status"],
            expected_assignee=row["expected_assignee"],
            status=ActionStatus(row["status"]),
            params=json.loads(row["params"]) if row["params"] else {},
            created_at=pendulum.parse(row["created_at"]),
            executed_at=pendulum.parse(row["executed_at"]) if row["executed_at"] else None,
            result=json.loads(row["result"]) if row["result"] else None,
        )
