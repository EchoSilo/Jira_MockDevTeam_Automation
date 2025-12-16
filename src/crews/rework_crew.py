"""
Rework Crew - handles QA rejection and rework cycles.

Manages the rework lifecycle:
1. QA rejects with feedback
2. Developer fixes issues
3. Re-review (if applicable)
4. Re-test
"""

from typing import Optional
from crewai import Task

from .base_crew import BaseCrew
from ..state import ActiveScenario, ScenarioPhase


class ReworkCrew(BaseCrew):
    """Crew for handling QA rejection and rework scenarios."""

    def qa_reject(
        self,
        scenario: ActiveScenario,
        rejection_reason: str,
        qa_id: Optional[str] = None,
    ) -> dict:
        """
        QA rejects a ticket with detailed feedback.

        Actions:
        1. Add detailed rejection comment with repro steps
        2. Transition back to In Progress
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
                "action": "qa_reject",
                "ticket": scenario.ticket_key,
                "result": "No QA configured",
                "skipped": True,
            }

        persona = self.get_persona(qa_id)
        agent = self.get_agent(qa_id, use_complex_llm=True)

        task = Task(
            description=f"""You are {persona['display_name']} (QA) and you found an issue with {scenario.ticket_key}.

The issue type: {rejection_reason}

Your task:
1. Use 'Get Issue Details' to understand the ticket and acceptance criteria
2. Use 'Add Comment to Issue' to provide rejection feedback
   - Start with "❌ **QA Failed:**" or similar
   - Describe the issue found (be specific)
   - Include steps to reproduce if applicable
   - This should be 3-5 sentences - detailed enough to be actionable
3. Use 'Transition Issue Status' to move back to 'In Progress'

Your communication style: {persona.get('persona', '')}

Be specific and constructive. The goal is to help the developer fix the issue quickly.
The rejection should be based on something realistic that could be missed during development.
""",
            expected_output=f"QA rejection with feedback added to {scenario.ticket_key}, moved back to In Progress",
            agent=agent,
        )

        result = self.execute_crew([agent], [task])

        return {
            "action": "qa_reject",
            "ticket": scenario.ticket_key,
            "agent": qa_id,
            "rejection_reason": rejection_reason,
            "result": result,
        }

    def developer_acknowledge_rejection(
        self,
        scenario: ActiveScenario,
    ) -> dict:
        """
        Developer acknowledges the rejection and starts fixing.

        Actions:
        1. Add acknowledgment comment
        2. Log some investigation time
        """
        developer_id = scenario.assigned_agent
        if not developer_id:
            return {"error": "No developer assigned"}

        persona = self.get_persona(developer_id)
        agent = self.get_agent(developer_id, use_complex_llm=False)

        task = Task(
            description=f"""You are {persona['display_name']} and your work on {scenario.ticket_key} was rejected by QA.

Your task:
1. Use 'Get Issue Comments' to see the QA feedback
2. Use 'Add Comment to Issue' to acknowledge and respond
   - Acknowledge the issue
   - Briefly say you're looking into it
   - Keep it 1-2 sentences - you're focused on fixing, not writing
3. Use 'Log Work Time' to log 15-30m for investigation

Your communication style: {persona.get('persona', '')}

Be professional and focused. Something like "Got it, looking into this now." is appropriate.
""",
            expected_output=f"Developer acknowledged rejection on {scenario.ticket_key}",
            agent=agent,
        )

        result = self.execute_crew([agent], [task])

        return {
            "action": "developer_acknowledge_rejection",
            "ticket": scenario.ticket_key,
            "agent": developer_id,
            "result": result,
        }

    def developer_fix_issue(
        self,
        scenario: ActiveScenario,
    ) -> dict:
        """
        Developer completes the fix and moves back to review/testing.

        Actions:
        1. Add comment explaining the fix
        2. Transition to Code Review or Testing
        3. Log work time
        """
        developer_id = scenario.assigned_agent
        if not developer_id:
            return {"error": "No developer assigned"}

        persona = self.get_persona(developer_id)
        agent = self.get_agent(developer_id, use_complex_llm=True)

        task = Task(
            description=f"""You are {persona['display_name']} and you've fixed the issue on {scenario.ticket_key}.

Your task:
1. Use 'Get Issue Comments' to see what the original issue was
2. Use 'Add Comment to Issue' to explain your fix
   - Reference the original issue
   - Briefly explain what you changed
   - 2-3 sentences is appropriate
3. Use 'Transition Issue Status' to move to 'Code Review' or 'Testing'
4. Use 'Log Work Time' to log 30m-1h of fix work

Your communication style: {persona.get('persona', '')}

Be specific about what you fixed. This helps QA know what to focus on during re-test.
""",
            expected_output=f"Fix completed on {scenario.ticket_key}, ready for re-test",
            agent=agent,
        )

        result = self.execute_crew([agent], [task])

        return {
            "action": "developer_fix_issue",
            "ticket": scenario.ticket_key,
            "agent": developer_id,
            "result": result,
        }

    def qa_verify_fix(
        self,
        scenario: ActiveScenario,
        qa_id: Optional[str] = None,
    ) -> dict:
        """
        QA verifies the fix and approves the ticket.

        Actions:
        1. Add verification comment
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
                "action": "qa_verify_fix",
                "ticket": scenario.ticket_key,
                "result": "No QA configured",
                "skipped": True,
            }

        persona = self.get_persona(qa_id)
        agent = self.get_agent(qa_id, use_complex_llm=False)

        task = Task(
            description=f"""You are {persona['display_name']} (QA) verifying the fix on {scenario.ticket_key}.

Your task:
1. Use 'Get Issue Comments' to see the developer's fix notes
2. Use 'Add Comment to Issue' to confirm the fix
   - Start with "✅ **Verified:**" or similar
   - Confirm the issue is resolved
   - Mention any additional testing done
   - 1-2 sentences is enough
3. Use 'Transition Issue Status' to move to 'Done'
4. Use 'Log Work Time' to log 15-30m of re-test time

Your communication style: {persona.get('persona', '')}

Be positive - the issue is fixed and you're confirming good work.
""",
            expected_output=f"Fix verified on {scenario.ticket_key}, moved to Done",
            agent=agent,
        )

        result = self.execute_crew([agent], [task])

        return {
            "action": "qa_verify_fix",
            "ticket": scenario.ticket_key,
            "agent": qa_id,
            "result": result,
        }
