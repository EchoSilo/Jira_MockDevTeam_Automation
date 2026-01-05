"""
Tech Lead agent.
Reviews technical approaches, flags blockers, provides architectural guidance.
"""

import logging
import random
from typing import Optional

logger = logging.getLogger(__name__)

from .base_agent import BaseAgent
from ..state.simulation_state import SimulationState

# Issue types that tech leads can work on (excludes Epics which are PM-only)
TECH_LEAD_ALLOWED_ISSUE_TYPES = ["Story", "Bug", "Task"]


class TechLeadAgent(BaseAgent):
    """Tech Lead agent - technical oversight and guidance."""

    async def select_action(self, state: SimulationState) -> Optional[dict]:
        """Select a tech lead appropriate action."""
        actions = []

        # Get items in code review (filtered to allowed issue types - no Epics)
        in_review = []
        try:
            in_review = self.jira.get_project_issues(
                statuses=["Code Review", "In Review"],
                issue_types=TECH_LEAD_ALLOWED_ISSUE_TYPES,
                max_results=10,
            )
        except Exception as e:
            logger.warning(f"Failed to get code review items for {self.agent_id}: {e}")

        # Get items in progress (for architectural review, filtered - no Epics)
        in_progress = self.jira.get_in_progress_issues(
            issue_types=TECH_LEAD_ALLOWED_ISSUE_TYPES
        )

        # Review code
        if in_review:
            # Filter to own team if possible
            team_items = [i for i in in_review]  # Could filter by labels/components
            if team_items:
                actions.append({
                    "type": "code_review_comment",
                    "ticket": random.choice(team_items).key,
                    "weight": 3,
                })

        # Architectural guidance on in-progress items
        if in_progress:
            actions.append({
                "type": "architectural_comment",
                "ticket": random.choice(in_progress).key,
                "weight": 2,
            })

        # Flag potential blockers
        if in_progress and random.random() < 0.2:
            actions.append({
                "type": "flag_blocker",
                "ticket": random.choice(in_progress).key,
                "weight": 1,
            })

        # Technical notes on backlog items (filtered - no Epics)
        backlog = self.jira.get_backlog_issues(
            max_results=10,
            issue_types=TECH_LEAD_ALLOWED_ISSUE_TYPES
        )
        if backlog:
            actions.append({
                "type": "add_technical_notes",
                "ticket": random.choice(backlog).key,
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
        """Execute the selected tech lead action."""
        action_type = action.get("type")

        if action_type == "code_review_comment":
            return await self._code_review_comment(action.get("ticket"), state)

        elif action_type == "architectural_comment":
            return await self._architectural_comment(action.get("ticket"), state)

        elif action_type == "flag_blocker":
            return await self._flag_blocker(action.get("ticket"), state)

        elif action_type == "add_technical_notes":
            return await self._add_technical_notes(action.get("ticket"), state)

        return {"action": action_type, "status": "unknown_action", "agent": self.display_name}

    async def _code_review_comment(self, ticket_key: str, state: SimulationState) -> dict:
        """Add code review feedback."""
        issue = self.jira.get_issue(ticket_key)

        comment = self.llm.generate_technical_comment(
            agent_name=self.display_name,
            agent_role="Tech Lead",
            agent_persona=self.persona,
            ticket_key=ticket_key,
            ticket_summary=issue.fields.summary,
            ticket_description=issue.fields.description,
            comment_type="code_review",
        )

        self.jira.add_comment(ticket_key, comment)

        # Approve and move forward (most reviews pass)
        if random.random() < 0.85:
            success = self.jira.transition_issue(ticket_key, "Ready for QA")
            if not success:
                self.jira.transition_issue(ticket_key, "Testing")
            state.track_ticket(ticket_key, "Ready for QA")

            # Unassign review from self now that review is complete
            agent_state = state.get_agent_state(self.agent_id)
            if agent_state:
                agent_state.unassign_review(ticket_key)
                logger.info(f"Completed code review for {ticket_key}, unassigned from review queue")

        return {
            "action": "code_review_comment",
            "ticket": ticket_key,
            "agent": self.display_name,
        }

    async def _architectural_comment(self, ticket_key: str, state: SimulationState) -> dict:
        """Add architectural guidance."""
        issue = self.jira.get_issue(ticket_key)

        comment = self.llm.generate_technical_comment(
            agent_name=self.display_name,
            agent_role="Tech Lead",
            agent_persona=self.persona,
            ticket_key=ticket_key,
            ticket_summary=issue.fields.summary,
            ticket_description=issue.fields.description,
            comment_type="architectural",
        )

        self.jira.add_comment(ticket_key, comment)

        return {
            "action": "architectural_comment",
            "ticket": ticket_key,
            "agent": self.display_name,
        }

    async def _flag_blocker(self, ticket_key: str, state: SimulationState) -> dict:
        """Flag a potential blocker."""
        issue = self.jira.get_issue(ticket_key)

        comment = self.llm.generate_technical_comment(
            agent_name=self.display_name,
            agent_role="Tech Lead",
            agent_persona=self.persona,
            ticket_key=ticket_key,
            ticket_summary=issue.fields.summary,
            ticket_description=issue.fields.description,
            comment_type="blocker",
        )

        self.jira.add_comment(ticket_key, f"⚠️ **Potential Blocker:**\n{comment}")

        # Update state
        if ticket_key in state.active_tickets:
            state.active_tickets[ticket_key].blocked = True

        return {
            "action": "flag_blocker",
            "ticket": ticket_key,
            "agent": self.display_name,
        }

    async def _add_technical_notes(self, ticket_key: str, state: SimulationState) -> dict:
        """Add technical notes to a backlog item."""
        issue = self.jira.get_issue(ticket_key)

        comment = self.llm.generate_technical_comment(
            agent_name=self.display_name,
            agent_role="Tech Lead",
            agent_persona=self.persona,
            ticket_key=ticket_key,
            ticket_summary=issue.fields.summary,
            ticket_description=issue.fields.description,
            comment_type="design",
        )

        self.jira.add_comment(ticket_key, f"**Technical Notes:**\n{comment}")

        return {
            "action": "add_technical_notes",
            "ticket": ticket_key,
            "agent": self.display_name,
        }
