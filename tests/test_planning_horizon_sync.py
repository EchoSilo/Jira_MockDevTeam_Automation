"""Tests for _sync_planning_horizon_from_jira reading real sprint contents.

Covers the reconciliation gap where the planning horizon was rebuilt from
Jira's future sprints but always zeroed committed_items/committed_points,
discarding whatever the sprint actually had committed in Jira.
"""

from unittest.mock import Mock

import pendulum

from src.main import (
    _sync_planning_horizon_from_jira,
    _update_predicted_spillover,
    _should_run_sprint_planning,
)
from src.state import SimulationState


def _issue(key, points, issue_type="Story", status="To Do"):
    issue = Mock()
    issue.key = key
    issue.fields.customfield_10016 = points
    issue.fields.issuetype.name = issue_type
    issue.fields.status.name = status
    return issue


def _jira(future_sprints, sprint_issues_by_id=None):
    jira = Mock()
    jira.get_future_sprints.return_value = future_sprints
    sprint_issues_by_id = sprint_issues_by_id or {}
    jira.get_sprint_issues.side_effect = lambda sprint_id: sprint_issues_by_id.get(sprint_id, [])
    return jira


def test_sync_reads_committed_items_and_points_from_jira():
    jira = _jira(
        future_sprints=[
            {
                "id": 11,
                "name": "ESCRUM Sprint 11",
                "start_date": "2026-07-08T00:00:00.000Z",
                "end_date": "2026-07-21T23:59:59.000Z",
            }
        ],
        sprint_issues_by_id={
            11: [_issue("ESCRUM-101", 5), _issue("ESCRUM-102", 3)],
        },
    )
    state = SimulationState()

    _sync_planning_horizon_from_jira(state, jira, target_sprints=3)

    horizon = state.get_planning_horizon()
    assert len(horizon.future_sprints) == 1
    plan = horizon.future_sprints[0]
    assert plan.sprint_number == 11
    assert set(plan.committed_items) == {"ESCRUM-101", "ESCRUM-102"}
    assert plan.committed_points == 8


def test_sync_reflects_genuinely_empty_sprint():
    """A future sprint that exists in Jira but has no issues yet stays at 0
    points - this is the exact case that previously reported phantom points."""
    jira = _jira(
        future_sprints=[
            {
                "id": 11,
                "name": "ESCRUM Sprint 11",
                "start_date": "2026-07-08T00:00:00.000Z",
                "end_date": "2026-07-21T23:59:59.000Z",
            }
        ],
        sprint_issues_by_id={11: []},
    )
    state = SimulationState()

    _sync_planning_horizon_from_jira(state, jira, target_sprints=3)

    plan = state.get_planning_horizon().future_sprints[0]
    assert plan.committed_items == []
    assert plan.committed_points == 0


def test_sync_sets_scenario_id_from_real_jira_sprint_id():
    """Every synced future sprint must carry its real Jira sprint id (as a
    str, matching SprintPlan.scenario_id's type) so top_up_future_sprints can
    later add items to the correct existing sprint."""
    jira = _jira(
        future_sprints=[
            {
                "id": 211,
                "name": "ESCRUM Sprint 11",
                "start_date": "2026-07-19T04:00:00.000Z",
                "end_date": "2026-08-02T04:00:00.000Z",
            }
        ],
        sprint_issues_by_id={211: []},
    )
    state = SimulationState()

    _sync_planning_horizon_from_jira(state, jira, target_sprints=3)

    plan = state.get_planning_horizon().future_sprints[0]
    assert plan.scenario_id == "211"
    # Must round-trip through save/reload without a pydantic ValidationError
    # (the str/int landmine this regression test guards against).
    state.set_planning_horizon(state.get_planning_horizon())
    reloaded = state.get_planning_horizon()
    assert reloaded.future_sprints[0].scenario_id == "211"


def test_sync_uses_estimated_points_when_real_points_missing():
    """Real story points are null on most backlog issues in this project -
    committed_points must fall back to the type-based estimate instead of
    silently reading 0 for a sprint that visibly has real items."""
    jira = _jira(
        future_sprints=[
            {
                "id": 212,
                "name": "ESCRUM Sprint 12",
                "start_date": "2026-08-02T00:00:00.000Z",
                "end_date": "2026-08-16T23:59:59.000Z",
            }
        ],
        sprint_issues_by_id={
            212: [
                _issue("ESCRUM-201", None, issue_type="Task"),   # estimate: 3
                _issue("ESCRUM-202", 0, issue_type="Bug"),       # estimate: 2
            ],
        },
    )
    state = SimulationState()

    _sync_planning_horizon_from_jira(state, jira, target_sprints=3)

    plan = state.get_planning_horizon().future_sprints[0]
    assert set(plan.committed_items) == {"ESCRUM-201", "ESCRUM-202"}
    assert plan.committed_points == 5  # 3 (Task) + 2 (Bug) estimated


def test_sync_tolerates_sprint_issue_fetch_errors():
    """A Jira error reading one sprint's issues shouldn't blow up the sync -
    it should just leave that sprint's committed data empty."""
    jira = _jira(
        future_sprints=[
            {
                "id": 11,
                "name": "ESCRUM Sprint 11",
                "start_date": "2026-07-08T00:00:00.000Z",
                "end_date": "2026-07-21T23:59:59.000Z",
            }
        ],
    )
    jira.get_sprint_issues.side_effect = Exception("Jira API error")
    state = SimulationState()

    _sync_planning_horizon_from_jira(state, jira, target_sprints=3)

    plan = state.get_planning_horizon().future_sprints[0]
    assert plan.committed_items == []
    assert plan.committed_points == 0


