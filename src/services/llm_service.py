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

    def generate_release_notes(
        self,
        version_name: str,
        issues_by_category: dict[str, list[dict]],
        issues_by_team: dict[str, dict],
        version_metrics: dict,
    ) -> dict:
        """
        Generate executive and technical release notes for a version.

        Args:
            version_name: The version name (e.g., "v1.2.0")
            issues_by_category: Issues grouped by category (Features, Fixes, Improvements)
                Each item: {"key": "PROJ-123", "summary": "...", "team": "alpha", "type": "Story"}
            issues_by_team: Issues grouped by team with contribution counts
                {"alpha": {"Features": 3, "Fixes": 2, "issues": [...]}, ...}
            version_metrics: Overall metrics
                {"total_issues": 11, "done_count": 11, "teams": ["alpha", "beta"]}

        Returns:
            {
                "executive_notes": str,  # Customer-facing markdown
                "technical_notes": str,  # Internal team-focused markdown
            }
        """
        categories_text = self._format_categories_for_prompt(issues_by_category)
        team_contributions_text = self._format_team_contributions_for_prompt(issues_by_team)

        # Generate executive notes
        executive_prompt = f"""You are a technical writer creating customer-facing release notes for {version_name}.

Write polished, engaging release notes similar to video game patch notes (like Call of Duty or Fortnite updates).

## Issues in this release:
{categories_text}

## Guidelines:
- Focus on WHAT users can now do, not HOW it was built
- Use exciting but professional language
- Group by Features, Fixes, and Improvements (only include sections that have items)
- Avoid technical jargon - speak to end users
- Be concise but impactful
- Use bullet points for easy scanning
- Start with a brief exciting summary paragraph
- Do NOT use emoji

Write the release notes in Markdown format. Just the notes, no preamble."""

        executive_response = self.client.messages.create(
            model=self.complex_model,
            max_tokens=2000,
            messages=[{"role": "user", "content": executive_prompt}],
        )
        executive_notes = executive_response.content[0].text.strip()

        # Generate technical notes
        technical_prompt = f"""You are a release manager creating internal technical release notes for {version_name}.

Write detailed technical release notes for the engineering team and stakeholders.

## Issues by Category:
{categories_text}

## Team Contributions:
{team_contributions_text}

## Metrics:
- Total Issues: {version_metrics.get('total_issues', 0)}
- Teams: {', '.join(version_metrics.get('teams', [])) or 'None'}

## Guidelines:
- Include ticket keys (e.g., PROJ-123) for traceability
- Credit teams with phrases like "Team Alpha delivered..."
- Group by team first, then by category within each team
- Include technical details where relevant
- Note any notable complexity or technical achievements
- Be professional and informative
- Do NOT use emoji

Write the technical release notes in Markdown format. Just the notes, no preamble."""

        technical_response = self.client.messages.create(
            model=self.complex_model,
            max_tokens=2500,
            messages=[{"role": "user", "content": technical_prompt}],
        )
        technical_notes = technical_response.content[0].text.strip()

        return {
            "executive_notes": executive_notes,
            "technical_notes": technical_notes,
        }

    def _format_categories_for_prompt(self, issues_by_category: dict) -> str:
        """Format issues by category for LLM prompt."""
        lines = []
        for category, issues in issues_by_category.items():
            if issues:
                lines.append(f"\n### {category}")
                for issue in issues:
                    lines.append(f"- [{issue['key']}] {issue['summary']} (Team: {issue.get('team', 'Unknown')})")
        return "\n".join(lines) if lines else "No issues in this release."

    def _format_team_contributions_for_prompt(self, issues_by_team: dict) -> str:
        """Format team contributions for LLM prompt."""
        lines = []
        for team, data in issues_by_team.items():
            if team == "unassigned":
                team_name = "Unassigned"
            else:
                team_name = f"Team {team.title()}"
            counts = []
            for cat in ["Features", "Fixes", "Improvements"]:
                count = data.get(cat, 0)
                if count > 0:
                    counts.append(f"{count} {cat}")
            if counts:
                lines.append(f"\n### {team_name}")
                lines.append(f"Delivered: {', '.join(counts)}")
                for issue in data.get("issues", []):
                    lines.append(f"- [{issue['key']}] {issue['summary']}")
        return "\n".join(lines) if lines else "No team contributions recorded."
