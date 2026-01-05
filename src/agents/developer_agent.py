"""
Developer agent.
Picks up tasks, transitions statuses, adds comments, logs work.
"""

import logging
import random
from typing import Optional

logger = logging.getLogger(__name__)

from .base_agent import BaseAgent
from ..state.simulation_state import SimulationState

# Issue types that developers can work on (excludes Epics which are PM-only)
DEVELOPER_ALLOWED_ISSUE_TYPES = ["Story", "Bug", "Task"]


class DeveloperAgent(BaseAgent):
    """Developer agent - does the actual work."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seniority = self.config.get("seniority", "mid")
        self.error_rate = self.config.get("error_rate", 0.0)

    async def select_action(self, state: SimulationState) -> Optional[dict]:
        """Select a developer-appropriate action."""
        actions = []

        # Get my current assignments (filtered to allowed issue types - no Epics)
        my_tickets = []
        try:
            in_progress = self.jira.get_in_progress_issues(
                issue_types=DEVELOPER_ALLOWED_ISSUE_TYPES
            )
            my_tickets = [
                i for i in in_progress
                if i.fields.assignee and i.fields.assignee.accountId == self.jira_account_id
            ]
        except Exception as e:
            logger.warning(f"Failed to get in-progress issues for {self.agent_id}: {e}")

        # Get backlog items I could pick up (filtered to allowed issue types - no Epics)
        backlog = self.jira.get_backlog_issues(
            max_results=15,
            issue_types=DEVELOPER_ALLOWED_ISSUE_TYPES
        )

        workload = state.get_agent_workload(self.agent_id)

        # If I have work in progress, likely continue it
        if my_tickets:
            ticket = random.choice(my_tickets)
            ticket_state = state.active_tickets.get(ticket.key)

            # Progress the ticket
            actions.append({
                "type": "transition_to_review",
                "ticket": ticket.key,
                "weight": 3 if self.seniority == "senior" else 2,
            })

            # Add progress comment
            actions.append({
                "type": "progress_comment",
                "ticket": ticket.key,
                "weight": 2,
            })

            # Log work
            actions.append({
                "type": "log_work",
                "ticket": ticket.key,
                "weight": 2,
            })

        # If low workload, pick up new work
        if workload < 3 and backlog:
            # Filter to appropriate complexity for seniority
            suitable = backlog
            if self.seniority == "junior":
                # Junior takes simpler items
                suitable = [b for b in backlog if "complex" not in (b.fields.summary or "").lower()]

            if suitable:
                actions.append({
                    "type": "pick_up_task",
                    "ticket": random.choice(suitable).key,
                    "weight": 2,
                })

        # Could ask a question (more likely for junior)
        if my_tickets and self.seniority in ["junior", "mid"]:
            actions.append({
                "type": "ask_question",
                "ticket": random.choice(my_tickets).key,
                "weight": 2 if self.seniority == "junior" else 1,
            })

        if not actions:
            return None

        # Weighted random selection
        total_weight = sum(a.get("weight", 1) for a in actions)
        r = random.uniform(0, total_weight)
        cumulative = 0
        for action in actions:
            cumulative += action.get("weight", 1)
            if r <= cumulative:
                return action

        return actions[0]

    async def execute_action(self, action: dict, state: SimulationState) -> dict:
        """Execute the selected developer action."""
        action_type = action.get("type")

        if action_type == "pick_up_task":
            return await self._pick_up_task(action.get("ticket"), state)

        elif action_type == "transition_to_review":
            return await self._transition_to_review(action.get("ticket"), state)

        elif action_type == "progress_comment":
            return await self._add_progress_comment(action.get("ticket"), state)

        elif action_type == "log_work":
            result = self.log_work_time(action.get("ticket"))
            return result or {"action": "log_work", "status": "failed", "agent": self.display_name}

        elif action_type == "ask_question":
            return await self._ask_question(action.get("ticket"), state)

        return {"action": action_type, "status": "unknown_action", "agent": self.display_name}

    async def _pick_up_task(self, ticket_key: str, state: SimulationState) -> dict:
        """Assign a task to self and start working."""
        # Assign to self
        self.jira.assign_issue(ticket_key, self.jira_account_id)

        # Transition to In Progress
        self.jira.transition_issue(ticket_key, "In Progress")

        # Add comment
        comment = self.pick_random_template("status_transitions", "to_in_progress")
        if not comment:
            comment = "Starting work on this."
        self.jira.add_comment(ticket_key, comment)

        # Track in state
        state.track_ticket(ticket_key, "In Progress", self.agent_id)
        agent_state = state.get_agent_state(self.agent_id)
        agent_state.assigned_tickets.append(ticket_key)

        return {
            "action": "pick_up_task",
            "ticket": ticket_key,
            "agent": self.display_name,
        }

    async def _transition_to_review(self, ticket_key: str, state: SimulationState) -> dict:
        """Move ticket to code review."""
        # Check for junior error rate
        if self.error_rate > 0 and random.random() < self.error_rate:
            # Junior makes mistake - ticket will need rework
            # For now just add a comment indicating uncertainty
            comment = self.llm.generate_comment(
                agent_name=self.display_name,
                agent_role="Developer",
                agent_persona=self.persona,
                ticket_key=ticket_key,
                ticket_summary="",
                ticket_description="",
                recent_comments=[],
                action_context="Finished implementation but not 100% sure about edge cases",
                action_type="uncertain_completion",
            )
            self.jira.add_comment(ticket_key, comment)

        # Transition to review
        success = self.jira.transition_issue(ticket_key, "Code Review")
        if not success:
            success = self.jira.transition_issue(ticket_key, "In Review")

        if success:
            comment = self.pick_random_template("status_transitions", "to_code_review")
            if comment:
                self.jira.add_comment(ticket_key, comment)
            state.track_ticket(ticket_key, "Code Review", self.agent_id)

        return {
            "action": "transition_to_review",
            "ticket": ticket_key,
            "success": success,
            "agent": self.display_name,
        }

    async def _add_progress_comment(self, ticket_key: str, state: SimulationState) -> dict:
        """Add a progress update comment."""
        issue = self.jira.get_issue(ticket_key)
        comments = self.jira.get_comments(ticket_key, max_results=3)
        recent_comments = [c.body for c in comments]

        comment = self.llm.generate_comment(
            agent_name=self.display_name,
            agent_role="Developer",
            agent_persona=self.persona,
            ticket_key=ticket_key,
            ticket_summary=issue.fields.summary,
            ticket_description=issue.fields.description,
            recent_comments=recent_comments,
            action_context="Providing a progress update on implementation",
            action_type="progress_update",
        )

        self.jira.add_comment(ticket_key, comment)

        return {
            "action": "progress_comment",
            "ticket": ticket_key,
            "agent": self.display_name,
        }

    async def _ask_question(self, ticket_key: str, state: SimulationState) -> dict:
        """Ask a clarifying question."""
        issue = self.jira.get_issue(ticket_key)

        comment = self.llm.generate_comment(
            agent_name=self.display_name,
            agent_role="Developer",
            agent_persona=self.persona,
            ticket_key=ticket_key,
            ticket_summary=issue.fields.summary,
            ticket_description=issue.fields.description,
            recent_comments=[],
            action_context="Need clarification on requirements or implementation approach",
            action_type="question",
        )

        self.jira.add_comment(ticket_key, comment)

        return {
            "action": "ask_question",
            "ticket": ticket_key,
            "agent": self.display_name,
        }
