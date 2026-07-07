"""Integration tests for sprint planning flow."""

import pytest
from unittest.mock import Mock, MagicMock
import pendulum

from src.planning import (
    SprintPlanner, SprintPlan, PlanningHorizon, VelocityTracker,
)
from src.state import SimulationState


@pytest.fixture
def mock_jira():
    """Create mock Jira client."""
    jira = Mock()
    # Mock backlog items
    mock_issue = Mock()
    mock_issue.key = "PROJ-100"
    mock_issue.fields.issuetype.name = "Story"
    mock_issue.fields.summary = "Test story"
    mock_issue.fields.priority.name = "Medium"
    mock_issue.fields.customfield_10016 = 5  # Story points
    jira.get_issues_not_in_sprint.return_value = [mock_issue]
    jira.create_sprint.return_value = {"id": "123", "name": "Sprint 8"}
    return jira


@pytest.fixture
def mock_llm():
    """Create mock LLM service."""
    llm = Mock()
    llm.generate.return_value = '["PROJ-100"]'
    return llm


@pytest.fixture
def mock_scheduler(tmp_path):
    """Create mock scheduler."""
    from src.scheduling import Scheduler
    from src.scheduling.persistence import ScheduledActionStore
    from src.scheduling.virtual_clock import VirtualClock

    store = ScheduledActionStore(str(tmp_path / "scheduler.db"))
    clock = VirtualClock(pendulum.datetime(2026, 2, 4, 10, 0, tz="UTC"))
    return Scheduler(store=store, virtual_clock=clock)


@pytest.fixture
def settings():
    """Create test settings."""
    return {
        "sprint": {
            "duration_days": 7,
            "start_day": "wednesday",
            "planning_horizon_sprints": 3,
            "capacity_buffer": 0.8,
        }
    }


@pytest.fixture
def personas():
    """A full alpha team roster for agent-assignment tests."""
    return {
        "agents": {
            "alpha_pm": {"team": "alpha", "role": "pm"},
            "alpha_tl": {"team": "alpha", "role": "tech_lead"},
            "alpha_dev1": {"team": "alpha", "role": "developer"},
            "alpha_dev2": {"team": "alpha", "role": "developer"},
            "alpha_qa": {"team": "alpha", "role": "qa"},
        }
    }


