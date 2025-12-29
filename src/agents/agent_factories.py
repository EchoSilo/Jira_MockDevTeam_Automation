"""
CrewAI Agent Factory Functions.

Creates CrewAI Agent instances from persona configurations.
Each agent type has specific roles, goals, and tool access.
"""

from crewai import Agent
from typing import Optional


def create_pm_agent(
    persona_config: dict,
    tools: list,
    llm: Optional[str] = None,
) -> Agent:
    """
    Create a Product Manager agent.

    PM agents create stories, manage backlog, and provide product direction.
    They do NOT delegate to other agents.
    """
    display_name = persona_config.get("display_name", "Product Manager")
    team = persona_config.get("team") or "unknown"  # Handle null team values
    persona = persona_config.get("persona", "")

    return Agent(
        role="Product Manager",
        goal=f"""Drive product development for Team {team.title()} by:
        - Creating clear, well-defined user stories with acceptance criteria
        - Prioritizing backlog based on business value and dependencies
        - Ensuring requirements are understood by the development team
        - Tracking progress and removing blockers
        - Communicating status and priorities clearly""",
        backstory=f"""You are {display_name}, a Product Manager.

{persona}

You communicate in Jira through comments and ticket creation.
Your comments should be concise, professional, and actionable.
Focus on user value and business outcomes in your communication.""",
        tools=tools,
        llm=llm,
        verbose=False,
        allow_delegation=False,
        max_iter=5,
        max_rpm=10,
    )


def create_developer_agent(
    persona_config: dict,
    tools: list,
    llm: Optional[str] = None,
) -> Agent:
    """
    Create a Developer agent.

    Developer agents pick up tasks, write code, transition statuses,
    and communicate progress. Seniority affects behavior.
    """
    display_name = persona_config.get("display_name", "Developer")
    team = persona_config.get("team") or "unknown"  # Handle null team values
    seniority = persona_config.get("seniority") or "mid"  # Handle null seniority
    persona = persona_config.get("persona", "")

    seniority_context = {
        "junior": """You are still learning and sometimes need guidance.
        You ask clarifying questions when requirements are unclear.
        You may occasionally need rework after code review or QA.""",
        "mid": """You have solid experience and work independently on most tasks.
        You ask questions when facing novel challenges.
        You provide good documentation and clear status updates.""",
        "senior": """You are highly experienced and mentor others.
        You complete work efficiently with minimal rework.
        You proactively identify technical risks and dependencies.""",
    }

    return Agent(
        role=f"Software Developer ({seniority.title()})",
        goal=f"""Execute development work effectively by:
        - Picking up tasks appropriate to your skill level
        - Transitioning tickets through workflow states accurately
        - Providing clear progress updates and technical context
        - Asking clarifying questions when requirements are unclear
        - Logging work time appropriately""",
        backstory=f"""You are {display_name}, a {seniority} developer on Team {team.title()}.

{persona}

{seniority_context.get(seniority, seniority_context['mid'])}

Your Jira comments should be brief and technical.
Focus on what you're doing, blockers encountered, and progress made.""",
        tools=tools,
        llm=llm,
        verbose=False,
        allow_delegation=False,
        max_iter=5,
        max_rpm=10,
    )


def create_qa_agent(
    persona_config: dict,
    tools: list,
    llm: Optional[str] = None,
) -> Agent:
    """
    Create a QA Engineer agent.

    QA agents test tickets, approve or reject work, document test cases,
    and create bug reports when issues are found.
    """
    display_name = persona_config.get("display_name", "QA Engineer")
    team = persona_config.get("team") or "unknown"  # Handle null team values
    persona = persona_config.get("persona", "")

    return Agent(
        role="QA Engineer",
        goal=f"""Ensure quality of Team {team.title()}'s deliverables by:
        - Testing tickets against acceptance criteria
        - Approving work that meets quality standards
        - Rejecting work with clear, actionable feedback when issues found
        - Documenting test scenarios and edge cases
        - Creating detailed bug reports when defects discovered""",
        backstory=f"""You are {display_name}, a QA Engineer on Team {team.title()}.

{persona}

You are thorough and detail-oriented in your testing.
When rejecting work, provide specific reproduction steps.
When approving, confirm which criteria were verified.
Your goal is quality, not being a gatekeeper.""",
        tools=tools,
        llm=llm,
        verbose=False,
        allow_delegation=False,
        max_iter=5,
        max_rpm=10,
    )


def create_tech_lead_agent(
    persona_config: dict,
    tools: list,
    llm: Optional[str] = None,
) -> Agent:
    """
    Create a Tech Lead agent.

    Tech Lead agents review code, provide architectural guidance,
    identify technical risks, and mentor team members.
    """
    display_name = persona_config.get("display_name", "Tech Lead")
    team = persona_config.get("team") or "unknown"  # Handle null team values
    persona = persona_config.get("persona", "")

    return Agent(
        role="Tech Lead",
        goal=f"""Provide technical leadership for Team {team.title()} by:
        - Reviewing code and providing constructive feedback
        - Offering architectural guidance and design direction
        - Identifying technical risks and dependencies early
        - Mentoring developers through helpful comments
        - Ensuring technical quality and consistency""",
        backstory=f"""You are {display_name}, Tech Lead for Team {team.title()}.

{persona}

You balance quality with pragmatism.
Your code review feedback is specific and educational.
You raise concerns early before they become blockers.
You help developers grow through thoughtful guidance.""",
        tools=tools,
        llm=llm,
        verbose=False,
        allow_delegation=False,
        max_iter=5,
        max_rpm=10,
    )


# ============ Agent Factory Registry ============

AGENT_FACTORIES = {
    "pm": create_pm_agent,
    "developer": create_developer_agent,
    "qa": create_qa_agent,
    "tech_lead": create_tech_lead_agent,
}


def create_agent(
    role: str,
    persona_config: dict,
    tools: list,
    llm: Optional[str] = None,
) -> Agent:
    """
    Create an agent of the specified role.

    Args:
        role: Agent role ("pm", "developer", "qa", "tech_lead")
        persona_config: Configuration dict from personas.yaml
        tools: List of CrewAI tools the agent can use
        llm: Optional LLM model string (e.g., "claude-3-haiku-20240307")

    Returns:
        CrewAI Agent instance
    """
    factory = AGENT_FACTORIES.get(role)
    if not factory:
        raise ValueError(f"Unknown agent role: {role}. Valid roles: {list(AGENT_FACTORIES.keys())}")

    return factory(persona_config, tools, llm)


def get_agent_display_info(persona_config: dict) -> dict:
    """Extract display information from persona config."""
    return {
        "id": persona_config.get("id", "unknown"),
        "display_name": persona_config.get("display_name", "Unknown"),
        "team": persona_config.get("team") or "unknown",  # Handle null team values
        "role": persona_config.get("role", "developer"),
        "seniority": persona_config.get("seniority"),
        "jira_account_id": persona_config.get("jira_account_id"),
    }
