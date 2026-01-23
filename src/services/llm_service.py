"""
LLM Service for generating contextual content.
Routes between Haiku (fast/cheap) and Sonnet (complex) based on action type.
"""

import os
import logging
import time
from typing import Optional
import anthropic
import litellm
import yaml

logger = logging.getLogger(__name__)


class LLMService:
    """Handles all LLM interactions with model routing via LiteLLM.

    Supports multiple providers through LiteLLM:
    - anthropic/model-name: Direct Anthropic API
    - openrouter/provider/model: OpenRouter (100+ models)
    - openai/model-name: Direct OpenAI API
    """

    def __init__(self, config_path: str = "config/settings.yaml"):
        # Keep Anthropic client only for Skills API (beta feature not in LiteLLM)
        self._anthropic_client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY", "")
        )
        # LiteLLM uses environment variables automatically for API keys:
        # ANTHROPIC_API_KEY, OPENROUTER_API_KEY, OPENAI_API_KEY, etc.

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

        response = litellm.completion(
            model=model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.choices[0].message.content.strip()

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

        response = litellm.completion(
            model=self.complex_model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )

        import json
        return json.loads(response.choices[0].message.content.strip())

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

        response = litellm.completion(
            model=self.complex_model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )

        import json
        return json.loads(response.choices[0].message.content.strip())

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

        response = litellm.completion(
            model=self.complex_model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.choices[0].message.content.strip()

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

        executive_response = litellm.completion(
            model=self.complex_model,
            max_tokens=2000,
            messages=[{"role": "user", "content": executive_prompt}],
        )
        executive_notes = executive_response.choices[0].message.content.strip()

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

        technical_response = litellm.completion(
            model=self.complex_model,
            max_tokens=2500,
            messages=[{"role": "user", "content": technical_prompt}],
        )
        technical_notes = technical_response.choices[0].message.content.strip()

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

    def generate_release_tags(
        self,
        version_name: str,
        issues_by_category: dict[str, list[dict]],
        executive_notes: str,
    ) -> list[str]:
        """
        Generate 3-5 descriptive tags for a release based on its content.

        Tags are high-level themes like:
        - "Security", "Performance", "UX", "API", "Bug Fixes"
        - "Breaking Changes", "New Features", "Infrastructure"
        - Domain-specific: "Equipment", "Workouts", "Analytics"

        Args:
            version_name: The version name (e.g., "v1.2.0")
            issues_by_category: Issues grouped by category
            executive_notes: The executive summary for additional context

        Returns:
            List of 3-5 tag strings
        """
        import json as json_module

        categories_text = self._format_categories_for_prompt(issues_by_category)

        prompt = f"""Analyze this software release and generate 3-5 descriptive tags.

Version: {version_name}

Issues by category:
{categories_text}

Executive summary:
{executive_notes[:1500]}

Generate tags that:
- Describe the major themes/areas of this release
- Are 1-2 words each (e.g., "Performance", "New Features", "Bug Fixes")
- Are useful for filtering/searching releases later
- Include both technical categories (API, Performance, Security) and functional areas
- Reflect what's actually in the release, not generic placeholders

Common tag examples: "Performance", "Security", "New Features", "Bug Fixes", "UX Improvements", "API Changes", "Infrastructure", "Documentation", "Mobile", "Integrations", "Analytics", "User Management"

Respond with ONLY a JSON array of tag strings, nothing else.
Example: ["New Features", "Performance", "Bug Fixes"]"""

        try:
            response = litellm.completion(
                model=self.routine_model,  # Use Haiku for speed/cost
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse the JSON array from response
            response_text = response.choices[0].message.content.strip()

            # Handle potential markdown code blocks
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                response_text = "\n".join(lines[1:-1])

            tags = json_module.loads(response_text)

            # Ensure we have a list of strings and limit to 5 tags
            if isinstance(tags, list):
                tags = [str(t).strip() for t in tags[:5] if t]
                logger.info(f"Generated {len(tags)} tags for {version_name}: {tags}")
                return tags

        except Exception as e:
            logger.warning(f"Failed to generate tags for {version_name}: {e}")

        # Return empty list on failure
        return []

    def generate_document_with_skill(
        self,
        skill_id: str,
        version_name: str,
        executive_notes: str,
        technical_notes: str,
        metrics: dict,
    ) -> bytes:
        """
        Generate a document using Anthropic Skills API.

        Args:
            skill_id: The skill to use ("pptx", "docx", or "pdf")
            version_name: The version name for the release
            executive_notes: Customer-facing release notes (markdown)
            technical_notes: Technical release notes (markdown)
            metrics: Release metrics dict

        Returns:
            bytes: The generated document file content
        """
        logger.info(f"[Skills API] Starting document generation: skill={skill_id}, version={version_name}")
        start_time = time.time()

        prompt = f"""Create a professional release notes document for {version_name}.

## Executive Summary (Customer-Facing)
{executive_notes}

## Technical Details (Internal)
{technical_notes}

## Statistics
- Total Issues: {metrics.get('total_issues', 0)}
- Teams Contributing: {', '.join(metrics.get('teams', [])) or 'None'}
- Features: {metrics.get('category_counts', {}).get('Features', 0)}
- Fixes: {metrics.get('category_counts', {}).get('Fixes', 0)}
- Improvements: {metrics.get('category_counts', {}).get('Improvements', 0)}

Create a polished, professional document with:
- Clear section headers
- Good visual hierarchy
- Professional formatting
- Executive summary first, then technical details
"""

        try:
            logger.info(f"[Skills API] Calling beta.messages.create with skill_id={skill_id}")

            # Skills API requires direct Anthropic client (not available via LiteLLM)
            response = self._anthropic_client.beta.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=16384,
                betas=["code-execution-2025-08-25", "skills-2025-10-02"],
                container={
                    "skills": [{
                        "type": "anthropic",
                        "skill_id": skill_id,
                        "version": "latest"
                    }]
                },
                messages=[{"role": "user", "content": prompt}],
                tools=[{"type": "code_execution_20250825", "name": "code_execution"}]
            )

            elapsed = time.time() - start_time
            logger.info(f"[Skills API] Response received in {elapsed:.2f}s")

            # Log response structure for debugging
            logger.info(f"[Skills API] Response type: {type(response).__name__}")
            logger.info(f"[Skills API] Response stop_reason: {getattr(response, 'stop_reason', 'N/A')}")
            logger.info(f"[Skills API] Response content blocks: {len(response.content)}")

            for i, block in enumerate(response.content):
                block_type = getattr(block, 'type', 'unknown')
                logger.info(f"[Skills API] Block {i}: type={block_type}")

                # Log text content (truncated)
                if block_type == 'text' and hasattr(block, 'text'):
                    preview = block.text[:200] + "..." if len(block.text) > 200 else block.text
                    logger.info(f"[Skills API] Block {i} text preview: {preview}")

                # Log all attributes for debugging
                attrs = [a for a in dir(block) if not a.startswith('_')]
                logger.debug(f"[Skills API] Block {i} attributes: {attrs}")

            # Extract file_id from response
            file_id = self._extract_file_id_from_response(response)

            if not file_id:
                # Detailed error for debugging
                block_types = [getattr(b, 'type', 'unknown') for b in response.content]
                error_msg = f"No file_id found. Response had {len(response.content)} blocks: {block_types}"
                logger.error(f"[Skills API] {error_msg}")

                # Log full response for debugging
                for i, block in enumerate(response.content):
                    logger.error(f"[Skills API] Full block {i}: {block}")

                raise ValueError(error_msg)

            logger.info(f"[Skills API] Extracted file_id: {file_id}")

            # Download the file
            logger.info(f"[Skills API] Downloading file...")
            file_response = self._anthropic_client.beta.files.download(
                file_id=file_id,
                betas=["files-api-2025-04-14"]
            )

            # Handle BinaryAPIResponse - try different methods to get content
            logger.info(f"[Skills API] File response type: {type(file_response).__name__}")
            if hasattr(file_response, 'read'):
                content = file_response.read()
            elif hasattr(file_response, 'content'):
                content = file_response.content
            elif hasattr(file_response, 'iter_bytes'):
                content = b''.join(file_response.iter_bytes())
            else:
                # Try to read as bytes directly
                content = bytes(file_response)
            logger.info(f"[Skills API] File downloaded: {len(content)} bytes")

            total_elapsed = time.time() - start_time
            logger.info(f"[Skills API] Document generation complete in {total_elapsed:.2f}s")

            return content

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"[Skills API] Failed after {elapsed:.2f}s: {type(e).__name__}: {e}")
            raise

    def _extract_file_id_from_response(self, response) -> Optional[str]:
        """Extract file_id from a Skills API response with detailed logging."""
        logger.debug(f"[Skills API] Searching for file_id in response...")

        # First check response-level attributes
        if hasattr(response, 'output_files') and response.output_files:
            for f in response.output_files:
                if hasattr(f, 'file_id'):
                    logger.info(f"[Skills API] Found file_id in response.output_files: {f.file_id}")
                    return f.file_id

        for i, block in enumerate(response.content):
            block_type = getattr(block, 'type', None)
            logger.debug(f"[Skills API] Checking block {i}: type={block_type}")

            # Log all attributes of this block for debugging
            attrs = [a for a in dir(block) if not a.startswith('_')]
            logger.info(f"[Skills API] Block {i} ({block_type}) attributes: {attrs}")

            # Check for tool_result blocks
            if block_type == 'tool_result':
                logger.debug(f"[Skills API] Found tool_result block")
                if hasattr(block, 'content'):
                    for j, item in enumerate(block.content):
                        item_type = getattr(item, 'type', 'unknown')
                        logger.debug(f"[Skills API] tool_result item {j}: type={item_type}")
                        if hasattr(item, 'file_id'):
                            logger.info(f"[Skills API] Found file_id in tool_result: {item.file_id}")
                            return item.file_id

            # Check for direct file blocks
            elif block_type == 'file':
                if hasattr(block, 'file_id'):
                    logger.info(f"[Skills API] Found file_id in file block: {block.file_id}")
                    return block.file_id

            # Check for container_result (Skills API specific)
            elif block_type == 'container_result':
                logger.debug(f"[Skills API] Found container_result block")
                if hasattr(block, 'files') and block.files:
                    for f in block.files:
                        if hasattr(f, 'file_id'):
                            logger.info(f"[Skills API] Found file_id in container_result: {f.file_id}")
                            return f.file_id

            # Check for code execution result blocks (bash, text_editor)
            elif 'code_execution_tool_result' in str(block_type):
                logger.info(f"[Skills API] Found code execution result block: {block_type}")
                # Check content attribute
                if hasattr(block, 'content'):
                    content = block.content
                    logger.info(f"[Skills API] Block content type: {type(content).__name__}")
                    # Content might be an object or a list
                    if hasattr(content, 'file_id'):
                        logger.info(f"[Skills API] Found file_id in content: {content.file_id}")
                        return content.file_id
                    # Check for nested content list (BetaBashCodeExecutionResultBlock.content)
                    if hasattr(content, 'content') and isinstance(content.content, list):
                        for k, item in enumerate(content.content):
                            logger.info(f"[Skills API] Checking nested content item {k}: {type(item).__name__}")
                            if hasattr(item, 'file_id') and item.file_id:
                                logger.info(f"[Skills API] Found file_id in content.content[{k}]: {item.file_id}")
                                return item.file_id
                    if hasattr(content, 'files') and content.files:
                        for f in content.files:
                            if hasattr(f, 'file_id'):
                                logger.info(f"[Skills API] Found file_id in content.files: {f.file_id}")
                                return f.file_id
                    # Check for output_files
                    if hasattr(content, 'output_files') and content.output_files:
                        for f in content.output_files:
                            if hasattr(f, 'file_id'):
                                logger.info(f"[Skills API] Found file_id in content.output_files: {f.file_id}")
                                return f.file_id
                # Check block-level files attribute
                if hasattr(block, 'files') and block.files:
                    for f in block.files:
                        if hasattr(f, 'file_id'):
                            logger.info(f"[Skills API] Found file_id in block.files: {f.file_id}")
                            return f.file_id
                # Check output_files attribute
                if hasattr(block, 'output_files') and block.output_files:
                    for f in block.output_files:
                        if hasattr(f, 'file_id'):
                            logger.info(f"[Skills API] Found file_id in block.output_files: {f.file_id}")
                            return f.file_id

            # Check nested content structures
            if hasattr(block, 'content') and isinstance(block.content, list):
                for j, item in enumerate(block.content):
                    if hasattr(item, 'file_id'):
                        logger.info(f"[Skills API] Found file_id in nested content: {item.file_id}")
                        return item.file_id
                    if hasattr(item, 'type') and item.type == 'file':
                        if hasattr(item, 'file_id'):
                            logger.info(f"[Skills API] Found file_id in nested file block: {item.file_id}")
                            return item.file_id

        logger.warning(f"[Skills API] No file_id found in response")
        return None
