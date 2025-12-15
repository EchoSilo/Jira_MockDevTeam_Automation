"""
Product Manager agent.
Creates stories, prioritizes backlog, adds acceptance criteria.
"""

import random
from typing import Optional

from .base_agent import BaseAgent
from ..state.simulation_state import SimulationState


class PMAgent(BaseAgent):
    """Product Manager agent - creates and manages backlog."""

    async def select_action(self, state: SimulationState) -> Optional[dict]:
        """Select a PM-appropriate action."""
        actions = []

        # Get current project state from Jira
        backlog = self.jira.get_backlog_issues(max_results=20)
        in_progress = self.jira.get_in_progress_issues()

        # Possible actions based on state
        if len(backlog) < 10:
            # Backlog is thin, create new stories
            actions.append({"type": "create_story", "weight": 3})

        if backlog:
            # Could add acceptance criteria to existing stories
            stories_without_ac = [
                i for i in backlog
                if "acceptance criteria" not in (i.fields.description or "").lower()
            ]
            if stories_without_ac:
                actions.append({
                    "type": "add_acceptance_criteria",
                    "ticket": random.choice(stories_without_ac).key,
                    "weight": 2,
                })

        if in_progress:
            # Could comment on progress / blockers
            actions.append({
                "type": "comment_on_progress",
                "ticket": random.choice(in_progress).key,
                "weight": 1,
            })

        # Could prioritize / reorder backlog
        if len(backlog) > 5:
            actions.append({"type": "prioritize_backlog", "weight": 1})

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
        """Execute the selected PM action."""
        action_type = action.get("type")

        if action_type == "create_story":
            return await self._create_story(state)

        elif action_type == "add_acceptance_criteria":
            return await self._add_acceptance_criteria(action.get("ticket"), state)

        elif action_type == "comment_on_progress":
            return await self._comment_on_progress(action.get("ticket"), state)

        elif action_type == "prioritize_backlog":
            return await self._prioritize_comment(state)

        return {"action": action_type, "status": "unknown_action", "agent": self.display_name}

    async def _create_story(self, state: SimulationState) -> dict:
        """Create a new story in the backlog."""
        # Get context for LLM
        existing_epics = []
        try:
            epics = self.jira.get_project_issues(issue_types=["Epic"], max_results=10)
            existing_epics = [e.fields.summary for e in epics]
        except Exception:
            pass

        recent_stories = []
        try:
            stories = self.jira.get_project_issues(issue_types=["Story"], max_results=10)
            recent_stories = [s.fields.summary for s in stories]
        except Exception:
            pass

        # Get team focus from config
        team_config = self.config.get("team", "alpha")
        team_focus = "Core Platform" if team_config == "alpha" else "User Experience"

        # Generate story via LLM
        story_data = self.llm.generate_story(
            agent_name=self.display_name,
            agent_persona=self.persona,
            team_focus=team_focus,
            existing_epics=existing_epics,
            recent_stories=recent_stories,
        )

        # Create in Jira
        issue = self.jira.create_issue(
            summary=story_data["summary"],
            description=story_data["description"],
            issue_type=story_data.get("issue_type", "Story"),
            priority=story_data.get("priority", "Medium"),
        )

        # Track in state
        state.track_ticket(issue.key, "To Do")

        return {
            "action": "create_story",
            "ticket": issue.key,
            "summary": story_data["summary"],
            "agent": self.display_name,
        }

    async def _add_acceptance_criteria(self, ticket_key: str, state: SimulationState) -> dict:
        """Add acceptance criteria to an existing story."""
        issue = self.jira.get_issue(ticket_key)
        current_desc = issue.fields.description or ""

        # Generate AC via LLM
        comment = self.llm.generate_comment(
            agent_name=self.display_name,
            agent_role="Product Manager",
            agent_persona=self.persona,
            ticket_key=ticket_key,
            ticket_summary=issue.fields.summary,
            ticket_description=current_desc,
            recent_comments=[],
            action_context="Adding acceptance criteria to clarify requirements",
            action_type="acceptance_criteria",
        )

        # Add as comment (simpler than editing description)
        self.jira.add_comment(ticket_key, f"**Acceptance Criteria:**\n{comment}")

        return {
            "action": "add_acceptance_criteria",
            "ticket": ticket_key,
            "agent": self.display_name,
        }

    async def _comment_on_progress(self, ticket_key: str, state: SimulationState) -> dict:
        """Add a progress-related comment."""
        issue = self.jira.get_issue(ticket_key)

        # Get recent comments
        comments = self.jira.get_comments(ticket_key, max_results=3)
        recent_comments = [c.body for c in comments]

        comment = self.llm.generate_comment(
            agent_name=self.display_name,
            agent_role="Product Manager",
            agent_persona=self.persona,
            ticket_key=ticket_key,
            ticket_summary=issue.fields.summary,
            ticket_description=issue.fields.description,
            recent_comments=recent_comments,
            action_context="Checking in on progress or asking for status update",
            action_type="progress_check",
        )

        self.jira.add_comment(ticket_key, comment)

        return {
            "action": "comment_on_progress",
            "ticket": ticket_key,
            "agent": self.display_name,
        }

    async def _prioritize_comment(self, state: SimulationState) -> dict:
        """Add a comment about prioritization."""
        backlog = self.jira.get_backlog_issues(max_results=5)
        if not backlog:
            return {"action": "prioritize_backlog", "status": "no_backlog", "agent": self.display_name}

        # Pick a random backlog item to comment on priority
        issue = random.choice(backlog)

        comment = self.llm.generate_comment(
            agent_name=self.display_name,
            agent_role="Product Manager",
            agent_persona=self.persona,
            ticket_key=issue.key,
            ticket_summary=issue.fields.summary,
            ticket_description=issue.fields.description,
            recent_comments=[],
            action_context="Adjusting priority or explaining why this is important",
            action_type="prioritization",
        )

        self.jira.add_comment(issue.key, comment)

        return {
            "action": "prioritize_comment",
            "ticket": issue.key,
            "agent": self.display_name,
        }
