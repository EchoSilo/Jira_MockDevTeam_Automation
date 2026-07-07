"""Tests for sync_state_with_jira active-sprint reconciliation.

These cover the "app is aware of the proper backlog state" behavior: scenario
tracking is scoped to the active sprint and reconciled (create / complete /
reassign / drop) against what Jira actually shows.
"""

from unittest.mock import Mock

from src.state import SimulationState
from src.state.models import ActiveScenario, TicketComplexity
from src.state.simulation_state import sync_state_with_jira


PERSONAS = {
    "agents": {
        "alpha_dev": {"jira_account_id": "acc-dev"},
        "alpha_qa": {"jira_account_id": "acc-qa"},
    }
}


def _issue(key, status="In Progress", issue_type="Story", account_id=None):
    issue = Mock()
    issue.key = key
    issue.fields.status.name = status
    issue.fields.issuetype.name = issue_type
    if account_id is None:
        issue.fields.assignee = None
    else:
        assignee = Mock()
        assignee.accountId = account_id
        issue.fields.assignee = assignee
    return issue


def _jira(active_sprint_id=100, sprint_issues=None):
    jira = Mock()
    jira.get_active_sprint.return_value = {"id": active_sprint_id, "name": "ESCRUM Sprint 10"}
    jira.get_sprint_issues.return_value = sprint_issues or []
    return jira


def test_creates_scenario_for_untracked_sprint_ticket():
    state = SimulationState()
    jira = _jira(sprint_issues=[_issue("ESCRUM-1", account_id="acc-dev")])

    sync_state_with_jira(state, jira, PERSONAS)

    scenario = state.get_scenario_by_ticket("ESCRUM-1")
    assert scenario is not None
    assert scenario.assigned_agent == "alpha_dev"
    assert "ESCRUM-1" in state.get_agent_state("alpha_dev").assigned_tickets
    # Scoped to the active sprint, not all active issues
    jira.get_sprint_issues.assert_called_once_with(100)


def test_drops_scenario_no_longer_in_active_sprint():
    state = SimulationState()
    scenario = ActiveScenario.create_normal_flow(
        ticket_key="ESCRUM-9",
        complexity=TicketComplexity.STORY,
        assigned_agent="alpha_dev",
    )
    state.add_scenario(scenario)
    state.get_agent_state("alpha_dev").assign_ticket("ESCRUM-9")

    # Jira's active sprint no longer contains ESCRUM-9 (moved to backlog / removed)
    jira = _jira(sprint_issues=[_issue("ESCRUM-1", account_id="acc-dev")])

    sync_state_with_jira(state, jira, PERSONAS)

    assert state.get_scenario_by_ticket("ESCRUM-9") is None
    assert "ESCRUM-9" not in state.get_agent_state("alpha_dev").assigned_tickets


def test_reconciles_reassignment():
    state = SimulationState()
    scenario = ActiveScenario.create_normal_flow(
        ticket_key="ESCRUM-2",
        complexity=TicketComplexity.STORY,
        assigned_agent="alpha_dev",
    )
    state.add_scenario(scenario)
    state.get_agent_state("alpha_dev").assign_ticket("ESCRUM-2")

    # Jira now shows ESCRUM-2 assigned to QA
    jira = _jira(sprint_issues=[_issue("ESCRUM-2", account_id="acc-qa")])

    sync_state_with_jira(state, jira, PERSONAS)

    updated = state.get_scenario_by_ticket("ESCRUM-2")
    assert updated.assigned_agent == "alpha_qa"
    assert "ESCRUM-2" in state.get_agent_state("alpha_qa").assigned_tickets
    assert "ESCRUM-2" not in state.get_agent_state("alpha_dev").assigned_tickets


def test_completes_done_ticket():
    state = SimulationState()
    scenario = ActiveScenario.create_normal_flow(
        ticket_key="ESCRUM-3",
        complexity=TicketComplexity.STORY,
        assigned_agent="alpha_dev",
    )
    state.add_scenario(scenario)

    jira = _jira(sprint_issues=[_issue("ESCRUM-3", status="Done", account_id="acc-dev")])

    sync_state_with_jira(state, jira, PERSONAS)

    assert state.get_scenario_by_ticket("ESCRUM-3") is None


def test_no_active_sprint_skips_removal_reconciliation():
    """Without an active sprint, fall back to legacy behavior and don't nuke tracking."""
    state = SimulationState()
    scenario = ActiveScenario.create_normal_flow(
        ticket_key="ESCRUM-7",
        complexity=TicketComplexity.STORY,
        assigned_agent="alpha_dev",
    )
    state.add_scenario(scenario)

    jira = Mock()
    jira.get_active_sprint.return_value = None
    jira.get_all_active_issues.return_value = []  # legacy path

    sync_state_with_jira(state, jira, PERSONAS)

    # Not dropped, because we had no sprint to scope against
    assert state.get_scenario_by_ticket("ESCRUM-7") is not None
    jira.get_all_active_issues.assert_called_once()
