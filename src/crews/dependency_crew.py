"""
Dependency Crew - handles cross-team dependency scenarios.

Manages dependency lifecycle:
1. Developer identifies dependency on another team
2. Cross-team communication
3. Dependency resolution
"""

from typing import Optional
from crewai import Task

from .base_crew import BaseCrew
from ..state import ActiveScenario


class DependencyCrew(BaseCrew):
    """Crew for handling cross-team dependency scenarios."""

    def identify_dependency(
        self,
        scenario: ActiveScenario,
        dependency_ticket: str,
        dependency_team: str,
    ) -> dict:
        """
        Developer identifies a dependency on another team's work.

        Actions:
        1. Add comment explaining the dependency
        2. Link to the blocking ticket (if possible)
        """
        developer_id = scenario.assigned_agent
        if not developer_id:
            return {"error": "No developer assigned"}

        persona = self.get_persona(developer_id)
        agent = self.get_agent(developer_id, use_complex_llm=True)

        task = Task(
            description=f"""You are {persona['display_name']} and you've discovered a dependency.

Your ticket: {scenario.ticket_key}
Dependent on: {dependency_ticket} from Team {dependency_team.title()}

Your task:
1. Use 'Get Issue Details' on your ticket to understand the context
2. Use 'Get Issue Details' on {dependency_ticket} to see its status
3. Use 'Add Comment to Issue' on {scenario.ticket_key} to explain:
   - What the dependency is
   - Why you're blocked on the other team's work
   - Any technical context that helps
   - 2-3 sentences
4. Try 'Link Issues' to create a "is blocked by" link to {dependency_ticket}

Your communication style: {persona.get('persona', '')}

Be clear about the dependency without being demanding. This is normal cross-team coordination.
""",
            expected_output=f"Dependency identified and documented on {scenario.ticket_key}",
            agent=agent,
        )

        result = self.execute_crew([agent], [task])

        return {
            "action": "identify_dependency",
            "ticket": scenario.ticket_key,
            "dependency_ticket": dependency_ticket,
            "dependency_team": dependency_team,
            "agent": developer_id,
            "result": result,
        }

    def pm_coordinate_dependency(
        self,
        scenario: ActiveScenario,
        dependency_ticket: str,
        dependency_team: str,
    ) -> dict:
        """
        PM reaches out about the cross-team dependency.

        Actions:
        1. Add coordinating comment on both tickets
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
                "action": "pm_coordinate_dependency",
                "ticket": scenario.ticket_key,
                "result": "No PM configured",
                "skipped": True,
            }

        persona = self.get_persona(pm_id)
        agent = self.get_agent(pm_id, use_complex_llm=True)

        task = Task(
            description=f"""You are {persona['display_name']} (PM) coordinating a cross-team dependency.

Your team's ticket: {scenario.ticket_key}
Depends on: {dependency_ticket} from Team {dependency_team.title()}

Your task:
1. Use 'Get Issue Details' on both tickets
2. Use 'Get Issue Comments' on {dependency_ticket} to see its status
3. Use 'Add Comment to Issue' on {dependency_ticket}:
   - Politely flag that your team is waiting on this
   - Ask for an ETA or status update
   - 2-3 sentences, professional and collaborative
4. Use 'Add Comment to Issue' on {scenario.ticket_key}:
   - Note that you've reached out to the other team
   - 1 sentence is enough

Your communication style: {persona.get('persona', '')}

Be collaborative, not demanding. Cross-team coordination requires diplomacy.
""",
            expected_output=f"PM coordination comments added to both tickets",
            agent=agent,
        )

        result = self.execute_crew([agent], [task])

        return {
            "action": "pm_coordinate_dependency",
            "ticket": scenario.ticket_key,
            "dependency_ticket": dependency_ticket,
            "agent": pm_id,
            "result": result,
        }

    def other_team_responds(
        self,
        dependency_ticket: str,
        responding_team: str,
        response_context: str,
    ) -> dict:
        """
        Someone from the other team responds about the dependency.

        Actions:
        1. Add response comment on the dependency ticket
        """
        # Find someone from the other team to respond
        other_team_agents = self.get_team_agents(responding_team)

        # Prefer PM or tech lead for cross-team communication
        responder_id = other_team_agents.get("pm") or other_team_agents.get("tech_lead")
        if not responder_id and other_team_agents.get("developer"):
            responder_id = other_team_agents["developer"][0]

        if not responder_id:
            return {
                "action": "other_team_responds",
                "ticket": dependency_ticket,
                "result": f"No one from team {responding_team} available",
                "skipped": True,
            }

        persona = self.get_persona(responder_id)
        agent = self.get_agent(responder_id, use_complex_llm=False)

        task = Task(
            description=f"""You are {persona['display_name']} from Team {responding_team.title()} responding to a dependency request on {dependency_ticket}.

Context: {response_context}

Your task:
1. Use 'Get Issue Comments' to see what was asked
2. Use 'Add Comment to Issue' to respond:
   - Acknowledge the dependency/request
   - Provide status or timeline info
   - Be helpful and transparent
   - 2-3 sentences

Your communication style: {persona.get('persona', '')}

Be helpful - you're responding to another team's legitimate need.
""",
            expected_output=f"Response added to {dependency_ticket}",
            agent=agent,
        )

        result = self.execute_crew([agent], [task])

        return {
            "action": "other_team_responds",
            "ticket": dependency_ticket,
            "agent": responder_id,
            "result": result,
        }

    def resolve_dependency(
        self,
        scenario: ActiveScenario,
        resolution_note: str,
    ) -> dict:
        """
        Developer notes the dependency is resolved and continues work.

        Actions:
        1. Add resolution comment
        2. Resume work (transition back to In Progress if needed)
        """
        developer_id = scenario.assigned_agent
        if not developer_id:
            return {"error": "No developer assigned"}

        persona = self.get_persona(developer_id)
        agent = self.get_agent(developer_id, use_complex_llm=False)

        task = Task(
            description=f"""You are {persona['display_name']} and the dependency on {scenario.ticket_key} is now resolved.

Resolution: {resolution_note}

Your task:
1. Use 'Add Comment to Issue' to note the resolution:
   - Briefly explain what was resolved
   - Note you're resuming work
   - Thank the other team (briefly)
   - 1-2 sentences
2. Use 'Transition Issue Status' to 'In Progress' if needed

Your communication style: {persona.get('persona', '')}

Keep it brief and positive - the blocker is cleared, time to execute.
""",
            expected_output=f"Dependency resolved on {scenario.ticket_key}, work resumed",
            agent=agent,
        )

        result = self.execute_crew([agent], [task])

        return {
            "action": "resolve_dependency",
            "ticket": scenario.ticket_key,
            "agent": developer_id,
            "result": result,
        }
