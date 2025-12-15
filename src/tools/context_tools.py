"""
Context tools for gathering information for LLM prompts.
"""

from typing import Optional
from ..services.jira_client import JiraClient
from ..state.simulation_state import SimulationState


class ContextTools:
    """Tools for gathering context for LLM-generated content."""

    def __init__(self, jira_client: JiraClient):
        self.jira = jira_client

    def get_ticket_context(self, issue_key: str) -> dict:
        """Get full context for a ticket including comments."""
        try:
            issue = self.jira.get_issue(issue_key)
            comments = self.jira.get_comments(issue_key, max_results=5)

            return {
                "key": issue.key,
                "summary": issue.fields.summary,
                "description": issue.fields.description or "",
                "status": issue.fields.status.name,
                "type": issue.fields.issuetype.name,
                "assignee": issue.fields.assignee.displayName if issue.fields.assignee else None,
                "priority": issue.fields.priority.name if issue.fields.priority else None,
                "comments": [
                    {
                        "author": c.author.displayName,
                        "body": c.body,
                    }
                    for c in comments
                ],
            }
        except Exception as e:
            return {"error": str(e)}

    def get_project_summary(self) -> dict:
        """Get summary of current project state."""
        try:
            # Count issues by status
            statuses = {}
            all_issues = self.jira.get_project_issues(max_results=100)

            for issue in all_issues:
                status = issue.fields.status.name
                statuses[status] = statuses.get(status, 0) + 1

            # Get recent activity
            recent = self.jira.get_project_issues(max_results=5)
            recent_summaries = [i.fields.summary for i in recent]

            return {
                "total_issues": len(all_issues),
                "by_status": statuses,
                "recent_activity": recent_summaries,
            }
        except Exception as e:
            return {"error": str(e)}

    def get_team_workload(self, team: str, personas: dict) -> dict:
        """Get workload for a specific team."""
        team_agents = [
            config for aid, config in personas.get("agents", {}).items()
            if config.get("team") == team
        ]

        workload = {}
        for agent in team_agents:
            account_id = agent.get("jira_account_id")
            if account_id:
                try:
                    assigned = self.jira.get_in_progress_issues(assignee=account_id)
                    workload[agent.get("display_name")] = len(assigned)
                except Exception:
                    workload[agent.get("display_name")] = 0

        return workload

    def get_blocked_tickets(self) -> list[dict]:
        """Get tickets that are currently blocked."""
        try:
            # Look for tickets with blocker comments or blocked status
            jql = f"""
                project = {self.jira.project_key}
                AND (status = Blocked OR labels = blocked)
                ORDER BY updated DESC
            """
            issues = self.jira._client.search_issues(jql, maxResults=10)

            return [
                {
                    "key": i.key,
                    "summary": i.fields.summary,
                    "assignee": i.fields.assignee.displayName if i.fields.assignee else None,
                }
                for i in issues
            ]
        except Exception:
            return []
