"""
Jira API client wrapper for the simulator.
Handles all Jira interactions with proper authentication per agent.
"""

import os
from typing import Optional
from jira import JIRA
from jira.resources import Issue


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

    def get_backlog_issues(self, max_results: int = 30) -> list[Issue]:
        """Get issues in backlog (To Do status, not assigned to sprint)."""
        jql = f"""
            project = {self.project_key}
            AND status = "To Do"
            AND sprint IS EMPTY
            ORDER BY priority DESC, created ASC
        """
        return self._client.search_issues(jql, maxResults=max_results)

    def get_in_progress_issues(self, assignee: Optional[str] = None) -> list[Issue]:
        """Get issues currently in progress."""
        jql = f'project = {self.project_key} AND status = "In Progress"'
        if assignee:
            jql += f" AND assignee = {assignee}"
        return self._client.search_issues(jql)

    def get_issues_ready_for_testing(self) -> list[Issue]:
        """Get issues waiting for QA."""
        jql = f"""
            project = {self.project_key}
            AND status IN ("Ready for QA", "In Review", "Code Review")
            ORDER BY updated ASC
        """
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
