"""
QA Engineer agent.
Tests tickets, approves or rejects, creates bugs.
"""

import logging
import random
from typing import Optional

logger = logging.getLogger(__name__)

from .base_agent import BaseAgent
from ..state.simulation_state import SimulationState

# Issue types that QA can work on (excludes Epics which are PM-only)
QA_ALLOWED_ISSUE_TYPES = ["Story", "Bug", "Task"]


class QAAgent(BaseAgent):
    """QA Engineer agent - tests and validates work."""

    async def select_action(self, state: SimulationState) -> Optional[dict]:
        """Select a QA-appropriate action."""
        actions = []

        # First, check tickets assigned to this QA in state
        agent_state = state.get_agent_state(self.agent_id)
        assigned_tickets = agent_state.assigned_tickets if agent_state else []

        # Get tickets ready for testing from Jira (filtered to allowed issue types)
        ready_for_qa = self.jira.get_issues_ready_for_testing(
            issue_types=QA_ALLOWED_ISSUE_TYPES
        )

        # Prioritize tickets that are both assigned to us AND ready for testing
        if assigned_tickets and ready_for_qa:
            # Filter to tickets we're assigned to
            ready_keys = {t.key for t in ready_for_qa}
            my_tickets = [t for t in ready_for_qa if t.key in assigned_tickets]
            if my_tickets:
                ready_for_qa = my_tickets  # Only work on our assigned tickets

        if ready_for_qa:
            ticket = random.choice(ready_for_qa)

            # Decide: approve, reject, or add test scenarios
            # Most tickets pass, some get rejected
            if random.random() < 0.75:
                actions.append({
                    "type": "approve_ticket",
                    "ticket": ticket.key,
                    "weight": 3,
                })
            else:
                actions.append({
                    "type": "reject_ticket",
                    "ticket": ticket.key,
                    "weight": 3,
                })

            # Could also add test scenarios
            actions.append({
                "type": "add_test_scenarios",
                "ticket": ticket.key,
                "weight": 1,
            })

        # Could create a bug from testing
        if ready_for_qa and random.random() < 0.15:
            actions.append({
                "type": "create_bug",
                "related_ticket": random.choice(ready_for_qa).key,
                "weight": 1,
            })

        # Log testing work
        if ready_for_qa:
            actions.append({
                "type": "log_work",
                "ticket": random.choice(ready_for_qa).key,
                "weight": 1,
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
        """Execute the selected QA action."""
        action_type = action.get("type")

        if action_type == "approve_ticket":
            return await self._approve_ticket(action.get("ticket"), state)

        elif action_type == "reject_ticket":
            return await self._reject_ticket(action.get("ticket"), state)

        elif action_type == "add_test_scenarios":
            return await self._add_test_scenarios(action.get("ticket"), state)

        elif action_type == "create_bug":
            return await self._create_bug(action.get("related_ticket"), state)

        elif action_type == "log_work":
            result = self.log_work_time(action.get("ticket"))
            return result or {"action": "log_work", "status": "failed", "agent": self.display_name}

        return {"action": action_type, "status": "unknown_action", "agent": self.display_name}

    async def _approve_ticket(self, ticket_key: str, state: SimulationState) -> dict:
        """Approve a ticket after testing."""
        # Transition to Done
        success = self.jira.transition_issue(ticket_key, "Done")
        if not success:
            success = self.jira.transition_issue(ticket_key, "Closed")

        # Add approval comment
        comment = self.pick_random_template("qa_actions", "approved")
        if not comment:
            issue = self.jira.get_issue(ticket_key)
            comment = self.llm.generate_comment(
                agent_name=self.display_name,
                agent_role="QA Engineer",
                agent_persona=self.persona,
                ticket_key=ticket_key,
                ticket_summary=issue.fields.summary,
                ticket_description=issue.fields.description,
                recent_comments=[],
                action_context="Tested and verified - all acceptance criteria met",
                action_type="qa_approval",
            )

        self.jira.add_comment(ticket_key, comment)

        if success:
            state.track_ticket(ticket_key, "Done")

        return {
            "action": "approve_ticket",
            "ticket": ticket_key,
            "success": success,
            "agent": self.display_name,
        }

    async def _reject_ticket(self, ticket_key: str, state: SimulationState) -> dict:
        """Reject a ticket - needs rework."""
        issue = self.jira.get_issue(ticket_key)

        # Generate rejection reason
        comment = self.llm.generate_comment(
            agent_name=self.display_name,
            agent_role="QA Engineer",
            agent_persona=self.persona,
            ticket_key=ticket_key,
            ticket_summary=issue.fields.summary,
            ticket_description=issue.fields.description,
            recent_comments=[],
            action_context="Found an issue during testing that needs to be fixed",
            action_type="qa_rejection",
        )

        # Transition back to In Progress
        success = self.jira.transition_issue(ticket_key, "In Progress")
        if not success:
            success = self.jira.transition_issue(ticket_key, "To Do")

        # Add rejection comment
        rejection_prefix = self.pick_random_template("qa_actions", "rejected")
        full_comment = f"{rejection_prefix}\n\n{comment}" if rejection_prefix else comment
        self.jira.add_comment(ticket_key, full_comment)

        if success:
            state.track_ticket(ticket_key, "In Progress")

        return {
            "action": "reject_ticket",
            "ticket": ticket_key,
            "success": success,
            "agent": self.display_name,
        }

    async def _add_test_scenarios(self, ticket_key: str, state: SimulationState) -> dict:
        """Add test scenarios to a ticket."""
        issue = self.jira.get_issue(ticket_key)

        comment = self.llm.generate_comment(
            agent_name=self.display_name,
            agent_role="QA Engineer",
            agent_persona=self.persona,
            ticket_key=ticket_key,
            ticket_summary=issue.fields.summary,
            ticket_description=issue.fields.description,
            recent_comments=[],
            action_context="Documenting test scenarios and edge cases to verify",
            action_type="test_scenarios",
        )

        self.jira.add_comment(ticket_key, f"**Test Scenarios:**\n{comment}")

        return {
            "action": "add_test_scenarios",
            "ticket": ticket_key,
            "agent": self.display_name,
        }

    async def _create_bug(self, related_ticket_key: str, state: SimulationState) -> dict:
        """Create a bug found during testing."""
        related_issue = self.jira.get_issue(related_ticket_key)

        # Generate bug via LLM
        bug_data = self.llm.generate_bug_report(
            agent_name=self.display_name,
            agent_persona=self.persona,
            related_ticket={
                "summary": related_issue.fields.summary,
                "description": related_issue.fields.description,
            },
        )

        # Create bug in Jira
        bug = self.jira.create_issue(
            summary=bug_data["summary"],
            description=bug_data["description"],
            issue_type="Bug",
            priority=bug_data.get("priority", "High"),
        )

        # Link to original ticket
        try:
            self.jira.link_issues(bug.key, related_ticket_key, "is caused by")
        except Exception as e:
            logger.warning(f"Failed to link bug {bug.key} to {related_ticket_key}: {e}")

        # Track in state
        state.track_ticket(bug.key, "To Do")

        return {
            "action": "create_bug",
            "ticket": bug.key,
            "related_to": related_ticket_key,
            "agent": self.display_name,
        }