def _active_sprint_jira(issues, days_elapsed, total_days=14):
    """A jira client mock with an active sprint `days_elapsed` days into a
    `total_days`-day sprint, holding the given issues."""
    jira = Mock()
    start = pendulum.now("UTC").subtract(days=days_elapsed)
    end = start.add(days=total_days)
    jira.get_active_sprint.return_value = {
        "id": 99,
        "name": "ESCRUM Sprint 9",
        "start_date": start.to_iso8601_string(),
        "end_date": end.to_iso8601_string(),
    }
    jira.get_sprint_issues.return_value = issues
    return jira


class TestPredictedSpillover:
    """Tests for _update_predicted_spillover - the burndown-pace-based
    early-warning discount future sprint capacity is reduced by."""

    def test_behind_pace_sprint_flags_at_risk_points(self):
        """Halfway through a 14-day, 20-point sprint with almost nothing
        done should flag a meaningful chunk of points at risk."""
        issues = [_issue(f"ESCRUM-{i}", 5, status="To Do") for i in range(4)]  # 20 pts, all open
        jira = _active_sprint_jira(issues, days_elapsed=7, total_days=14)
        state = SimulationState()

        _update_predicted_spillover(state, jira)

        # Ideal remaining at day 7/14 is ~10 pts; actual remaining is 20 -> ~10 at risk.
        assert state.get_planning_horizon().predicted_spillover_points > 0

    def test_on_pace_sprint_flags_no_risk(self):
        """A sprint that's completed proportionally to elapsed time is not at risk."""
        issues = [
            _issue("ESCRUM-1", 5, status="Done"),
            _issue("ESCRUM-2", 5, status="Done"),
            _issue("ESCRUM-3", 5, status="To Do"),
            _issue("ESCRUM-4", 5, status="To Do"),
        ]  # 20 pts total, half done at the halfway point
        jira = _active_sprint_jira(issues, days_elapsed=7, total_days=14)
        state = SimulationState()

        _update_predicted_spillover(state, jira)

        assert state.get_planning_horizon().predicted_spillover_points == 0

    def test_day_zero_never_flags_false_risk(self):
        """A sprint that just started has 100% of ideal capacity remaining -
        even with nothing done yet, this must not flag risk."""
        issues = [_issue(f"ESCRUM-{i}", 5, status="To Do") for i in range(4)]
        jira = _active_sprint_jira(issues, days_elapsed=0, total_days=14)
        state = SimulationState()

        _update_predicted_spillover(state, jira)

        assert state.get_planning_horizon().predicted_spillover_points == 0

    def test_no_active_sprint_defaults_to_zero_without_crashing(self):
        jira = Mock()
        jira.get_active_sprint.return_value = None
        state = SimulationState()

        _update_predicted_spillover(state, jira)  # must not raise

        assert state.get_planning_horizon().predicted_spillover_points == 0

    def test_missing_dates_defaults_to_zero_without_crashing(self):
        jira = Mock()
        jira.get_active_sprint.return_value = {"id": 99, "name": "Sprint 9"}
        state = SimulationState()

        _update_predicted_spillover(state, jira)  # must not raise

        assert state.get_planning_horizon().predicted_spillover_points == 0

    def test_value_is_overwritten_not_accumulated(self):
        """Calling this repeatedly must reflect current risk, not a running sum."""
        behind_issues = [_issue(f"ESCRUM-{i}", 5, status="To Do") for i in range(4)]
        jira_behind = _active_sprint_jira(behind_issues, days_elapsed=7, total_days=14)
        state = SimulationState()

        _update_predicted_spillover(state, jira_behind)
        first_value = state.get_planning_horizon().predicted_spillover_points
        assert first_value > 0

        _update_predicted_spillover(state, jira_behind)
        second_value = state.get_planning_horizon().predicted_spillover_points

        assert second_value == first_value  # not doubled


class TestShouldRunSprintPlanning:
    """Tests for the once-per-sprint gate."""

    def test_true_when_never_planned(self):
        state = SimulationState()
        assert _should_run_sprint_planning(state) is True

    def test_false_after_marking_current_sprint_planned(self):
        state = SimulationState()
        state.last_planned_for_sprint = state.sprint.sprint_number
        assert _should_run_sprint_planning(state) is False

    def test_true_again_after_sprint_number_changes(self):
        """Simulates a rollover: sprint_number is a read-only property derived
        from the injected Jira sprint name, so advance it the same way a
        real rollover would - by injecting the new active sprint."""
        state = SimulationState()
        state.sprint.inject_jira_sprint({
            "name": "ESCRUM Sprint 9",
            "start_date": "2026-07-01T00:00:00.000Z",
            "end_date": "2026-07-14T23:59:59.000Z",
        })
        state.last_planned_for_sprint = state.sprint.sprint_number
        assert _should_run_sprint_planning(state) is False

        state.sprint.inject_jira_sprint({
            "name": "ESCRUM Sprint 10",
            "start_date": "2026-07-15T00:00:00.000Z",
            "end_date": "2026-07-28T23:59:59.000Z",
        })
        assert _should_run_sprint_planning(state) is True
