"""
Logged LLM Service wrapper.

Wraps LLMService to capture all LLM calls with full prompts,
responses, token usage, and timing.
"""

import time
from typing import Optional

from ..services.llm_service import LLMService
from .writer import AsyncLogWriter


class LoggedLLMService(LLMService):
    """
    Drop-in replacement for LLMService that logs all calls.

    Inherits from LLMService and wraps each method to capture
    prompts, responses, token counts, and timing.
    """

    def __init__(
        self,
        log_writer: AsyncLogWriter,
        config_path: str = "config/settings.yaml",
    ):
        super().__init__(config_path)
        self._log_writer = log_writer

        # Context for logging - can be set per-call
        self._current_agent_id: Optional[str] = None
        self._current_agent_name: Optional[str] = None
        self._current_ticket_key: Optional[str] = None
        self._current_scenario_id: Optional[str] = None

    def set_context(
        self,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        ticket_key: Optional[str] = None,
        scenario_id: Optional[str] = None,
    ) -> None:
        """Set context for subsequent log entries."""
        self._current_agent_id = agent_id
        self._current_agent_name = agent_name
        self._current_ticket_key = ticket_key
        self._current_scenario_id = scenario_id

    def clear_context(self) -> None:
        """Clear the current context."""
        self._current_agent_id = None
        self._current_agent_name = None
        self._current_ticket_key = None
        self._current_scenario_id = None

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
        """Generate a contextual comment with full logging."""

        # Build the prompt (same logic as parent)
        comments_text = (
            "\n".join([f"- {c}" for c in recent_comments[-3:]])
            if recent_comments
            else "No recent comments."
        )

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
        is_complex = model == self.complex_model
        start_time = time.time()

        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )

            duration_ms = int((time.time() - start_time) * 1000)
            response_text = response.content[0].text.strip()

            # Log the call
            self._log_writer.log_llm_call(
                model=model,
                action_type=action_type,
                prompt=prompt,
                response=response_text,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=agent_name,
                ticket_key=ticket_key,
                scenario_id=self._current_scenario_id,
                is_complex=is_complex,
            )

            return response_text

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_writer.log_llm_call(
                model=model,
                action_type=action_type,
                prompt=prompt,
                response="",
                input_tokens=0,
                output_tokens=0,
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=agent_name,
                ticket_key=ticket_key,
                scenario_id=self._current_scenario_id,
                is_complex=is_complex,
                error=str(e),
            )
            raise

    def generate_story(
        self,
        agent_name: str,
        agent_persona: str,
        team_focus: str,
        existing_epics: list[str],
        recent_stories: list[str],
    ) -> dict:
        """Generate a new story with full logging."""

        epics_text = (
            "\n".join([f"- {e}" for e in existing_epics])
            if existing_epics
            else "No existing epics."
        )
        stories_text = (
            "\n".join([f"- {s}" for s in recent_stories[-5:]])
            if recent_stories
            else "No recent stories."
        )

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

        model = self.complex_model
        start_time = time.time()

        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )

            duration_ms = int((time.time() - start_time) * 1000)
            raw_response = response.content[0].text.strip()

            # Log the call
            self._log_writer.log_llm_call(
                model=model,
                action_type="generate_story",
                prompt=prompt,
                response=raw_response,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=agent_name,
                ticket_key=self._current_ticket_key,
                scenario_id=self._current_scenario_id,
                is_complex=True,
            )

            import json

            return json.loads(raw_response)

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_writer.log_llm_call(
                model=model,
                action_type="generate_story",
                prompt=prompt,
                response="",
                input_tokens=0,
                output_tokens=0,
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=agent_name,
                is_complex=True,
                error=str(e),
            )
            raise

    def generate_bug_report(
        self,
        agent_name: str,
        agent_persona: str,
        related_ticket: dict,
    ) -> dict:
        """Generate a bug report with full logging."""

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

        model = self.complex_model
        start_time = time.time()

        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )

            duration_ms = int((time.time() - start_time) * 1000)
            raw_response = response.content[0].text.strip()

            # Log the call
            self._log_writer.log_llm_call(
                model=model,
                action_type="generate_bug_report",
                prompt=prompt,
                response=raw_response,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=agent_name,
                ticket_key=related_ticket.get("key"),
                scenario_id=self._current_scenario_id,
                is_complex=True,
            )

            import json

            return json.loads(raw_response)

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_writer.log_llm_call(
                model=model,
                action_type="generate_bug_report",
                prompt=prompt,
                response="",
                input_tokens=0,
                output_tokens=0,
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=agent_name,
                is_complex=True,
                error=str(e),
            )
            raise

    def generate_technical_comment(
        self,
        agent_name: str,
        agent_role: str,
        agent_persona: str,
        ticket_key: str,
        ticket_summary: str,
        ticket_description: str,
        comment_type: str,
    ) -> str:
        """Generate a technical comment with full logging."""

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

        model = self.complex_model
        start_time = time.time()

        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )

            duration_ms = int((time.time() - start_time) * 1000)
            response_text = response.content[0].text.strip()

            # Log the call
            self._log_writer.log_llm_call(
                model=model,
                action_type=f"technical_comment_{comment_type}",
                prompt=prompt,
                response=response_text,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=agent_name,
                ticket_key=ticket_key,
                scenario_id=self._current_scenario_id,
                is_complex=True,
            )

            return response_text

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self._log_writer.log_llm_call(
                model=model,
                action_type=f"technical_comment_{comment_type}",
                prompt=prompt,
                response="",
                input_tokens=0,
                output_tokens=0,
                duration_ms=duration_ms,
                agent_id=self._current_agent_id,
                agent_name=agent_name,
                ticket_key=ticket_key,
                scenario_id=self._current_scenario_id,
                is_complex=True,
                error=str(e),
            )
            raise
