"""
CrewAI tools for Jira operations.
These wrap the JiraClient for use in CrewAI agents if needed.
"""

from typing import Optional
from crewai.tools import tool

from ..services.jira_client import JiraClient


class JiraTools:
    """Collection of Jira tools for CrewAI agents."""

    def __init__(self, jira_client: JiraClient):
        self.jira = jira_client

    def get_tools(self) -> list:
        """Return list of tools for CrewAI."""
        return [
            self.search_issues,
            self.get_issue_details,
            self.add_comment,
            self.transition_issue,
        ]

    @tool("Search Jira Issues")
    def search_issues(self, query: str) -> str:
        """
        Search for Jira issues.
        Args:
            query: Search terms or JQL query
        Returns:
            List of matching issues
        """
        try:
            # Simple search - try as JQL first
            if "=" in query or "AND" in query or "OR" in query:
                issues = self.jira._client.search_issues(query, maxResults=10)
            else:
                # Text search
                jql = f'project = {self.jira.project_key} AND text ~ "{query}"'
                issues = self.jira._client.search_issues(jql, maxResults=10)

            results = []
            for issue in issues:
                results.append(
                    f"- {issue.key}: {issue.fields.summary} [{issue.fields.status.name}]"
                )

            return "\n".join(results) if results else "No issues found"
        except Exception as e:
            return f"Error searching: {str(e)}"

    @tool("Get Issue Details")
    def get_issue_details(self, issue_key: str) -> str:
        """
        Get detailed information about a specific issue.
        Args:
            issue_key: The Jira issue key (e.g., PROJ-123)
        Returns:
            Issue details including summary, description, status, assignee
        """
        try:
            issue = self.jira.get_issue(issue_key)
            assignee = issue.fields.assignee
            assignee_name = assignee.displayName if assignee else "Unassigned"

            return f"""
Issue: {issue.key}
Summary: {issue.fields.summary}
Status: {issue.fields.status.name}
Type: {issue.fields.issuetype.name}
Assignee: {assignee_name}
Priority: {issue.fields.priority.name if issue.fields.priority else 'None'}

Description:
{issue.fields.description or 'No description'}
""".strip()
        except Exception as e:
            return f"Error getting issue: {str(e)}"

    @tool("Add Comment to Issue")
    def add_comment(self, issue_key: str, comment: str) -> str:
        """
        Add a comment to a Jira issue.
        Args:
            issue_key: The Jira issue key
            comment: The comment text to add
        Returns:
            Confirmation message
        """
        try:
            self.jira.add_comment(issue_key, comment)
            return f"Comment added to {issue_key}"
        except Exception as e:
            return f"Error adding comment: {str(e)}"

    @tool("Transition Issue Status")
    def transition_issue(self, issue_key: str, status: str) -> str:
        """
        Change the status of a Jira issue.
        Args:
            issue_key: The Jira issue key
            status: Target status name (e.g., 'In Progress', 'Done')
        Returns:
            Confirmation or error message
        """
        try:
            success = self.jira.transition_issue(issue_key, status)
            if success:
                return f"Transitioned {issue_key} to {status}"
            else:
                return f"Could not transition {issue_key} to {status} - transition not available"
        except Exception as e:
            return f"Error transitioning: {str(e)}"
