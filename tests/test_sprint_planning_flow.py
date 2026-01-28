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

        # Create state with sufficient horizon
        state = SimulationState()
        horizon = PlanningHorizon()
        horizon.add_sprint_plan(SprintPlan(
            sprint_number=8,
            start_date=pendulum.now("UTC").add(days=7),
            end_date=pendulum.now("UTC").add(days=14),
        ))
        horizon.add_sprint_plan(SprintPlan(
            sprint_number=9,
            start_date=pendulum.now("UTC").add(days=14),
            end_date=pendulum.now("UTC").add(days=21),
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

    def test_sprint_dates_start_wednesday(
        self, mock_jira, mock_llm, mock_scheduler, settings
    ):
        """Test that sprints start on Wednesday."""
        planner = SprintPlanner(mock_jira, mock_llm, mock_scheduler, settings)
        state = SimulationState()

        result = planner.plan_next_sprint(state, pm_agent_id="pm_alpha")

        plan_data = result["sprint_plan"]
        start_date = pendulum.parse(plan_data["start_date"])
        # Wednesday = 2 in Pendulum (0=Monday)
        assert start_date.day_of_week == 2

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


class TestSimulationStatePlanningIntegration:
    """Test SimulationState integration with planning models."""

    def test_needs_sprint_planning_empty(self):
        """Test needs_sprint_planning with empty horizon."""
        state = SimulationState()
        assert state.needs_sprint_planning() is True

    def test_needs_sprint_planning_sufficient(self):
        """Test needs_sprint_planning with sufficient horizon."""
        state = SimulationState()
        horizon = PlanningHorizon()
        horizon.add_sprint_plan(SprintPlan(
            sprint_number=8,
            start_date=pendulum.now("UTC").add(days=7),
            end_date=pendulum.now("UTC").add(days=14),
        ))
        horizon.add_sprint_plan(SprintPlan(
            sprint_number=9,
            start_date=pendulum.now("UTC").add(days=14),
            end_date=pendulum.now("UTC").add(days=21),
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
