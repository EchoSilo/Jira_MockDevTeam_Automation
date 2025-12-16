"""
Scope Creep Crew - handles mid-sprint story injection.

Manages scope creep scenarios:
1. PM creates new urgent story mid-sprint
2. Priority discussions
3. Developer picks up (potentially causing overload)
"""

from typing import Optional
from crewai import Task

from .base_crew import BaseCrew
from ..state import ActiveScenario


class ScopeCreepCrew(BaseCrew):
    """Crew for handling scope creep / mid-sprint story creation."""

    def create_mid_sprint_story(
        self,
        pm_id: str,
        team: str,
        urgency_context: str,
    ) -> dict:
        """
        PM creates a new story mid-sprint due to urgent need.

        Actions:
        1. Create new story with urgency context
        2. Add comment explaining why it's being added mid-sprint
        """
        persona = self.get_persona(pm_id)
        agent = self.get_agent(pm_id, use_complex_llm=True)

        # Get team focus for context
        team_config = self.personas.get("teams", {}).get(team, {})
        team_focus = team_config.get("focus", "Product Development")

        task = Task(
            description=f"""You are {persona['display_name']} (PM) and need to add an urgent story mid-sprint.

Context for urgency: {urgency_context}
Team focus area: {team_focus}

Your task:
1. Use 'Get In Progress Issues' to see current sprint work
2. Use 'Create New Issue' to create a new Story:
   - Summary should be clear and actionable
   - Description should include:
     - Why this is urgent
     - Acceptance criteria (3-5 bullet points)
     - Any context about timing or priority
   - Set priority to 'High'
3. After creation, use 'Add Comment to Issue' on the new ticket:
   - Explain why this is being added mid-sprint
   - Acknowledge the impact on the team
   - 2-3 sentences

Your communication style: {persona.get('persona', '')}

The story should feel like a real urgent request - customer issue, critical bug discovery,
time-sensitive feature, etc. Be specific about the business need.
""",
            expected_output="New urgent story created with explanation",
            agent=agent,
        )

        result = self.execute_crew([agent], [task])

        return {
            "action": "create_mid_sprint_story",
            "agent": pm_id,
            "team": team,
            "urgency_context": urgency_context,
            "result": result,
        }

    def pm_prioritize_new_story(
        self,
        pm_id: str,
        ticket_key: str,
    ) -> dict:
        """
        PM adds priority context to a newly created story.

        Actions:
        1. Comment on ticket about priority relative to other work
        """
        persona = self.get_persona(pm_id)
        agent = self.get_agent(pm_id, use_complex_llm=True)

        task = Task(
            description=f"""You are {persona['display_name']} (PM) providing priority context for {ticket_key}.

Your task:
1. Use 'Get Issue Details' to see the ticket
2. Use 'Get In Progress Issues' to see what else the team is working on
3. Use 'Add Comment to Issue' to clarify priority:
   - Where this fits relative to current work
   - Any trade-offs being made
   - Who should pick this up (or let team self-select)
   - 2-3 sentences

Your communication style: {persona.get('persona', '')}

Be clear about priorities while respecting the team's ability to self-organize.
""",
            expected_output=f"Priority context added to {ticket_key}",
            agent=agent,
        )

        result = self.execute_crew([agent], [task])

        return {
            "action": "pm_prioritize_new_story",
            "ticket": ticket_key,
            "agent": pm_id,
            "result": result,
        }

    def tech_lead_review_scope(
        self,
        tech_lead_id: str,
        ticket_key: str,
    ) -> dict:
        """
        Tech lead reviews and comments on scope change.

        Actions:
        1. Add technical feasibility/impact comment
        """
        persona = self.get_persona(tech_lead_id)
        agent = self.get_agent(tech_lead_id, use_complex_llm=True)

        task = Task(
            description=f"""You are {persona['display_name']} (Tech Lead) reviewing new mid-sprint work {ticket_key}.

Your task:
1. Use 'Get Issue Details' to understand the new requirement
2. Use 'Get In Progress Issues' to see team capacity
3. Use 'Add Comment to Issue' with your technical assessment:
   - Brief feasibility assessment
   - Any technical considerations
   - Impact on current work or dependencies
   - 2-3 sentences

Your communication style: {persona.get('persona', '')}

Provide technical leadership - help the team understand the real effort and any concerns.
""",
            expected_output=f"Tech lead assessment added to {ticket_key}",
            agent=agent,
        )

        result = self.execute_crew([agent], [task])

        return {
            "action": "tech_lead_review_scope",
            "ticket": ticket_key,
            "agent": tech_lead_id,
            "result": result,
        }

    def developer_pickup_urgent(
        self,
        developer_id: str,
        ticket_key: str,
        has_existing_work: bool = False,
    ) -> dict:
        """
        Developer picks up the urgent story.

        Actions:
        1. Assign and transition to In Progress
        2. Add comment about taking on the work
        """
        persona = self.get_persona(developer_id)
        agent = self.get_agent(developer_id, use_complex_llm=False)

        existing_work_context = ""
        if has_existing_work:
            existing_work_context = """
Note: You already have other work in progress. Acknowledge this in your comment -
mention you'll balance this with your current work or that you're pausing something else.
"""

        task = Task(
            description=f"""You are {persona['display_name']} picking up urgent story {ticket_key}.

{existing_work_context}

Your task:
1. Use 'Get Issue Details' to see what the urgent work is
2. Use 'Assign Issue to User' to assign to your account ID: {persona['jira_account_id']}
3. Use 'Transition Issue Status' to move to 'In Progress'
4. Use 'Add Comment to Issue' to acknowledge:
   - That you're picking this up
   - Brief note about approach or timing (1-2 sentences)

Your communication style: {persona.get('persona', '')}

Show that you're responsive to urgent needs while being realistic about impact.
""",
            expected_output=f"Developer picked up urgent story {ticket_key}",
            agent=agent,
        )

        result = self.execute_crew([agent], [task])

        return {
            "action": "developer_pickup_urgent",
            "ticket": ticket_key,
            "agent": developer_id,
            "result": result,
        }