class TestSprintPlanner:
    """Test suite for SprintPlanner orchestration."""

    def test_check_and_plan_when_needed(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        """Test that planning triggers when horizon is low."""
        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)
        state = SimulationState()  # Empty horizon = needs planning

        result = planner.check_and_plan(state, pm_agent_id="pm_alpha")

        assert result is not None
        assert result["success"] is True

    def test_no_planning_when_horizon_sufficient(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        """Test that planning skips when horizon is sufficient."""
        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)

        # Create state with sufficient horizon (default target is 3 sprints)
        state = SimulationState()
        horizon = PlanningHorizon()
        for n, offset in ((8, 7), (9, 14), (10, 21)):
            horizon.add_sprint_plan(SprintPlan(
                sprint_number=n,
                start_date=pendulum.now("UTC").add(days=offset),
                end_date=pendulum.now("UTC").add(days=offset + 7),
            ))
        state.set_planning_horizon(horizon)

        result = planner.check_and_plan(state, pm_agent_id="pm_alpha")

        assert result is None  # No planning needed

    def test_plan_next_sprint_creates_plan(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        """Test that planning creates a sprint plan."""
        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)
        state = SimulationState()

        result = planner.plan_next_sprint(state, pm_agent_id="pm_alpha")

        assert result["success"] is True
        assert result["sprint_plan"] is not None
        assert result["actions_scheduled"] > 0

    def test_plan_updates_state(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        """Test that planning updates simulation state."""
        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)
        state = SimulationState()

        planner.plan_next_sprint(state, pm_agent_id="pm_alpha")

        horizon = state.get_planning_horizon()
        assert horizon.get_sprint_count() >= 1

    def test_cadence_and_naming_derived_from_active_sprint(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        """Future sprint chains off the active sprint's dates and matches its naming."""
        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)
        state = SimulationState()
        # Active board sprint: ESCRUM Sprint 10, 14-day, Mon Jul 6 -> Sun Jul 19
        state.sprint.inject_jira_sprint({
            "name": "ESCRUM Sprint 10",
            "start_date": "2026-07-06T00:00:00.000Z",
            "end_date": "2026-07-19T23:59:59.000Z",
        })

        result = planner.plan_next_sprint(state, pm_agent_id="pm_alpha")

        plan_data = result["sprint_plan"]
        start_date = pendulum.parse(plan_data["start_date"])
        end_date = pendulum.parse(plan_data["end_date"])
        # Starts the day after the active sprint ends (Jul 20)
        assert start_date.date().isoformat() == "2026-07-20"
        # Same 14-day cadence as the active sprint
        assert (end_date.date() - start_date.date()).days + 1 == 14
        # Naming matches the board prefix + next number
        assert result["sprint_name"] == "ESCRUM Sprint 11"

    def test_plan_populates_jira_sprint_with_items(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        """plan_next_sprint must ADD committed items to the created Jira sprint."""
        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)
        state = SimulationState()

        result = planner.plan_next_sprint(state, pm_agent_id="pm_alpha")

        committed = result["sprint_plan"]["committed_items"]
        assert committed  # something was selected
        # add_issue_to_sprint was called for the committed item(s)
        assert mock_jira.add_issue_to_sprint.called
        added_keys = {
            call.args[1][0] for call in mock_jira.add_issue_to_sprint.call_args_list
        }
        assert set(committed).issubset(added_keys)
        assert result["items_added"] >= 1

    def test_scenario_id_coerced_to_string_for_int_jira_ids(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        """Real Jira sprint ids are ints; SprintPlan.scenario_id is typed str.
        Assigning the int directly used to succeed silently until the next
        state.get_planning_horizon() pydantic round-trip raised a
        ValidationError. Regression test for that landmine."""
        mock_jira.create_sprint.return_value = {"id": 123, "name": "Sprint 8"}
        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)
        state = SimulationState()

        result = planner.plan_next_sprint(state, pm_agent_id="pm_alpha")

        assert result["success"] is True
        # Must not raise - this is the exact round-trip that used to crash.
        horizon = state.get_planning_horizon()
        assert horizon.future_sprints[0].scenario_id == "123"

    def test_plan_skips_horizon_when_jira_sprint_creation_fails(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        """If Jira sprint creation fails, nothing is persisted as committed."""
        mock_jira.create_sprint.side_effect = Exception("Jira API error")
        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)
        state = SimulationState()

        result = planner.plan_next_sprint(state, pm_agent_id="pm_alpha")

        assert result["success"] is False
        assert result["sprint_plan"] is None
        assert state.get_planning_horizon().get_sprint_count() == 0

    def test_plan_records_only_confirmed_items_when_population_fails(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        """If add_issue_to_sprint fails for every item, committed_points/items
        must reflect that (empty), not the full aspirational selection."""
        mock_jira.add_issue_to_sprint.return_value = False
        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)
        state = SimulationState()

        result = planner.plan_next_sprint(state, pm_agent_id="pm_alpha")

        assert result["success"] is True
        assert result["items_added"] == 0
        plan = result["sprint_plan"]
        assert plan["committed_items"] == []
        assert plan["committed_points"] == 0

    def test_plan_to_horizon_stops_on_repeated_jira_failure(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        """plan_to_horizon must not keep fabricating sprint plans across
        iterations once Jira sprint creation is failing outright."""
        mock_jira.create_sprint.side_effect = Exception("Jira API error")
        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)
        state = SimulationState()

        result = planner.plan_to_horizon(state, "pm_alpha", target_sprints=3)

        assert result["sprints_planned"] == 1  # breaks after the first failure
        assert state.get_planning_horizon().get_sprint_count() == 0

    def test_plan_to_horizon_reaches_target(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        """plan_to_horizon tops the board up to the configured future-sprint count."""
        # Provide enough distinct backlog so each future sprint gets an item
        issues = []
        for i in range(6):
            issue = Mock()
            issue.key = f"PROJ-{200+i}"
            issue.fields.issuetype.name = "Story"
            issue.fields.summary = f"Story {i}"
            issue.fields.priority.name = "Medium"
            issue.fields.customfield_10016 = 3
            issues.append(issue)
        mock_jira.get_issues_not_in_sprint.return_value = issues

        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)
        state = SimulationState()

        result = planner.plan_to_horizon(state, "pm_alpha", target_sprints=3)

        assert result["sprints_planned"] == 3
        assert state.get_planning_horizon().get_sprint_count() == 3

    def test_velocity_affects_capacity(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        """Test that velocity history affects capacity."""
        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)
        state = SimulationState()

        # Set up velocity history
        velocity = VelocityTracker()
        velocity.record_sprint(5, 25, 20)
        velocity.record_sprint(6, 25, 25)
        velocity.record_sprint(7, 25, 24)
        state.set_velocity_tracker(velocity)

        result = planner.plan_next_sprint(state, pm_agent_id="pm_alpha")

        # Capacity should be ~80% of avg velocity (~23) = ~18
        # This affects which items are selected
        assert result["success"] is True

    def test_record_sprint_completion(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        """Test recording sprint completion."""
        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)
        state = SimulationState()

        planner.record_sprint_completion(
            state,
            sprint_number=7,
            committed=20,
            completed=18,
        )

        velocity = state.get_velocity_tracker()
        assert len(velocity.sprint_history) == 1
        assert velocity.sprint_history[0].completed == 18

    def _scenario_actions(self, scheduler):
        """Return lifecycle actions (those tagged with a scenario_id)."""
        return [a for a in scheduler.queue._heap if a.scenario_id]

    def test_scheduled_steps_get_real_agents_and_wide_window(
        self, mock_jira, mock_llm, mock_scheduler, settings, personas
    ):
        """Every scheduled lifecycle step is owned by a real agent (never '')
        with a wide execution window, and roles map sensibly."""
        planner = SprintPlanner(
            mock_jira, mock_llm, mock_scheduler, settings, personas=personas
        )
        state = SimulationState()

        planner.plan_next_sprint(state, pm_agent_id="alpha_pm")

        actions = self._scenario_actions(mock_scheduler)
        assert actions, "lifecycle steps should have been scheduled"

        by_type = {a.action_type: a for a in actions}
        # No ownerless steps
        assert all(a.agent_id for a in actions)
        # Wide window (config default 480), not the fragile 30
        assert all(a.window_minutes == 480 for a in actions)
        # Role mapping
        assert by_type["pick_up_task"].agent_id in {"alpha_dev1", "alpha_dev2"}
        # Same dev carries pick-up through progress
        assert by_type["progress_to_review"].agent_id == by_type["pick_up_task"].agent_id
        assert by_type["complete_review"].agent_id == "alpha_tl"
        assert by_type["qa_approve"].agent_id == "alpha_qa"

    def test_scheduled_steps_never_ownerless_without_personas(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        """With no roster, steps fall back to the PM id rather than empty string."""
        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)
        state = SimulationState()

        planner.plan_next_sprint(state, pm_agent_id="alpha_pm")

        actions = self._scenario_actions(mock_scheduler)
        assert actions
        assert all(a.agent_id == "alpha_pm" for a in actions)

    def test_plan_to_horizon_triggers_on_short_runway(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        """Even at the target count, a near-term runway (< 14 days) plans more."""
        # 3 planned sprints, all ending within 14 days -> runway gate should fire.
        state = SimulationState()
        horizon = PlanningHorizon()
        for n, offset in ((8, 1), (9, 3), (10, 5)):
            horizon.add_sprint_plan(SprintPlan(
                sprint_number=n,
                start_date=pendulum.now("UTC").add(days=offset),
                end_date=pendulum.now("UTC").add(days=offset + 2),
            ))
        state.set_planning_horizon(horizon)

        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)
        result = planner.plan_to_horizon(state, "alpha_pm", target_sprints=3)

        # Count already met, but the runway gate forces at least one more sprint.
        assert result["sprints_planned"] >= 1

    def test_fallback_prioritization(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        """Test fallback prioritization when LLM unavailable."""
        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)

        backlog = [
            {"key": "PROJ-101", "type": "Story"},
            {"key": "PROJ-102", "type": "Bug"},
            {"key": "PROJ-103", "type": "Task"},
        ]

        prioritized = planner._fallback_prioritize(backlog)

        # Bug should be first
        assert prioritized[0]["key"] == "PROJ-102"
        assert prioritized[0]["type"] == "Bug"

    def test_multiple_items_selected(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        """Test that multiple items are selected within capacity."""
        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)

        # Create multiple mock issues
        issues = []
        for i in range(5):
            issue = Mock()
            issue.key = f"PROJ-{100+i}"
            issue.fields.issuetype.name = "Story"
            issue.fields.summary = f"Story {i}"
            issue.fields.priority.name = "Medium"
            issue.fields.customfield_10016 = 3  # 3 points each
            issues.append(issue)

        mock_jira.get_issues_not_in_sprint.return_value = issues
        state = SimulationState()

        result = planner.plan_next_sprint(state, pm_agent_id="pm_alpha")

        assert result["success"] is True
        # Should select multiple items (capacity defaults to 20 for new team)
        plan = result["sprint_plan"]
        assert len(plan["committed_items"]) > 1


