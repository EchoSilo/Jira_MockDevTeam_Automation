"""
Ticket Lifecycle Crew - handles normal ticket flow through the workflow.

Manages transitions:
- Backlog → Assigned (dev picks up)
- In Progress → Code Review (dev completes)
- Code Review → Testing (tech lead approves)
- Testing → Done (QA approves)
"""

from typing import Optional
from crewai import Crew, Task, Process

from .base_crew import BaseCrew
from ..state import ActiveScenario, ScenarioPhase


class TicketLifecycleCrew(BaseCrew):
    """Crew for progressing tickets through normal workflow."""

    def pick_up_from_backlog(
        self,
        scenario: ActiveScenario,
        developer_id: str,
    ) -> dict:
        """
        Developer picks up a ticket from backlog and starts work.

        Actions:
        1. Assign ticket to developer
        2. Transition to In Progress
        3. Add pickup comment
        """
        persona = self.get_persona(developer_id)
        agent = self.get_agent(developer_id, use_complex_llm=False)

        task = Task(
            description=f"""You are {persona['display_name']} picking up ticket {scenario.ticket_key}.

Your task:
1. Use the 'Assign Issue to User' tool to assign {scenario.ticket_key} to account ID: {persona['jira_account_id']}
2. Use the 'Transition Issue Status' tool to move {scenario.ticket_key} to 'In Progress'
3. Use the 'Add Comment to Issue' tool to add a brief comment indicating you're starting work

Your communication style: {persona.get('persona', '')}

Keep the comment brief and natural - something like "Picking this up" or "Starting work on this now."
""",
            expected_output=f"Confirmation that {scenario.ticket_key} was assigned, transitioned to In Progress, and comment added",
            agent=agent,
        )

        result = self.execute_crew([agent], [task])

        return {
            "action": "pick_up_from_backlog",
            "ticket": scenario.ticket_key,
            "agent": developer_id,
            "result": result,
        }

    def progress_to_review(
        self,
        scenario: ActiveScenario,
    ) -> dict:
        """
        Developer completes work and moves ticket to code review.

        Actions:
        1. Add completion comment
        2. Transition to Code Review
        3. Log work time
        """
        developer_id = scenario.assigned_agent
        if not developer_id:
            return {"error": "No developer assigned to scenario"}

        persona = self.get_persona(developer_id)
        agent = self.get_agent(developer_id, use_complex_llm=True)  # Complex for contextual comment

        task = Task(
            description=f"""You are {persona['display_name']} completing work on {scenario.ticket_key}.

Your task:
1. First, use 'Get Issue Details' to understand what this ticket is about
2. Use 'Add Comment to Issue' to add a brief completion comment
   - Reference something specific about the implementation
   - Keep it 1-2 sentences, professional and technical
3. Use 'Transition Issue Status' to move the ticket to 'Code Review'
4. Use 'Log Work Time' to log between 30m and 2h of work

Your communication style: {persona.get('persona', '')}

Important: Your comment should sound like a real developer, not AI. Be brief and specific.
""",
            expected_output=f"Confirmation that {scenario.ticket_key} was moved to Code Review with comment and work logged",
            agent=agent,
        )

        result = self.execute_crew([agent], [task])

        return {
            "action": "progress_to_review",
            "ticket": scenario.ticket_key,
            "agent": developer_id,
            "result": result,
        }

    def complete_code_review(
        self,
        scenario: ActiveScenario,
        tech_lead_id: Optional[str] = None,
    ) -> dict:
        """
        Tech lead reviews and approves code, moving to testing.

        Actions:
        1. Add code review comment
        2. Transition to Testing/Ready for QA
        """
        # Find tech lead for this team if not provided
        if not tech_lead_id:
            developer_id = scenario.assigned_agent
            if developer_id:
                dev_persona = self.get_persona(developer_id)
                team = dev_persona.get("team", "alpha")
                team_agents = self.get_team_agents(team)
                tech_lead_id = team_agents.get("tech_lead")

        if not tech_lead_id:
            # No tech lead, auto-approve by transitioning directly
            return {
                "action": "complete_code_review",
                "ticket": scenario.ticket_key,
                "result": "Auto-approved (no tech lead configured)",
                "skipped": True,
            }

        persona = self.get_persona(tech_lead_id)
        agent = self.get_agent(tech_lead_id, use_complex_llm=True)

        task = Task(
            description=f"""You are {persona['display_name']} reviewing {scenario.ticket_key} in code review.

Your task:
1. Use 'Get Issue Details' to understand the ticket
2. Use 'Get Issue Comments' to see what the developer said about the implementation
3. Use 'Add Comment to Issue' to add code review feedback
   - Provide constructive technical feedback
   - Note what looks good and any suggestions
   - Keep it 2-3 sentences
4. Use 'Transition Issue Status' to move to 'Testing' or 'Ready for QA'

Your communication style: {persona.get('persona', '')}

Be specific and technical in your feedback. Reference actual aspects of the ticket.
""",
            expected_output=f"Confirmation that {scenario.ticket_key} code review completed and moved to Testing",
            agent=agent,
        )

        result = self.execute_crew([agent], [task])

        return {
            "action": "complete_code_review",
            "ticket": scenario.ticket_key,
            "agent": tech_lead_id,
            "result": result,
        }

    def qa_approve(
        self,
        scenario: ActiveScenario,
        qa_id: Optional[str] = None,
    ) -> dict:
        """
        QA tests and approves ticket, moving to Done.

        Actions:
        1. Add QA approval comment
        2. Transition to Done
        3. Log testing time
        """
        # Find QA for this team if not provided
        if not qa_id:
            developer_id = scenario.assigned_agent
            if developer_id:
                dev_persona = self.get_persona(developer_id)
                team = dev_persona.get("team", "alpha")
                team_agents = self.get_team_agents(team)
                qa_id = team_agents.get("qa")

        if not qa_id:
            return {
                "action": "qa_approve",
                "ticket": scenario.ticket_key,
                "result": "No QA configured",
                "skipped": True,
            }

        persona = self.get_persona(qa_id)
        agent = self.get_agent(qa_id, use_complex_llm=False)

        task = Task(
            description=f"""You are {persona['display_name']} testing {scenario.ticket_key}.

Your task:
1. Use 'Get Issue Details' to understand the ticket and acceptance criteria
2. Use 'Add Comment to Issue' to add QA approval comment
   - Confirm testing passed
   - Mention what was verified (briefly)
   - 1-2 sentences is enough
3. Use 'Transition Issue Status' to move to 'Done'
4. Use 'Log Work Time' to log 15m-1h of testing time

Your communication style: {persona.get('persona', '')}

Keep it brief - something like "Tested and verified. All acceptance criteria met." with maybe one specific detail.
""",
            expected_output=f"Confirmation that {scenario.ticket_key} passed QA and moved to Done",
            agent=agent,
        )

        result = self.execute_crew([agent], [task])

        return {
            "action": "qa_approve",
            "ticket": scenario.ticket_key,
            "agent": qa_id,
            "result": result,
        }

    def add_progress_comment(
        self,
        scenario: ActiveScenario,
    ) -> dict:
        """
        Developer adds a progress update comment (for in-progress tickets).

        Used to add activity without changing status.
        """
        developer_id = scenario.assigned_agent
        if not developer_id:
            return {"error": "No developer assigned"}

        persona = self.get_persona(developer_id)
        agent = self.get_agent(developer_id, use_complex_llm=True)

        task = Task(
            description=f"""You are {persona['display_name']} providing a progress update on {scenario.ticket_key}.

Your task:
1. Use 'Get Issue Details' to understand the ticket
2. Use 'Get Issue Comments' to see recent conversation
3. Use 'Add Comment to Issue' to add a progress update
   - Share what you've done or are working on
   - Mention any findings or decisions
   - Keep it 1-2 sentences

Your communication style: {persona.get('persona', '')}

Sound natural - this is just a status update, not a formal report.
""",
            expected_output=f"Progress comment added to {scenario.ticket_key}",
            agent=agent,
        )

        result = self.execute_crew([agent], [task])

        return {
            "action": "add_progress_comment",
            "ticket": scenario.ticket_key,
            "agent": developer_id,
            "result": result,
        }
