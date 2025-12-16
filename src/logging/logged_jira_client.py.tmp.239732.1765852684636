"""
Logged Jira Client wrapper.

Wraps JiraClient to capture all Jira API calls with parameters,
response summaries, and timing.
"""

import time
from typing import Optional

from jira.resources import Issue

from ..services.jira_client import JiraClient
from .writer import AsyncLogWriter


class LoggedJiraClient(JiraClient):
    """
    Drop-in replacement for JiraClient that logs all API calls.

    Inherits from JiraClient and wraps each method to capture
    method name, parameters, response summary, and timing.
    """

    def __init__(
        self,
        log_writer: AsyncLogWriter,
        email: Optional[str] = None,
        api_token: Optional[str] = None,
        url: Optional[str] = None,
    ):
        super().__init__(email=email, api_token=api_token, url=url)
        self._log_writer = log_writer

        # Context for logging - can be set per-call
        self._current_agent_id: Optional[str] = None
        self._current_agent_name: Optional[str] = None
        self._current_scenario_id: Optional[str] = None

    def set_context(
        self,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        scenario_id: Optional[str] = None,
    ) -> None:
        """Set context for subsequent log entries."""
        self._current_agent_id = agent_id
        self._current_agent_name = agent_name
        self._current_scenario_id = scenario_id

    def clear_context(self) -> None:
        """Clear the current context."""
        self._current_agent_id = None
        self._current_agent_name = None
        self._current_scenario_id = None

    def get_issue(self, issue_key: str) -> Issue:
        """Fetch a single issue by key with logging."""
        start_time = time.time()
        try:
            result = super().get_issue(issue_key)
            duration_ms = int((time.time() - start_time) * 1000)

            self._log_writer.log_jira_call(
                method="get_issue",
                ticket_key=issue_key,
                parameters={"issue_key": issue_key},
                response_summary=f"Retrieved issue: {result.fields.summary[:50]}..."
                if result.fields.summary
                else "Retrieved issue",
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=self._current_agent_name,
                scenario_id=self._current_scenario_id,
            )
            return result

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_writer.log_jira_call(
                method="get_issue",
                ticket_key=issue_key,
                parameters={"issue_key": issue_key},
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=self._current_agent_name,
                scenario_id=self._current_scenario_id,
                error=str(e),
            )
            raise

    def get_project_issues(
        self,
        statuses: Optional[list[str]] = None,
        issue_types: Optional[list[str]] = None,
        max_results: int = 50,
    ) -> list[Issue]:
        """Fetch issues from the project with logging."""
        start_time = time.time()
        try:
            result = super().get_project_issues(statuses, issue_types, max_results)
            duration_ms = int((time.time() - start_time) * 1000)

            self._log_writer.log_jira_call(
                method="get_project_issues",
                parameters={
                    "statuses": statuses,
                    "issue_types": issue_types,
                    "max_results": max_results,
                },
                response_summary=f"Retrieved {len(result)} issues",
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=self._current_agent_name,
                scenario_id=self._current_scenario_id,
            )
            return result

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_writer.log_jira_call(
                method="get_project_issues",
                parameters={
                    "statuses": statuses,
                    "issue_types": issue_types,
                    "max_results": max_results,
                },
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=self._current_agent_name,
                scenario_id=self._current_scenario_id,
                error=str(e),
            )
            raise

    def get_backlog_issues(self, max_results: int = 30) -> list[Issue]:
        """Get backlog issues with logging."""
        start_time = time.time()
        try:
            result = super().get_backlog_issues(max_results)
            duration_ms = int((time.time() - start_time) * 1000)

            self._log_writer.log_jira_call(
                method="get_backlog_issues",
                parameters={"max_results": max_results},
                response_summary=f"Retrieved {len(result)} backlog issues",
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=self._current_agent_name,
                scenario_id=self._current_scenario_id,
            )
            return result

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_writer.log_jira_call(
                method="get_backlog_issues",
                parameters={"max_results": max_results},
                duration_ms=duration_ms,
                error=str(e),
            )
            raise

    def get_in_progress_issues(self, assignee: Optional[str] = None) -> list[Issue]:
        """Get in-progress issues with logging."""
        start_time = time.time()
        try:
            result = super().get_in_progress_issues(assignee)
            duration_ms = int((time.time() - start_time) * 1000)

            self._log_writer.log_jira_call(
                method="get_in_progress_issues",
                parameters={"assignee": assignee},
                response_summary=f"Retrieved {len(result)} in-progress issues",
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=self._current_agent_name,
                scenario_id=self._current_scenario_id,
            )
            return result

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_writer.log_jira_call(
                method="get_in_progress_issues",
                parameters={"assignee": assignee},
                duration_ms=duration_ms,
                error=str(e),
            )
            raise

    def get_issues_ready_for_testing(self) -> list[Issue]:
        """Get issues ready for QA with logging."""
        start_time = time.time()
        try:
            result = super().get_issues_ready_for_testing()
            duration_ms = int((time.time() - start_time) * 1000)

            self._log_writer.log_jira_call(
                method="get_issues_ready_for_testing",
                parameters={},
                response_summary=f"Retrieved {len(result)} issues ready for testing",
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=self._current_agent_name,
                scenario_id=self._current_scenario_id,
            )
            return result

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_writer.log_jira_call(
                method="get_issues_ready_for_testing",
                parameters={},
                duration_ms=duration_ms,
                error=str(e),
            )
            raise

    def transition_issue(self, issue_key: str, transition_name: str) -> bool:
        """Transition an issue with logging."""
        start_time = time.time()
        try:
            result = super().transition_issue(issue_key, transition_name)
            duration_ms = int((time.time() - start_time) * 1000)

            self._log_writer.log_jira_call(
                method="transition_issue",
                ticket_key=issue_key,
                parameters={
                    "issue_key": issue_key,
                    "transition_name": transition_name,
                },
                response_summary=f"Transition {'successful' if result else 'not found'}",
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=self._current_agent_name,
                scenario_id=self._current_scenario_id,
            )
            return result

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_writer.log_jira_call(
                method="transition_issue",
                ticket_key=issue_key,
                parameters={
                    "issue_key": issue_key,
                    "transition_name": transition_name,
                },
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=self._current_agent_name,
                scenario_id=self._current_scenario_id,
                error=str(e),
            )
            raise

    def add_comment(self, issue_key: str, comment: str) -> None:
        """Add a comment with logging."""
        start_time = time.time()
        try:
            super().add_comment(issue_key, comment)
            duration_ms = int((time.time() - start_time) * 1000)

            self._log_writer.log_jira_call(
                method="add_comment",
                ticket_key=issue_key,
                parameters={
                    "issue_key": issue_key,
                    "comment_length": len(comment),
                    "comment_preview": comment[:100] + "..."
                    if len(comment) > 100
                    else comment,
                },
                response_summary="Comment added successfully",
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=self._current_agent_name,
                scenario_id=self._current_scenario_id,
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_writer.log_jira_call(
                method="add_comment",
                ticket_key=issue_key,
                parameters={"issue_key": issue_key, "comment_length": len(comment)},
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=self._current_agent_name,
                scenario_id=self._current_scenario_id,
                error=str(e),
            )
            raise

    def assign_issue(self, issue_key: str, account_id: str) -> None:
        """Assign an issue with logging."""
        start_time = time.time()
        try:
            super().assign_issue(issue_key, account_id)
            duration_ms = int((time.time() - start_time) * 1000)

            self._log_writer.log_jira_call(
                method="assign_issue",
                ticket_key=issue_key,
                parameters={"issue_key": issue_key, "account_id": account_id},
                response_summary=f"Assigned to {account_id}",
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=self._current_agent_name,
                scenario_id=self._current_scenario_id,
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_writer.log_jira_call(
                method="assign_issue",
                ticket_key=issue_key,
                parameters={"issue_key": issue_key, "account_id": account_id},
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=self._current_agent_name,
                scenario_id=self._current_scenario_id,
                error=str(e),
            )
            raise

    def log_work(
        self, issue_key: str, time_spent: str, comment: Optional[str] = None
    ) -> None:
        """Log work with logging."""
        start_time = time.time()
        try:
            super().log_work(issue_key, time_spent, comment)
            duration_ms = int((time.time() - start_time) * 1000)

            self._log_writer.log_jira_call(
                method="log_work",
                ticket_key=issue_key,
                parameters={
                    "issue_key": issue_key,
                    "time_spent": time_spent,
                    "has_comment": comment is not None,
                },
                response_summary=f"Logged {time_spent}",
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=self._current_agent_name,
                scenario_id=self._current_scenario_id,
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_writer.log_jira_call(
                method="log_work",
                ticket_key=issue_key,
                parameters={"issue_key": issue_key, "time_spent": time_spent},
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=self._current_agent_name,
                scenario_id=self._current_scenario_id,
                error=str(e),
            )
            raise

    def create_issue(
        self,
        summary: str,
        description: str,
        issue_type: str = "Story",
        priority: Optional[str] = None,
        labels: Optional[list[str]] = None,
        parent_key: Optional[str] = None,
    ) -> Issue:
        """Create an issue with logging."""
        start_time = time.time()
        try:
            result = super().create_issue(
                summary, description, issue_type, priority, labels, parent_key
            )
            duration_ms = int((time.time() - start_time) * 1000)

            self._log_writer.log_jira_call(
                method="create_issue",
                ticket_key=result.key,
                parameters={
                    "summary": summary[:100],
                    "issue_type": issue_type,
                    "priority": priority,
                    "labels": labels,
                    "parent_key": parent_key,
                },
                response_summary=f"Created {result.key}: {summary[:50]}",
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=self._current_agent_name,
                scenario_id=self._current_scenario_id,
            )
            return result

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_writer.log_jira_call(
                method="create_issue",
                parameters={
                    "summary": summary[:100],
                    "issue_type": issue_type,
                    "priority": priority,
                },
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=self._current_agent_name,
                scenario_id=self._current_scenario_id,
                error=str(e),
            )
            raise

    def link_issues(
        self, from_key: str, to_key: str, link_type: str = "Blocks"
    ) -> None:
        """Link issues with logging."""
        start_time = time.time()
        try:
            super().link_issues(from_key, to_key, link_type)
            duration_ms = int((time.time() - start_time) * 1000)

            self._log_writer.log_jira_call(
                method="link_issues",
                ticket_key=from_key,
                parameters={
                    "from_key": from_key,
                    "to_key": to_key,
                    "link_type": link_type,
                },
                response_summary=f"Linked {from_key} -> {to_key} ({link_type})",
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=self._current_agent_name,
                scenario_id=self._current_scenario_id,
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_writer.log_jira_call(
                method="link_issues",
                ticket_key=from_key,
                parameters={
                    "from_key": from_key,
                    "to_key": to_key,
                    "link_type": link_type,
                },
                duration_ms=duration_ms,
                error=str(e),
            )
            raise

    def update_issue(self, issue_key: str, fields: dict) -> None:
        """Update issue fields with logging."""
        start_time = time.time()
        try:
            super().update_issue(issue_key, fields)
            duration_ms = int((time.time() - start_time) * 1000)

            self._log_writer.log_jira_call(
                method="update_issue",
                ticket_key=issue_key,
                parameters={"issue_key": issue_key, "fields": list(fields.keys())},
                response_summary=f"Updated fields: {list(fields.keys())}",
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=self._current_agent_name,
                scenario_id=self._current_scenario_id,
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_writer.log_jira_call(
                method="update_issue",
                ticket_key=issue_key,
                parameters={"issue_key": issue_key, "fields": list(fields.keys())},
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=self._current_agent_name,
                scenario_id=self._current_scenario_id,
                error=str(e),
            )
            raise

    def get_transitions(self, issue_key: str) -> list[dict]:
        """Get available transitions with logging."""
        start_time = time.time()
        try:
            result = super().get_transitions(issue_key)
            duration_ms = int((time.time() - start_time) * 1000)

            transition_names = [t["name"] for t in result]
            self._log_writer.log_jira_call(
                method="get_transitions",
                ticket_key=issue_key,
                parameters={"issue_key": issue_key},
                response_summary=f"Available: {transition_names}",
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=self._current_agent_name,
                scenario_id=self._current_scenario_id,
            )
            return result

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_writer.log_jira_call(
                method="get_transitions",
                ticket_key=issue_key,
                parameters={"issue_key": issue_key},
                duration_ms=duration_ms,
                error=str(e),
            )
            raise

    def get_comments(self, issue_key: str, max_results: int = 10) -> list:
        """Get comments with logging."""
        start_time = time.time()
        try:
            result = super().get_comments(issue_key, max_results)
            duration_ms = int((time.time() - start_time) * 1000)

            self._log_writer.log_jira_call(
                method="get_comments",
                ticket_key=issue_key,
                parameters={"issue_key": issue_key, "max_results": max_results},
                response_summary=f"Retrieved {len(result)} comments",
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=self._current_agent_name,
                scenario_id=self._current_scenario_id,
            )
            return result

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_writer.log_jira_call(
                method="get_comments",
                ticket_key=issue_key,
                parameters={"issue_key": issue_key, "max_results": max_results},
                duration_ms=duration_ms,
                error=str(e),
            )
            raise

    def get_current_user(self) -> dict:
        """Get current user with logging."""
        start_time = time.time()
        try:
            result = super().get_current_user()
            duration_ms = int((time.time() - start_time) * 1000)

            self._log_writer.log_jira_call(
                method="get_current_user",
                parameters={},
                response_summary=f"User: {result.get('displayName', 'Unknown')}",
                duration_ms=duration_ms,
            )
            return result

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_writer.log_jira_call(
                method="get_current_user",
                parameters={},
                duration_ms=duration_ms,
                error=str(e),
            )
            raise
