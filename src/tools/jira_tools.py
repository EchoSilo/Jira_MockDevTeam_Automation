"""
CrewAI tools for Jira operations.

These tools wrap the JiraClient for use by CrewAI agents.
Each tool is decorated with @tool and has clear descriptions
for the LLM to understand when and how to use them.
"""

from typing import Optional
from crewai.tools import tool

from ..services.jira_client import JiraClient


class JiraTools:
    """
    Collection of Jira tools for CrewAI agents.

    Tools are organized by role - different agent types get different tool sets.
    All tools share a single JiraClient instance for consistent authentication.
    """

    def __init__(self, jira_client: JiraClient):
        self.jira = jira_client
        self._create_tools()

    def _create_tools(self) -> None:
        """Create tool instances bound to this JiraClient."""
        # We need to create closures that capture self.jira

        jira = self.jira  # Capture for closures

        @tool("Search Jira Issues")
        def search_issues(query: str) -> str:
            """
            Search for Jira issues using JQL or text search.

            Args:
                query: JQL query (e.g., 'status = "In Progress"') or text to search

            Returns:
                List of matching issues with key, summary, status, and assignee
            """
            try:
                if "=" in query or "AND" in query or "OR" in query:
                    issues = jira._client.search_issues(query, maxResults=10)
                else:
                    jql = f'project = {jira.project_key} AND text ~ "{query}"'
                    issues = jira._client.search_issues(jql, maxResults=10)

                if not issues:
                    return "No issues found"

                results = []
                for issue in issues:
                    assignee = issue.fields.assignee
                    assignee_name = assignee.displayName if assignee else "Unassigned"
                    results.append(
                        f"- {issue.key}: {issue.fields.summary} "
                        f"[{issue.fields.status.name}] (Assignee: {assignee_name})"
                    )
                return "\n".join(results)
            except Exception as e:
                return f"Error searching: {str(e)}"

        @tool("Get Issue Details")
        def get_issue_details(issue_key: str) -> str:
            """
            Get detailed information about a specific Jira issue.

            Args:
                issue_key: The Jira issue key (e.g., PROJ-123)

            Returns:
                Issue details including summary, description, status, assignee, priority
            """
            try:
                issue = jira.get_issue(issue_key)
                assignee = issue.fields.assignee
                assignee_name = assignee.displayName if assignee else "Unassigned"

                return f"""Issue: {issue.key}
Summary: {issue.fields.summary}
Type: {issue.fields.issuetype.name}
Status: {issue.fields.status.name}
Priority: {issue.fields.priority.name if issue.fields.priority else 'None'}
Assignee: {assignee_name}

Description:
{issue.fields.description or 'No description'}"""
            except Exception as e:
                return f"Error getting issue: {str(e)}"

        @tool("Add Comment to Issue")
        def add_comment(issue_key: str, comment: str) -> str:
            """
            Add a comment to a Jira issue.

            Args:
                issue_key: The Jira issue key (e.g., PROJ-123)
                comment: The comment text to add

            Returns:
                Confirmation message
            """
            try:
                jira.add_comment(issue_key, comment)
                return f"Comment added to {issue_key}"
            except Exception as e:
                return f"Error adding comment: {str(e)}"

        @tool("Transition Issue Status")
        def transition_issue(issue_key: str, new_status: str) -> str:
            """
            Change the status of a Jira issue.

            Args:
                issue_key: The Jira issue key (e.g., PROJ-123)
                new_status: Target status name (e.g., 'In Progress', 'Code Review', 'Done')

            Returns:
                Confirmation or error message
            """
            try:
                success = jira.transition_issue(issue_key, new_status)
                if success:
                    return f"Transitioned {issue_key} to '{new_status}'"
                else:
                    # Get available transitions
                    available = jira.get_transitions(issue_key)
                    trans_names = [t["name"] for t in available]
                    return f"Could not transition to '{new_status}'. Available transitions: {trans_names}"
            except Exception as e:
                return f"Error transitioning: {str(e)}"

        @tool("Assign Issue to User")
        def assign_issue(issue_key: str, account_id: str) -> str:
            """
            Assign a Jira issue to a user.

            Args:
                issue_key: The Jira issue key (e.g., PROJ-123)
                account_id: The Jira account ID of the assignee

            Returns:
                Confirmation message
            """
            try:
                jira.assign_issue(issue_key, account_id)
                return f"Assigned {issue_key} to account {account_id}"
            except Exception as e:
                return f"Error assigning: {str(e)}"

        @tool("Log Work Time")
        def log_work(issue_key: str, time_spent: str, work_description: str = "") -> str:
            """
            Log work time on a Jira issue.

            Args:
                issue_key: The Jira issue key (e.g., PROJ-123)
                time_spent: Time in Jira format (e.g., '30m', '1h', '2h 30m')
                work_description: Optional description of work done

            Returns:
                Confirmation message
            """
            try:
                jira.log_work(issue_key, time_spent, work_description or None)
                return f"Logged {time_spent} on {issue_key}"
            except Exception as e:
                return f"Error logging work: {str(e)}"

        @tool("Create New Issue")
        def create_issue(
            summary: str,
            description: str,
            issue_type: str = "Story",
            priority: str = "Medium"
        ) -> str:
            """
            Create a new Jira issue.

            Args:
                summary: Brief title for the issue
                description: Detailed description with acceptance criteria
                issue_type: Type of issue ('Story', 'Bug', 'Task', 'Epic')
                priority: Priority level ('Highest', 'High', 'Medium', 'Low', 'Lowest')

            Returns:
                The key of the created issue
            """
            try:
                issue = jira.create_issue(
                    summary=summary,
                    description=description,
                    issue_type=issue_type,
                    priority=priority,
                )
                return f"Created {issue.key}: {summary}"
            except Exception as e:
                return f"Error creating issue: {str(e)}"

        @tool("Get Backlog Issues")
        def get_backlog() -> str:
            """
            Get issues in the backlog (To Do status, not in sprint).

            Returns:
                List of backlog issues with key, summary, and priority
            """
            try:
                issues = jira.get_backlog_issues(max_results=15)
                if not issues:
                    return "Backlog is empty"

                results = []
                for issue in issues:
                    priority = issue.fields.priority.name if issue.fields.priority else "None"
                    results.append(f"- {issue.key}: {issue.fields.summary} [Priority: {priority}]")
                return f"Backlog ({len(issues)} items):\n" + "\n".join(results)
            except Exception as e:
                return f"Error getting backlog: {str(e)}"

        @tool("Get In Progress Issues")
        def get_in_progress() -> str:
            """
            Get issues currently in progress.

            Returns:
                List of in-progress issues with key, summary, and assignee
            """
            try:
                issues = jira.get_in_progress_issues()
                if not issues:
                    return "No issues in progress"

                results = []
                for issue in issues:
                    assignee = issue.fields.assignee
                    assignee_name = assignee.displayName if assignee else "Unassigned"
                    results.append(f"- {issue.key}: {issue.fields.summary} (Assignee: {assignee_name})")
                return f"In Progress ({len(issues)} items):\n" + "\n".join(results)
            except Exception as e:
                return f"Error getting in-progress issues: {str(e)}"

        @tool("Get Issues Ready for Testing")
        def get_ready_for_qa() -> str:
            """
            Get issues that are ready for QA testing.

            Returns:
                List of issues awaiting QA with key, summary, and assignee
            """
            try:
                issues = jira.get_issues_ready_for_testing()
                if not issues:
                    return "No issues ready for testing"

                results = []
                for issue in issues:
                    assignee = issue.fields.assignee
                    assignee_name = assignee.displayName if assignee else "Unassigned"
                    results.append(f"- {issue.key}: {issue.fields.summary} (Developer: {assignee_name})")
                return f"Ready for QA ({len(issues)} items):\n" + "\n".join(results)
            except Exception as e:
                return f"Error getting QA queue: {str(e)}"

        @tool("Link Issues")
        def link_issues(from_issue: str, to_issue: str, link_type: str = "Blocks") -> str:
            """
            Create a link between two Jira issues.

            Args:
                from_issue: Source issue key
                to_issue: Target issue key
                link_type: Type of link ('Blocks', 'is blocked by', 'relates to', 'is caused by')

            Returns:
                Confirmation message
            """
            try:
                jira.link_issues(from_issue, to_issue, link_type)
                return f"Linked {from_issue} -> {to_issue} ({link_type})"
            except Exception as e:
                return f"Error linking issues: {str(e)}"

        @tool("Get Issue Comments")
        def get_comments(issue_key: str) -> str:
            """
            Get recent comments on a Jira issue.

            Args:
                issue_key: The Jira issue key

            Returns:
                List of recent comments with author and text
            """
            try:
                comments = jira.get_comments(issue_key, max_results=5)
                if not comments:
                    return f"No comments on {issue_key}"

                results = []
                for c in comments:
                    author = c.author.displayName if hasattr(c, 'author') else "Unknown"
                    body = c.body[:200] + "..." if len(c.body) > 200 else c.body
                    results.append(f"[{author}]: {body}")
                return f"Recent comments on {issue_key}:\n" + "\n\n".join(results)
            except Exception as e:
                return f"Error getting comments: {str(e)}"

        # Store tool references
        self._search_issues = search_issues
        self._get_issue_details = get_issue_details
        self._add_comment = add_comment
        self._transition_issue = transition_issue
        self._assign_issue = assign_issue
        self._log_work = log_work
        self._create_issue = create_issue
        self._get_backlog = get_backlog
        self._get_in_progress = get_in_progress
        self._get_ready_for_qa = get_ready_for_qa
        self._link_issues = link_issues
        self._get_comments = get_comments

    # ============ Tool Sets by Role ============

    def get_all_tools(self) -> list:
        """Get all available Jira tools."""
        return [
            self._search_issues,
            self._get_issue_details,
            self._add_comment,
            self._transition_issue,
            self._assign_issue,
            self._log_work,
            self._create_issue,
            self._get_backlog,
            self._get_in_progress,
            self._get_ready_for_qa,
            self._link_issues,
            self._get_comments,
        ]

    def get_pm_tools(self) -> list:
        """Get tools appropriate for PM agents."""
        return [
            self._search_issues,
            self._get_issue_details,
            self._add_comment,
            self._create_issue,
            self._get_backlog,
            self._get_in_progress,
            self._get_comments,
        ]

    def get_developer_tools(self) -> list:
        """Get tools appropriate for Developer agents."""
        return [
            self._search_issues,
            self._get_issue_details,
            self._add_comment,
            self._transition_issue,
            self._assign_issue,
            self._log_work,
            self._get_backlog,
            self._get_in_progress,
            self._get_comments,
        ]

    def get_qa_tools(self) -> list:
        """Get tools appropriate for QA agents."""
        return [
            self._search_issues,
            self._get_issue_details,
            self._add_comment,
            self._transition_issue,
            self._log_work,
            self._create_issue,  # For bug creation
            self._get_ready_for_qa,
            self._link_issues,
            self._get_comments,
        ]

    def get_tech_lead_tools(self) -> list:
        """Get tools appropriate for Tech Lead agents."""
        return [
            self._search_issues,
            self._get_issue_details,
            self._add_comment,
            self._transition_issue,
            self._get_backlog,
            self._get_in_progress,
            self._get_ready_for_qa,
            self._get_comments,
        ]

    def get_tools_for_role(self, role: str) -> list:
        """Get appropriate tools for a given role."""
        role_tools = {
            "pm": self.get_pm_tools,
            "developer": self.get_developer_tools,
            "qa": self.get_qa_tools,
            "tech_lead": self.get_tech_lead_tools,
        }
        getter = role_tools.get(role, self.get_all_tools)
        return getter()

    # ============ Legacy Compatibility ============

    def get_tools(self) -> list:
        """Legacy method - returns all tools."""
        return self.get_all_tools()