def _existing_future_sprint(sprint_number, scenario_id, offset_days=7):
    """A PLANNED future sprint that already exists on the board (scenario_id
    set) with no committed items yet - the shape top_up_future_sprints acts on."""
    return SprintPlan(
        sprint_number=sprint_number,
        start_date=pendulum.now("UTC").add(days=offset_days),
        end_date=pendulum.now("UTC").add(days=offset_days + 13),
        scenario_id=scenario_id,
    )


def _backlog_issues(n, points=5, prefix="PROJ-2"):
    issues = []
    for i in range(n):
        issue = Mock()
        issue.key = f"{prefix}{i}"
        issue.fields.issuetype.name = "Story"
        issue.fields.summary = f"Story {i}"
        issue.fields.priority.name = "Medium"
        issue.fields.customfield_10016 = points
        issues.append(issue)
    return issues


class TestTopUpFutureSprints:
    """Tests for SprintPlanner.top_up_future_sprints - capacity- and
    spillover-aware backfilling of already-existing future sprints."""

    def test_populates_existing_empty_future_sprint(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        mock_jira.get_issues_not_in_sprint.return_value = _backlog_issues(3)
        mock_jira.get_sprint_issues.return_value = []  # nothing already in the sprint

        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)
        state = SimulationState()
        horizon = PlanningHorizon()
        horizon.add_sprint_plan(_existing_future_sprint(11, "500"))
        state.set_planning_horizon(horizon)

        result = planner.top_up_future_sprints(state, "alpha_pm")

        assert result["sprints_populated"] == 1
        plan = state.get_planning_horizon().future_sprints[0]
        assert plan.committed_items  # something got added
        assert plan.committed_points > 0
        assert mock_jira.add_issue_to_sprint.called

    def test_merges_with_existing_committed_items_not_overwrite(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        """A sprint that already has real Jira carryover (from rollover, or a
        prior top-up pass) keeps those items - new ones are added on top,
        not replacing them."""
        existing = _backlog_issues(1, points=5, prefix="CARRY-")
        mock_jira.get_sprint_issues.return_value = existing
        mock_jira.get_issues_not_in_sprint.return_value = _backlog_issues(2, points=3)

        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)
        state = SimulationState()
        horizon = PlanningHorizon()
        horizon.add_sprint_plan(_existing_future_sprint(11, "500"))
        state.set_planning_horizon(horizon)

        planner.top_up_future_sprints(state, "alpha_pm")

        plan = state.get_planning_horizon().future_sprints[0]
        assert "CARRY-0" in plan.committed_items  # carryover preserved
        assert len(plan.committed_items) > 1  # plus newly added items
        assert plan.committed_points == 5 + 3 + 3  # carryover + both new items

    def test_skips_sprint_already_at_capacity(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        """A sprint whose already-committed points meet/exceed target
        capacity (default 20 with no velocity history) gets nothing added."""
        mock_jira.get_sprint_issues.return_value = _backlog_issues(4, points=5)  # 20 pts
        mock_jira.get_issues_not_in_sprint.return_value = _backlog_issues(3, prefix="NEW-")

        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)
        state = SimulationState()
        horizon = PlanningHorizon()
        horizon.add_sprint_plan(_existing_future_sprint(11, "500"))
        state.set_planning_horizon(horizon)

        result = planner.top_up_future_sprints(state, "alpha_pm")

        assert result["sprints_populated"] == 0
        mock_jira.add_issue_to_sprint.assert_not_called()

    def test_soonest_sprint_absorbs_spillover_discount(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        """The soonest future sprint's capacity is reduced by
        predicted_spillover_points; later sprints are unaffected."""
        mock_jira.get_issues_not_in_sprint.return_value = _backlog_issues(5, points=5)
        mock_jira.get_sprint_issues.return_value = []  # both sprints start empty

        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)
        state = SimulationState()
        horizon = PlanningHorizon()
        horizon.add_sprint_plan(_existing_future_sprint(11, "500", offset_days=7))
        horizon.add_sprint_plan(_existing_future_sprint(12, "501", offset_days=21))
        horizon.predicted_spillover_points = 15
        state.set_planning_horizon(horizon)

        planner.top_up_future_sprints(state, "alpha_pm")

        by_number = {
            p.sprint_number: p for p in state.get_planning_horizon().future_sprints
        }
        # Sprint 11 (soonest): capacity 20 - 15 discount = 5 -> exactly 1 item (5pts)
        assert by_number[11].committed_points == 5
        assert len(by_number[11].committed_items) == 1
        # Sprint 12: full capacity 20, no discount -> up to 4 items (20pts)
        assert by_number[12].committed_points == 20
        assert len(by_number[12].committed_items) == 4

    def test_stops_when_backlog_exhausted(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        mock_jira.get_issues_not_in_sprint.return_value = []
        mock_jira.get_sprint_issues.return_value = []

        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)
        state = SimulationState()
        horizon = PlanningHorizon()
        horizon.add_sprint_plan(_existing_future_sprint(11, "500"))
        horizon.add_sprint_plan(_existing_future_sprint(12, "501"))
        state.set_planning_horizon(horizon)

        result = planner.top_up_future_sprints(state, "alpha_pm")

        assert result["sprints_populated"] == 0
        mock_jira.add_issue_to_sprint.assert_not_called()

    def test_small_remaining_capacity_on_one_sprint_does_not_block_others(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        """A sprint whose remaining capacity is too small for any available
        item to fit must not abort the whole pass - a later sprint with more
        room should still get populated. (Regression: real backlog was 25
        Task + 25 Story with zero Bugs, so a sprint with only 2pts remaining
        legitimately can't fit anything - that must not stop sprint 12/13
        from being topped up too.)"""
        mock_jira.get_sprint_issues.side_effect = lambda sprint_id: (
            _backlog_issues(1, points=18) if sprint_id == 500 else []
        )
        # Only 3-point items available - none fit into sprint 11's 2pt remaining.
        mock_jira.get_issues_not_in_sprint.return_value = _backlog_issues(3, points=3)

        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)
        state = SimulationState()
        horizon = PlanningHorizon()
        horizon.add_sprint_plan(_existing_future_sprint(11, "500"))
        horizon.add_sprint_plan(_existing_future_sprint(12, "501"))
        state.set_planning_horizon(horizon)

        result = planner.top_up_future_sprints(state, "alpha_pm")

        by_number = {
            p.sprint_number: p for p in state.get_planning_horizon().future_sprints
        }
        assert by_number[11].committed_items == []  # nothing fit sprint 11's 2pt remaining
        assert by_number[12].committed_items  # sprint 12 still got populated
        assert result["sprints_populated"] == 1

    def test_schedules_actions_only_for_confirmed_items(
        self, mock_jira, mock_llm, mock_scheduler, settings, personas
    ):
        """Lifecycle actions are scheduled only for items Jira actually
        confirmed added, not the full aspirational selection."""
        issues = _backlog_issues(2, points=3)
        mock_jira.get_issues_not_in_sprint.return_value = issues
        mock_jira.get_sprint_issues.return_value = []
        confirmed_key = issues[0].key
        rejected_key = issues[1].key
        mock_jira.add_issue_to_sprint.side_effect = (
            lambda sprint_id, keys: keys[0] == confirmed_key
        )

        planner = SprintPlanner(
            mock_jira, mock_llm, mock_scheduler, settings, personas=personas
        )
        state = SimulationState()
        horizon = PlanningHorizon()
        horizon.add_sprint_plan(_existing_future_sprint(11, "500"))
        state.set_planning_horizon(horizon)

        planner.top_up_future_sprints(state, "alpha_pm")

        plan = state.get_planning_horizon().future_sprints[0]
        assert plan.committed_items == [confirmed_key]

        actions = [a for a in mock_scheduler.queue._heap if a.scenario_id]
        scheduled_tickets = {a.ticket_key for a in actions}
        assert confirmed_key in scheduled_tickets
        assert rejected_key not in scheduled_tickets

    def test_idempotent_when_run_twice_in_a_row(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        """A second run in the same state (simulating a retry) doesn't
        double-add items - remaining capacity is recomputed from what's
        already committed, not a cached delta. The mock mirrors real Jira
        semantics: once an item is added to a sprint, it no longer shows up
        as unsprinted backlog, and re-adding an already-committed item is a
        harmless no-op (not a duplicate)."""
        all_issues = _backlog_issues(3)
        added_so_far = []

        def get_issues_not_in_sprint(issue_types=None):
            return [i for i in all_issues if i.key not in added_so_far]

        def get_sprint_issues(sprint_id):
            return [i for i in all_issues if i.key in added_so_far]

        def add_issue_to_sprint(sprint_id, keys):
            for key in keys:
                if key not in added_so_far:
                    added_so_far.append(key)
            return True

        mock_jira.get_issues_not_in_sprint.side_effect = get_issues_not_in_sprint
        mock_jira.get_sprint_issues.side_effect = get_sprint_issues
        mock_jira.add_issue_to_sprint.side_effect = add_issue_to_sprint

        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)
        state = SimulationState()
        horizon = PlanningHorizon()
        horizon.add_sprint_plan(_existing_future_sprint(11, "500"))
        state.set_planning_horizon(horizon)

        planner.top_up_future_sprints(state, "alpha_pm")
        first_plan = state.get_planning_horizon().future_sprints[0]
        first_items = list(first_plan.committed_items)

        planner.top_up_future_sprints(state, "alpha_pm")
        second_plan = state.get_planning_horizon().future_sprints[0]

        # No duplicates, and nothing new to add since the backlog is now
        # fully consumed (all 3 items already sprinted on the first run).
        assert second_plan.committed_items == first_items
        assert len(second_plan.committed_items) == len(set(second_plan.committed_items))


