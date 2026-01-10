"""
CrewAI tools for Jira operations.

These tools wrap the JiraClient for use by CrewAI agents.
Each tool is decorated with @tool and has clear descriptions
for the LLM to understand when and how to use them.
"""

import time
from typing import Optional, TYPE_CHECKING
from crewai.tools import tool

from ..services.jira_client import JiraClient

if TYPE_CHECKING:
    from ..logging import AsyncLogWriter


class JiraTools:
    """
    Collection of Jira tools for CrewAI agents.

    Tools are organized by role - different agent types get different tool sets.
    All tools share a single JiraClient instance for consistent authentication.
    """

    def __init__(
        self,
        jira_client: JiraClient,
        log_writer: "AsyncLogWriter | None" = None,
    ):
        self.jira = jira_client
        self.log_writer = log_writer
        self._current_agent_id: str | None = None
        self._current_ticket_key: str | None = None
        self._create_tools()

    def set_context(
        self,
        agent_id: str | None = None,
        ticket_key: str | None = None,
    ) -> None:
        """Set context for logging Jira calls."""
        self._current_agent_id = agent_id
        self._current_ticket_key = ticket_key

    def clear_context(self) -> None:
        """Clear the logging context."""
        self._current_agent_id = None
        self._current_ticket_key = None

    def _log_jira_call(
        self,
        method: str,
        parameters: dict,
        response: str,
        duration_ms: int,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        """Log a Jira API call if log_writer is available."""
        if not self.log_writer:
            return

        # Extract ticket key from parameters if not set in context
        ticket_key = self._current_ticket_key
        if not ticket_key:
            ticket_key = parameters.get("issue_key") or parameters.get("ticket_key")

        self.log_writer.log_jira_call(
            method=method,
            parameters=parameters,
            response_summary=response if success else "",
            duration_ms=duration_ms,
            agent_id=self._current_agent_id,
            ticket_key=ticket_key,
            error=error if not success else None,
        )

    def _create_tools(self) -> None:
        """Create tool instances bound to this JiraClient."""
        # We need to create closures that capture self.jira and self for logging

        jira = self.jira  # Capture for closures
        tools_self = self  # Capture self for logging

        @tool("Search Jira Issues")
        def search_issues(query: str) -> str:
            """
            Search for Jira issues using JQL or text search.

            Args:
                query: JQL query (e.g., 'status = "In Progress"') or text to search

            Returns:
                List of matching issues with key, summary, status, and assignee
            """
            start_time = time.time()
            try:
                if "=" in query or "AND" in query or "OR" in query:
                    issues = jira._client.search_issues(query, maxResults=10)
                else:
                    jql = f'project = {jira.project_key} AND text ~ "{query}"'
                    issues = jira._client.search_issues(jql, maxResults=10)

                if not issues:
                    result = "No issues found"
                else:
                    results = []
                    for issue in issues:
                        assignee = issue.fields.assignee
                        assignee_name = assignee.displayName if assignee else "Unassigned"
                        results.append(
                            f"- {issue.key}: {issue.fields.summary} "
                            f"[{issue.fields.status.name}] (Assignee: {assignee_name})"
                        )
                    result = "\n".join(results)

                duration_ms = int((time.time() - start_time) * 1000)
                tools_self._log_jira_call(
                    "search_issues", {"query": query}, result, duration_ms
                )
                return result
            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                tools_self._log_jira_call(
                    "search_issues", {"query": query}, "",
                    duration_ms, success=False, error=str(e)
                )
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
            start_time = time.time()
            try:
                issue = jira.get_issue(issue_key)
                assignee = issue.fields.assignee
                assignee_name = assignee.displayName if assignee else "Unassigned"

                result = f"""Issue: {issue.key}
Summary: {issue.fields.summary}
Type: {issue.fields.issuetype.name}
Status: {issue.fields.status.name}
Priority: {issue.fields.priority.name if issue.fields.priority else 'None'}
Assignee: {assignee_name}

Description:
{issue.fields.description or 'No description'}"""

                duration_ms = int((time.time() - start_time) * 1000)
                tools_self._log_jira_call(
                    "get_issue", {"issue_key": issue_key}, result, duration_ms
                )
                return result
            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                tools_self._log_jira_call(
                    "get_issue", {"issue_key": issue_key}, "",
                    duration_ms, success=False, error=str(e)
                )
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
            start_time = time.time()
            try:
                jira.add_comment(issue_key, comment)
                result = f"Comment added to {issue_key}"
                duration_ms = int((time.time() - start_time) * 1000)
                tools_self._log_jira_call(
                    "add_comment",
                    {"issue_key": issue_key, "comment": comment[:200]},
                    result, duration_ms
                )
                return result
            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                tools_self._log_jira_call(
                    "add_comment",
                    {"issue_key": issue_key, "comment": comment[:200]},
                    "", duration_ms, success=False, error=str(e)
                )
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
            start_time = time.time()
            try:
                success = jira.transition_issue(issue_key, new_status)
                if success:
                    result = f"Transitioned {issue_key} to '{new_status}'"
                else:
                    # Get available transitions
                    available = jira.get_transitions(issue_key)
                    trans_names = [t["name"] for t in available]
                    result = f"Could not transition to '{new_status}'. Available: {trans_names}"

                duration_ms = int((time.time() - start_time) * 1000)
                tools_self._log_jira_call(
                    "transition_issue",
                    {"issue_key": issue_key, "new_status": new_status},
                    result, duration_ms, success=success
                )
                return result
            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                tools_self._log_jira_call(
                    "transition_issue",
                    {"issue_key": issue_key, "new_status": new_status},
                    "", duration_ms, success=False, error=str(e)
                )
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
            start_time = time.time()
            try:
                jira.assign_issue(issue_key, account_id)
                result = f"Assigned {issue_key} to account {account_id}"
                duration_ms = int((time.time() - start_time) * 1000)
                tools_self._log_jira_call(
                    "assign_issue",
                    {"issue_key": issue_key, "account_id": account_id},
                    result, duration_ms
                )
                return result
            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                tools_self._log_jira_call(
                    "assign_issue",
                    {"issue_key": issue_key, "account_id": account_id},
                    "", duration_ms, success=False, error=str(e)
                )
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

        # ============ Sprint Management Tools ============

        @tool("Get Active Sprint")
        def get_active_sprint() -> str:
            """
            Get information about the currently active sprint.

            Returns:
                Sprint details including ID, name, and dates
            """
            try:
                sprint = jira.get_active_sprint()
                if not sprint:
                    return "No active sprint found"

                return (
                    f"Active Sprint: {sprint['name']} (ID: {sprint['id']})\n"
                    f"State: {sprint['state']}\n"
                    f"Start: {sprint.get('start_date', 'Not set')}\n"
                    f"End: {sprint.get('end_date', 'Not set')}"
                )
            except Exception as e:
                return f"Error getting active sprint: {str(e)}"

        @tool("Get Future Sprints")
        def get_future_sprints() -> str:
            """
            Get upcoming/future sprints for planning.

            Returns:
                List of future sprints with IDs and names
            """
            try:
                sprints = jira.get_future_sprints(max_results=4)
                if not sprints:
                    return "No future sprints found"

                results = []
                for s in sprints:
                    results.append(
                        f"- {s['name']} (ID: {s['id']}) - {s['state']}"
                    )
                return f"Future Sprints ({len(sprints)}):\n" + "\n".join(results)
            except Exception as e:
                return f"Error getting future sprints: {str(e)}"

        @tool("Get Unplanned Items")
        def get_unplanned_items() -> str:
            """
            Get items in backlog not assigned to any sprint.

            Returns:
                List of items needing sprint assignment
            """
            try:
                issues = jira.get_issues_not_in_sprint(
                    issue_types=["Story", "Bug", "Task"]
                )
                if not issues:
                    return "All items are assigned to sprints"

                results = []
                for issue in issues[:15]:
                    priority = (
                        issue.fields.priority.name
                        if issue.fields.priority
                        else "Medium"
                    )
                    issue_type = issue.fields.issuetype.name
                    results.append(
                        f"- {issue.key}: {issue.fields.summary} "
                        f"[{issue_type}] Priority: {priority}"
                    )

                return (
                    f"Unplanned items ({len(issues)} total):\n" + "\n".join(results)
                )
            except Exception as e:
                return f"Error getting unplanned items: {str(e)}"

        @tool("Add Issue to Sprint")
        def add_to_sprint(issue_key: str, sprint_id: int) -> str:
            """
            Add an issue to a specific sprint.

            Args:
                issue_key: The Jira issue key (e.g., PROJ-123)
                sprint_id: The ID of the target sprint

            Returns:
                Confirmation message
            """
            try:
                success = jira.add_issue_to_sprint(sprint_id, [issue_key])
                if success:
                    return f"Added {issue_key} to sprint {sprint_id}"
                return f"Failed to add {issue_key} to sprint"
            except Exception as e:
                return f"Error adding to sprint: {str(e)}"

        @tool("Create Sprint")
        def create_sprint(name: str, start_date: str, end_date: str) -> str:
            """
            Create a new sprint on the board.

            Args:
                name: Sprint name (e.g., 'Sprint 5')
                start_date: Start date in ISO format (YYYY-MM-DD)
                end_date: End date in ISO format (YYYY-MM-DD)

            Returns:
                Confirmation with new sprint ID
            """
            try:
                from datetime import date as date_type
                start = date_type.fromisoformat(start_date)
                end = date_type.fromisoformat(end_date)

                sprint = jira.create_sprint(name, start_date=start, end_date=end)
                if sprint:
                    return (
                        f"Created sprint '{sprint['name']}' (ID: {sprint['id']})"
                    )
                return "Failed to create sprint"
            except Exception as e:
                return f"Error creating sprint: {str(e)}"

        @tool("Start Sprint")
        def start_sprint(sprint_id: int) -> str:
            """
            Activate a future sprint, making it the current active sprint.

            Args:
                sprint_id: The ID of the future sprint to activate

            Returns:
                Success or failure message

            Note: If another sprint is currently active, it will be automatically
            closed when the new sprint starts.
            """
            try:
                from datetime import date as date_type, timedelta

                # Get sprint info first to verify it exists
                future_sprints = jira.get_future_sprints()
                sprint_info = next(
                    (s for s in future_sprints if s["id"] == sprint_id), None
                )

                if not sprint_info:
                    return f"Sprint {sprint_id} not found or not in 'future' state"

                # Use today as start, 7 days from now as end
                start_date = date_type.today()
                end_date = start_date + timedelta(days=7)

                success, error = jira.start_sprint(
                    sprint_id, start_date=start_date, end_date=end_date
                )
                if success:
                    return f"Successfully activated sprint {sprint_id}"
                return f"Failed to activate sprint {sprint_id}: {error}"
            except Exception as e:
                return f"Error starting sprint: {str(e)}"

        @tool("Complete Sprint")
        def complete_sprint(sprint_id: int) -> str:
            """
            Complete the currently active sprint, closing it out.

            Args:
                sprint_id: The ID of the active sprint to complete

            Returns:
                Success or failure message
            """
            try:
                success, error = jira.complete_sprint(sprint_id)
                if success:
                    return f"Successfully completed sprint {sprint_id}"
                return f"Failed to complete sprint {sprint_id}: {error}"
            except Exception as e:
                return f"Error completing sprint: {str(e)}"

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
        # Sprint tools
        self._get_active_sprint = get_active_sprint
        self._get_future_sprints = get_future_sprints
        self._get_unplanned_items = get_unplanned_items
        self._add_to_sprint = add_to_sprint
        self._create_sprint = create_sprint
        self._start_sprint = start_sprint
        self._complete_sprint = complete_sprint

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
            # Sprint tools
            self._get_active_sprint,
            self._get_future_sprints,
            self._get_unplanned_items,
            self._add_to_sprint,
            self._create_sprint,
            self._start_sprint,
            self._complete_sprint,
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
            # Sprint planning tools for PMs
            self._get_active_sprint,
            self._get_future_sprints,
            self._get_unplanned_items,
            self._add_to_sprint,
            self._create_sprint,
            self._start_sprint,
            self._complete_sprint,
        ]

    def get_sprint_planning_tools(self) -> list:
        """Get tools for sprint planning activities."""
        return [
            self._get_active_sprint,
            self._get_future_sprints,
            self._get_unplanned_items,
            self._add_to_sprint,
            self._create_sprint,
            self._start_sprint,
            self._complete_sprint,
            self._get_backlog,
            self._add_comment,
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
