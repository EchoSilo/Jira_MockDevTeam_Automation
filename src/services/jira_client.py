"""
Jira API client wrapper for the simulator.
Handles all Jira interactions with proper authentication per agent.
"""

import os
from datetime import date, datetime, timedelta
from typing import Optional
from jira import JIRA
from jira.resources import Issue

# Configured board ID for sprint operations
BOARD_ID = 4


class JiraClient:
    """Wrapper around the Jira API with agent-specific authentication."""

    def __init__(
        self,
        email: Optional[str] = None,
        api_token: Optional[str] = None,
        url: Optional[str] = None,
    ):
        self.url = url or os.environ["JIRA_URL"]
        self.email = email or os.environ["JIRA_EMAIL"]
        self.api_token = api_token or os.environ["JIRA_API_TOKEN"]
        self.project_key = os.environ.get("PROJECT_KEY", "")

        self._client = JIRA(
            server=self.url,
            basic_auth=(self.email, self.api_token),
        )

    def get_issue(self, issue_key: str) -> Issue:
        """Fetch a single issue by key."""
        return self._client.issue(issue_key)

    def get_project_issues(
        self,
        statuses: Optional[list[str]] = None,
        issue_types: Optional[list[str]] = None,
        max_results: int = 50,
    ) -> list[Issue]:
        """Fetch issues from the project with optional filters."""
        jql_parts = [f"project = {self.project_key}"]

        if statuses:
            status_str = ", ".join(f'"{s}"' for s in statuses)
            jql_parts.append(f"status IN ({status_str})")

        if issue_types:
            type_str = ", ".join(f'"{t}"' for t in issue_types)
            jql_parts.append(f"issuetype IN ({type_str})")

        jql = " AND ".join(jql_parts) + " ORDER BY updated DESC"

        return self._client.search_issues(jql, maxResults=max_results)

    def get_backlog_issues(
        self,
        max_results: int = 30,
        issue_types: Optional[list[str]] = None,
    ) -> list[Issue]:
        """Get issues in backlog (To Do status, not assigned to sprint).

        Args:
            max_results: Maximum number of issues to return
            issue_types: Optional list of issue types to filter (e.g., ["Story", "Bug", "Task"])
        """
        jql = f"project = {self.project_key} AND status = 'To Do' AND sprint IS EMPTY"
        if issue_types:
            type_str = ", ".join(f'"{t}"' for t in issue_types)
            jql += f" AND issuetype IN ({type_str})"
        jql += " ORDER BY priority DESC, created ASC"
        return self._client.search_issues(jql, maxResults=max_results)

    def get_in_progress_issues(
        self,
        assignee: Optional[str] = None,
        issue_types: Optional[list[str]] = None,
    ) -> list[Issue]:
        """Get issues currently in progress.

        Args:
            assignee: Optional assignee account ID to filter by
            issue_types: Optional list of issue types to filter (e.g., ["Story", "Bug", "Task"])
        """
        jql = f'project = {self.project_key} AND status = "In Progress"'
        if assignee:
            jql += f" AND assignee = {assignee}"
        if issue_types:
            type_str = ", ".join(f'"{t}"' for t in issue_types)
            jql += f" AND issuetype IN ({type_str})"
        return self._client.search_issues(jql)

    def get_issues_ready_for_testing(
        self,
        issue_types: Optional[list[str]] = None,
    ) -> list[Issue]:
        """Get issues waiting for QA.

        Args:
            issue_types: Optional list of issue types to filter (e.g., ["Story", "Bug", "Task"])
        """
        jql = f'project = {self.project_key} AND status IN ("Ready for QA", "In Review", "Code Review")'
        if issue_types:
            type_str = ", ".join(f'"{t}"' for t in issue_types)
            jql += f" AND issuetype IN ({type_str})"
        jql += " ORDER BY updated ASC"
        return self._client.search_issues(jql)

    def transition_issue(self, issue_key: str, transition_name: str) -> bool:
        """Transition an issue to a new status."""
        issue = self._client.issue(issue_key)
        transitions = self._client.transitions(issue)

        for t in transitions:
            if t["name"].lower() == transition_name.lower():
                self._client.transition_issue(issue, t["id"])
                return True

        # Try partial match
        for t in transitions:
            if transition_name.lower() in t["name"].lower():
                self._client.transition_issue(issue, t["id"])
                return True

        return False

    def add_comment(self, issue_key: str, comment: str) -> None:
        """Add a comment to an issue."""
        self._client.add_comment(issue_key, comment)

    def assign_issue(self, issue_key: str, account_id: str) -> None:
        """Assign an issue to a user by account ID."""
        self._client.assign_issue(issue_key, account_id)

    def log_work(
        self, issue_key: str, time_spent: str, comment: Optional[str] = None
    ) -> None:
        """Log work time on an issue. time_spent format: '1h', '30m', '2h 30m'"""
        self._client.add_worklog(issue_key, timeSpent=time_spent, comment=comment)

    def create_issue(
        self,
        summary: str,
        description: str,
        issue_type: str = "Story",
        priority: Optional[str] = None,
        labels: Optional[list[str]] = None,
        parent_key: Optional[str] = None,
    ) -> Issue:
        """Create a new issue in the project."""
        fields = {
            "project": {"key": self.project_key},
            "summary": summary,
            "description": description,
            "issuetype": {"name": issue_type},
        }

        if priority:
            fields["priority"] = {"name": priority}

        if labels:
            fields["labels"] = labels

        if parent_key and issue_type in ["Sub-task", "Subtask"]:
            fields["parent"] = {"key": parent_key}

        return self._client.create_issue(fields=fields)

    def link_issues(
        self, from_key: str, to_key: str, link_type: str = "Blocks"
    ) -> None:
        """Create a link between two issues."""
        self._client.create_issue_link(link_type, from_key, to_key)

    def update_issue(self, issue_key: str, fields: dict) -> None:
        """Update fields on an issue."""
        issue = self._client.issue(issue_key)
        issue.update(fields=fields)

    def get_transitions(self, issue_key: str) -> list[dict]:
        """Get available transitions for an issue."""
        issue = self._client.issue(issue_key)
        return self._client.transitions(issue)

    def get_comments(self, issue_key: str, max_results: int = 10) -> list:
        """Get recent comments on an issue."""
        issue = self._client.issue(issue_key)
        comments = self._client.comments(issue)
        return comments[-max_results:] if len(comments) > max_results else comments

    def get_current_user(self) -> dict:
        """Get the current authenticated user info."""
        return self._client.myself()

    # ==================== Sprint Methods ====================

    def get_active_sprint(self, board_id: int = BOARD_ID) -> Optional[dict]:
        """Get the currently active sprint for the board."""
        try:
            sprints = self._client.sprints(board_id, state="active")
            if sprints:
                sprint = sprints[0]
                return {
                    "id": sprint.id,
                    "name": sprint.name,
                    "state": sprint.state,
                    "start_date": getattr(sprint, "startDate", None),
                    "end_date": getattr(sprint, "endDate", None),
                }
            return None
        except Exception:
            return None

    def get_future_sprints(
        self, board_id: int = BOARD_ID, max_results: int = 4
    ) -> list[dict]:
        """Get upcoming/future sprints for planning."""
        try:
            sprints = self._client.sprints(board_id, state="future")
            result = []
            for sprint in sprints[:max_results]:
                result.append({
                    "id": sprint.id,
                    "name": sprint.name,
                    "state": sprint.state,
                    "start_date": getattr(sprint, "startDate", None),
                    "end_date": getattr(sprint, "endDate", None),
                })
            return result
        except Exception:
            return []

    def get_sprint_issues(
        self,
        sprint_id: int,
        issue_types: Optional[list[str]] = None,
    ) -> list[Issue]:
        """Get all issues in a specific sprint."""
        jql = f"project = {self.project_key} AND sprint = {sprint_id}"
        if issue_types:
            type_str = ", ".join(f'"{t}"' for t in issue_types)
            jql += f" AND issuetype IN ({type_str})"
        return self._client.search_issues(jql)

    def add_issue_to_sprint(self, sprint_id: int, issue_keys: list[str]) -> bool:
        """Add issues to a sprint."""
        try:
            self._client.add_issues_to_sprint(sprint_id, issue_keys)
            return True
        except Exception:
            return False

    def remove_issue_from_sprint(self, issue_key: str) -> bool:
        """Remove an issue from its current sprint (move to backlog)."""
        try:
            # Setting sprint to None moves it to backlog
            issue = self._client.issue(issue_key)
            # Get the sprint field ID (usually customfield_10020 or similar)
            sprint_field = self._get_sprint_field_id()
            if sprint_field:
                issue.update(fields={sprint_field: None})
                return True
            return False
        except Exception:
            return False

    def _get_sprint_field_id(self) -> Optional[str]:
        """Get the custom field ID for the sprint field."""
        try:
            fields = self._client.fields()
            for field in fields:
                if field["name"].lower() == "sprint":
                    return field["id"]
            return None
        except Exception:
            return None

    def create_sprint(
        self,
        name: str,
        board_id: int = BOARD_ID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Optional[dict]:
        """Create a new sprint on the board."""
        try:
            sprint_data = {"name": name, "board_id": board_id}
            if start_date:
                sprint_data["startDate"] = start_date.isoformat()
            if end_date:
                sprint_data["endDate"] = end_date.isoformat()

            sprint = self._client.create_sprint(**sprint_data)
            return {
                "id": sprint.id,
                "name": sprint.name,
                "state": sprint.state,
            }
        except Exception:
            return None

    def start_sprint(
        self,
        sprint_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> bool:
        """
        Activate a future sprint by setting state to 'active'.

        Note: If another sprint is active, it will be auto-closed by Jira.
        Requires start_date and end_date if not already set on the sprint.
        """
        try:
            update_data = {"state": "active"}
            if start_date:
                update_data["startDate"] = start_date.isoformat()
            if end_date:
                update_data["endDate"] = end_date.isoformat()

            self._client.update_sprint(sprint_id, **update_data)
            return True
        except Exception:
            return False

    def complete_sprint(
        self,
        sprint_id: int,
        move_incomplete_to: Optional[int] = None,
    ) -> bool:
        """
        Complete an active sprint by setting state to 'closed'.

        Args:
            sprint_id: The sprint to complete
            move_incomplete_to: Optional sprint ID to move incomplete issues to
        """
        try:
            self._client.update_sprint(sprint_id, state="closed")
            return True
        except Exception:
            return False

    def get_issues_not_in_sprint(
        self, issue_types: Optional[list[str]] = None
    ) -> list[Issue]:
        """Get issues not assigned to any sprint (refinement backlog)."""
        jql = f"project = {self.project_key} AND sprint IS EMPTY AND status != Done"
        if issue_types:
            type_str = ", ".join(f'"{t}"' for t in issue_types)
            jql += f" AND issuetype IN ({type_str})"
        jql += " ORDER BY priority DESC, created ASC"
        return self._client.search_issues(jql)

    def is_issue_in_active_sprint(self, issue_key: str) -> bool:
        """Check if an issue is in the currently active sprint."""
        try:
            issue = self._client.issue(issue_key)
            # Try standard sprint field, then customfield_10020 (common sprint field)
            sprint_field = getattr(issue.fields, "sprint", None)
            if not sprint_field:
                sprint_field = getattr(issue.fields, "customfield_10020", None)

            if sprint_field:
                # sprint_field can be a list of sprint objects
                if isinstance(sprint_field, list):
                    for sprint in sprint_field:
                        if hasattr(sprint, "state") and sprint.state == "active":
                            return True
                elif hasattr(sprint_field, "state"):
                    return sprint_field.state == "active"
            return False
        except Exception:
            return False

    def get_issue_sprint_info(self, issue_key: str) -> Optional[dict]:
        """Get sprint information for an issue."""
        try:
            issue = self._client.issue(issue_key)
            # Try standard sprint field, then customfield_10020 (common sprint field)
            sprint_field = getattr(issue.fields, "sprint", None)
            if not sprint_field:
                sprint_field = getattr(issue.fields, "customfield_10020", None)

            if sprint_field:
                if isinstance(sprint_field, list) and sprint_field:
                    sprint = sprint_field[-1]  # Most recent sprint
                    return {
                        "id": getattr(sprint, "id", None),
                        "name": getattr(sprint, "name", None),
                        "state": getattr(sprint, "state", None),
                    }
                elif hasattr(sprint_field, "id"):
                    return {
                        "id": sprint_field.id,
                        "name": getattr(sprint_field, "name", None),
                        "state": getattr(sprint_field, "state", None),
                    }
            return None
        except Exception:
            return None

    # ==================== Epic Methods ====================

    def get_epic_children(self, epic_key: str) -> list[Issue]:
        """Get all child issues of an Epic."""
        # Try both Epic Link and parent fields (depends on Jira version)
        jql = f'"Epic Link" = {epic_key} OR parent = {epic_key}'
        try:
            return self._client.search_issues(jql)
        except Exception:
            # Fall back to just Epic Link if parent syntax fails
            jql = f'"Epic Link" = {epic_key}'
            return self._client.search_issues(jql)

    def get_epics(self, max_results: int = 50) -> list[Issue]:
        """Get all Epics in the project."""
        jql = f'project = {self.project_key} AND issuetype = Epic ORDER BY updated DESC'
        return self._client.search_issues(jql, maxResults=max_results)

    def get_unassigned_epics(self) -> list[Issue]:
        """Get Epics that are not assigned to anyone."""
        jql = f'project = {self.project_key} AND issuetype = Epic AND assignee IS EMPTY'
        return self._client.search_issues(jql)

    def get_epics_needing_status_update(self) -> list[dict]:
        """
        Find Epics whose status doesn't match their children's state.

        Returns list of dicts with epic_key, current_status, suggested_status, reason
        """
        needs_update = []
        epics = self.get_epics()

        for epic in epics:
            children = self.get_epic_children(epic.key)
            if not children:
                continue

            child_statuses = [c.fields.status.name for c in children]
            epic_status = epic.fields.status.name

            # Determine what the Epic status should be
            all_done = all(
                s.lower() in ["done", "closed", "resolved"] for s in child_statuses
            )
            all_todo = all(
                s.lower() in ["to do", "backlog", "open"] for s in child_statuses
            )
            any_in_progress = any(
                s.lower() not in ["to do", "backlog", "open", "done", "closed", "resolved"]
                for s in child_statuses
            )

            suggested_status = None
            reason = None

            if all_done and epic_status.lower() not in ["done", "closed", "resolved"]:
                suggested_status = "Done"
                reason = "All child issues are completed"
            elif all_todo and epic_status.lower() not in ["to do", "backlog", "open"]:
                suggested_status = "To Do"
                reason = "All child issues are still in To Do"
            elif any_in_progress and epic_status.lower() in ["to do", "backlog", "open"]:
                suggested_status = "In Progress"
                reason = "Child issues have started work"

            if suggested_status:
                needs_update.append({
                    "epic_key": epic.key,
                    "current_status": epic_status,
                    "suggested_status": suggested_status,
                    "child_count": len(children),
                    "reason": reason,
                    "child_statuses": list(set(child_statuses)),
                })

        return needs_update