class TestSimulationStatePlanningIntegration:
    """Test SimulationState integration with planning models."""

    def test_needs_sprint_planning_empty(self):
        """Test needs_sprint_planning with empty horizon."""
        state = SimulationState()
        assert state.needs_sprint_planning() is True

    def test_needs_sprint_planning_sufficient(self):
        """Test needs_sprint_planning with sufficient horizon (default target: 3)."""
        state = SimulationState()
        horizon = PlanningHorizon()
        for n, offset in ((8, 7), (9, 14), (10, 21)):
            horizon.add_sprint_plan(SprintPlan(
                sprint_number=n,
                start_date=pendulum.now("UTC").add(days=offset),
                end_date=pendulum.now("UTC").add(days=offset + 7),
            ))
        state.set_planning_horizon(horizon)

        assert state.needs_sprint_planning() is False

    def test_velocity_tracker_persistence(self):
        """Test velocity tracker round-trips through state."""
        state = SimulationState()

        velocity = VelocityTracker()
        velocity.record_sprint(5, 20, 18)
        state.set_velocity_tracker(velocity)

        loaded = state.get_velocity_tracker()
        assert len(loaded.sprint_history) == 1
        assert loaded.sprint_history[0].sprint_number == 5

    def test_planning_horizon_persistence(self):
        """Test planning horizon round-trips through state."""
        state = SimulationState()

        horizon = PlanningHorizon()
        horizon.add_sprint_plan(SprintPlan(
            sprint_number=8,
            start_date=pendulum.now("UTC").add(days=7),
            end_date=pendulum.now("UTC").add(days=14),
        ))
        state.set_planning_horizon(horizon)

        loaded = state.get_planning_horizon()
        assert loaded.get_sprint_count() == 1

    def test_empty_horizon_creates_default(self):
        """Test that getting empty horizon creates default."""
        state = SimulationState()
        horizon = state.get_planning_horizon()

        assert horizon is not None
        assert isinstance(horizon, PlanningHorizon)
        assert horizon.get_sprint_count() == 0

    def test_empty_velocity_creates_default(self):
        """Test that getting empty velocity creates default."""
        state = SimulationState()
        velocity = state.get_velocity_tracker()

        assert velocity is not None
        assert isinstance(velocity, VelocityTracker)
        assert len(velocity.sprint_history) == 0
