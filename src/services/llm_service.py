"""
LLM Service for generating contextual content.
Routes between Haiku (fast/cheap) and Sonnet (complex) based on action type.
"""

import os
from typing import Optional
import anthropic
import yaml


class LLMService:
    """Handles all LLM interactions with model routing."""

    def __init__(self, config_path: str = "config/settings.yaml"):
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        self.routine_model = config["llm"]["routine_model"]
        self.complex_model = config["llm"]["complex_model"]
        self.complex_actions = config["llm"]["complex_actions"]

    def _get_model(self, action_type: str) -> str:
        """Determine which model to use based on action type."""
        if action_type in self.complex_actions:
            return self.complex_model
        return self.routine_model

    def generate_comment(
        self,
        agent_name: str,
        agent_role: str,
        agent_persona: str,
        ticket_key: str,
        ticket_summary: str,
        ticket_description: str,
        recent_comments: list[str],
        action_context: str,
        action_type: str = "comment",
    ) -> str:
        """Generate a contextual comment for a Jira ticket."""

        comments_text = "\n".join(
            [f"- {c}" for c in recent_comments[-3:]]
        ) if recent_comments else "No recent comments."

        prompt = f"""You are {agent_name}, a {agent_role} on a software development team.

Your personality and communication style:
{agent_persona}

Current ticket:
- Key: {ticket_key}
- Summary: {ticket_summary}
- Description: {ticket_description[:500] if ticket_description else 'No description'}

Recent comments on this ticket:
{comments_text}

Context: {action_context}

Write a realistic, brief Jira comment (1-3 sentences) that:
- Matches your persona's communication style
- References specific details from the ticket when relevant
- Sounds like a real {agent_role}, not AI
- Is professional but natural

Do NOT use phrases like:
- "I hope this helps"
- "Let me know if you have questions"
- "Happy to help"
- Any emoji

Just write the comment text directly, nothing else."""

        model = self._get_model(action_type)

        response = self.client.messages.create(
            model=model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text.strip()

    def generate_story(
        self,
        agent_name: str,
        agent_persona: str,
        team_focus: str,
        existing_epics: list[str],
        recent_stories: list[str],
    ) -> dict:
        """Generate a new story for the backlog."""

        epics_text = "\n".join([f"- {e}" for e in existing_epics]) if existing_epics else "No existing epics."
        stories_text = "\n".join([f"- {s}" for s in recent_stories[-5:]]) if recent_stories else "No recent stories."

        prompt = f"""You are {agent_name}, a Product Manager.

Your style:
{agent_persona}

Team focus area: {team_focus}

Existing epics in the project:
{epics_text}

Recent stories created:
{stories_text}

Create a NEW user story that:
- Fits the team's focus area
- Doesn't duplicate recent stories
- Is realistic for a software product
- Has clear acceptance criteria

Respond in this exact JSON format:
{{
    "summary": "Brief story title (as user story or task title)",
    "description": "Detailed description with acceptance criteria in bullet points",
    "issue_type": "Story",
    "priority": "Medium"
}}

Just the JSON, nothing else."""

        response = self.client.messages.create(
            model=self.complex_model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )

        import json
        return json.loads(response.content[0].text.strip())

    def generate_bug_report(
        self,
        agent_name: str,
        agent_persona: str,
        related_ticket: dict,
    ) -> dict:
        """Generate a bug report based on testing a ticket."""

        prompt = f"""You are {agent_name}, a QA Engineer.

Your style:
{agent_persona}

You found an issue while testing this ticket:
- Summary: {related_ticket.get('summary', 'Unknown')}
- Description: {related_ticket.get('description', 'No description')[:300]}

Create a realistic bug report that:
- Describes a plausible issue that could occur
- Has clear reproduction steps
- Is related to the original ticket's functionality

Respond in this exact JSON format:
{{
    "summary": "Bug: Brief description of the issue",
    "description": "## Description\\nWhat's happening\\n\\n## Steps to Reproduce\\n1. Step one\\n2. Step two\\n\\n## Expected Behavior\\nWhat should happen\\n\\n## Actual Behavior\\nWhat actually happens",
    "issue_type": "Bug",
    "priority": "High"
}}

Just the JSON, nothing else."""

        response = self.client.messages.create(
            model=self.complex_model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )

        import json
        return json.loads(response.content[0].text.strip())

    def generate_technical_comment(
        self,
        agent_name: str,
        agent_role: str,
        agent_persona: str,
        ticket_key: str,
        ticket_summary: str,
        ticket_description: str,
        comment_type: str,  # e.g., "architectural", "code_review", "blocker"
    ) -> str:
        """Generate a technical comment (uses complex model)."""

        type_guidance = {
            "architectural": "Discuss architectural considerations, trade-offs, or concerns.",
            "code_review": "Provide code review feedback - what looks good, what could be improved.",
            "blocker": "Explain a technical blocker and what's needed to unblock.",
            "design": "Discuss design decisions or alternatives.",
        }

        guidance = type_guidance.get(comment_type, "Provide technical insight.")

        prompt = f"""You are {agent_name}, a {agent_role}.

Your style:
{agent_persona}

Ticket: {ticket_key} - {ticket_summary}
Description: {ticket_description[:400] if ticket_description else 'No description'}

Task: {guidance}

Write a realistic technical comment (2-4 sentences) that:
- Shows technical depth appropriate for your role
- References specific aspects of the ticket
- Sounds like an experienced engineer

No fluff, no AI-speak. Just the comment."""

        response = self.client.messages.create(
            model=self.complex_model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text.strip()
