"""
Blocker Crew - handles blocking scenarios.

Manages the blocker lifecycle:
1. Developer flags a blocker
2. Discussion/investigation period
3. Blocker resolution
"""

from typing import Optional
from crewai import Task

from .base_crew import BaseCrew
from ..state import ActiveScenario, ScenarioPhase


class BlockerCrew(BaseCrew):
    """Crew for handling blocker scenarios."""

    def inject_blocker(
        self,
        scenario: ActiveScenario,
        blocker_reason: str,
    ) -> dict:
        """
        Developer flags a blocker on their ticket.

        Actions:
        1. Add blocker comment explaining the issue
        2. Optionally transition to Blocked status (if available)
        """
        developer_id = scenario.assigned_agent
        if not developer_id:
            return {"error": "No developer assigned to scenario"}

        persona = self.get_persona(developer_id)
        agent = self.get_agent(developer_id, use_complex_llm=True)

        task = Task(
            description=f"""You are {persona['display_name']} and you've hit a blocker on {scenario.ticket_key}.

The blocker situation: {blocker_reason}

Your task:
1. Use 'Get Issue Details' to understand the ticket context
2. Use 'Add Comment to Issue' to explain the blocker
   - Start with "⚠️ **Blocked:**" or similar indicator
   - Explain what the blocker is
   - Mention what's needed to unblock
   - Keep it 2-4 sentences
3. Try to use 'Transition Issue Status' to move to 'Blocked' (may not be available)

Your communication style: {persona.get('persona', '')}

Be specific about what's blocking you and what help you need. Don't be vague.
""",
            expected_output=f"Blocker flagged on {scenario.ticket_key} with explanation",
            agent=agent,
        )

        result = self.execute_crew([agent], [task])

        return {
            "action": "inject_blocker",
            "ticket": scenario.ticket_key,
            "agent": developer_id,
            "blocker_reason": blocker_reason,
            "result": result,
        }

    def discuss_blocker(
        self,
        scenario: ActiveScenario,
        responder_id: Optional[str] = None,
    ) -> dict:
        """
        Tech lead or another developer responds to the blocker.

        Actions:
        1. Review the blocker
        2. Add comment with suggestions or status
        """
        # Find someone to respond - preferably tech lead
        if not responder_id:
            developer_id = scenario.assigned_agent
            if developer_id:
                dev_persona = self.get_persona(developer_id)
                team = dev_persona.get("team", "alpha")
                team_agents = self.get_team_agents(team)

                # Prefer tech lead, then another developer
                responder_id = team_agents.get("tech_lead")
                if not responder_id and team_agents.get("developer"):
                    # Find a different developer
                    for dev_id in team_agents["developer"]:
                        if dev_id != developer_id:
                            responder_id = dev_id
                            break

        if not responder_id:
            return {
                "action": "discuss_blocker",
                "ticket": scenario.ticket_key,
                "result": "No one available to respond",
                "skipped": True,
            }

        persona = self.get_persona(responder_id)
        role = persona.get("role", "developer")
        agent = self.get_agent(responder_id, use_complex_llm=True)

        task = Task(
            description=f"""You are {persona['display_name']} ({role}) responding to a blocker on {scenario.ticket_key}.

The blocker reason was: {scenario.blocker_reason or 'See ticket comments'}

Your task:
1. Use 'Get Issue Details' to understand the ticket
2. Use 'Get Issue Comments' to see the blocker details
3. Use 'Add Comment to Issue' to respond helpfully
   - Acknowledge the blocker
   - Offer suggestions, context, or next steps
   - If you can help unblock, say so
   - 2-3 sentences is appropriate

Your communication style: {persona.get('persona', '')}

Be helpful and constructive. This is a team working together to solve a problem.
""",
            expected_output=f"Response to blocker on {scenario.ticket_key}",
            agent=agent,
        )

        result = self.execute_crew([agent], [task])

        return {
            "action": "discuss_blocker",
            "ticket": scenario.ticket_key,
            "agent": responder_id,
            "result": result,
        }

    def resolve_blocker(
        self,
        scenario: ActiveScenario,
        resolution_note: Optional[str] = None,
    ) -> dict:
        """
        Developer resolves the blocker and continues work.

        Actions:
        1. Add resolution comment
        2. Transition back to In Progress (if was in Blocked)
        """
        developer_id = scenario.assigned_agent
        if not developer_id:
            return {"error": "No developer assigned to scenario"}

        persona = self.get_persona(developer_id)
        agent = self.get_agent(developer_id, use_complex_llm=True)

        resolution_context = resolution_note or "Blocker has been resolved"

        task = Task(
            description=f"""You are {persona['display_name']} and the blocker on {scenario.ticket_key} has been resolved.

Resolution context: {resolution_context}

Your task:
1. Use 'Get Issue Details' and 'Get Issue Comments' to see the blocker discussion
2. Use 'Add Comment to Issue' to indicate the blocker is resolved
   - Briefly explain what unblocked you
   - Thank anyone who helped (if applicable)
   - Note that you're resuming work
   - 1-2 sentences
3. Use 'Transition Issue Status' to move back to 'In Progress' if needed

Your communication style: {persona.get('persona', '')}

Keep it brief and positive - the blocker is resolved, time to move on.
""",
            expected_output=f"Blocker resolved on {scenario.ticket_key}, back to In Progress",
            agent=agent,
        )

        result = self.execute_crew([agent], [task])

        return {
            "action": "resolve_blocker",
            "ticket": scenario.ticket_key,
            "agent": developer_id,
            "result": result,
        }

    def pm_check_on_blocker(
        self,
        scenario: ActiveScenario,
    ) -> dict:
        """
        PM checks in on a blocked ticket.

        Actions:
        1. Review the situation
        2. Add comment asking for update or offering help
        """
        developer_id = scenario.assigned_agent
        if not developer_id:
            return {"error": "No developer assigned"}

        dev_persona = self.get_persona(developer_id)
        team = dev_persona.get("team", "alpha")
        team_agents = self.get_team_agents(team)
        pm_id = team_agents.get("pm")

        if not pm_id:
            return {
                "action": "pm_check_on_blocker",
                "ticket": scenario.ticket_key,
                "result": "No PM configured",
                "skipped": True,
            }

        persona = self.get_persona(pm_id)
        agent = self.get_agent(pm_id, use_complex_llm=False)

        task = Task(
            description=f"""You are {persona['display_name']} (PM) checking on blocked ticket {scenario.ticket_key}.

Your task:
1. Use 'Get Issue Details' and 'Get Issue Comments' to understand the situation
2. Use 'Add Comment to Issue' to check in
   - Ask for a quick status update on the blocker
   - Offer to help if there's anything you can do
   - Keep it brief and supportive
   - 1-2 sentences

Your communication style: {persona.get('persona', '')}

Be supportive, not pushy. You're trying to help, not add pressure.
""",
            expected_output=f"PM check-in comment added to {scenario.ticket_key}",
            agent=agent,
        )

        result = self.execute_crew([agent], [task])

        return {
            "action": "pm_check_on_blocker",
            "ticket": scenario.ticket_key,
            "agent": pm_id,
            "result": result,
        }
