"""
Tests for planning models: SprintPlan, PlanningHorizon, and VelocityTracker.

Covers sprint planning, horizon management, and velocity-based capacity planning.
"""

import pytest
import pendulum
from src.planning import (
    SprintPlan, PlanningHorizon, SprintPlanStatus,
    VelocityTracker, SprintVelocityRecord,
)


class TestSprintPlan:
    """Tests for SprintPlan model."""

    def test_create_sprint_plan(self):
        """Test creating a sprint plan with committed items."""
        plan = SprintPlan(
            sprint_number=8,
            start_date=pendulum.datetime(2026, 2, 4, 9, 0, tz="UTC"),
            end_date=pendulum.datetime(2026, 2, 10, 17, 0, tz="UTC"),
            committed_items=["PROJ-100", "PROJ-101"],
            committed_points=13,
        )
        assert plan.sprint_number == 8
        assert len(plan.committed_items) == 2
        assert plan.committed_points == 13
        assert plan.status == SprintPlanStatus.PLANNED

    def test_sprint_plan_defaults(self):
        """Test sprint plan defaults (empty items, planned status)."""
        plan = SprintPlan(
            sprint_number=8,
            start_date=pendulum.datetime(2026, 2, 4, tz="UTC"),
            end_date=pendulum.datetime(2026, 2, 10, tz="UTC"),
        )
        assert plan.committed_items == []
        assert plan.committed_points == 0
        assert plan.status == SprintPlanStatus.PLANNED
        assert plan.scenario_id is None

    def test_sprint_plan_serialization(self):
        """Test JSON serialization of pendulum dates."""
        plan = SprintPlan(
            sprint_number=8,
            start_date=pendulum.datetime(2026, 2, 4, tz="UTC"),
            end_date=pendulum.datetime(2026, 2, 10, tz="UTC"),
        )
        data = plan.dict()
        assert "start_date" in data
        assert "end_date" in data
        # Pendulum datetime should be in data (not yet serialized to string)
        assert isinstance(data["start_date"], pendulum.DateTime)

    def test_sprint_plan_with_scenario(self):
        """Test sprint plan with scenario assignment."""
        plan = SprintPlan(
            sprint_number=8,
            start_date=pendulum.datetime(2026, 2, 4, tz="UTC"),
            end_date=pendulum.datetime(2026, 2, 10, tz="UTC"),
            scenario_id="normal_flow_001",
            velocity_estimate=20,
        )
        assert plan.scenario_id == "normal_flow_001"
        assert plan.velocity_estimate == 20


class TestPlanningHorizon:
    """Tests for PlanningHorizon model."""

    def test_needs_planning_empty(self):
        """Test needs_planning when no sprints planned."""
        horizon = PlanningHorizon()
        assert horizon.needs_planning() is True

    def test_needs_planning_below_minimum(self):
        """Test needs_planning when below min_sprints (2)."""
        horizon = PlanningHorizon()
        horizon.add_sprint_plan(SprintPlan(
            sprint_number=8,
            start_date=pendulum.now("UTC").add(days=7),
            end_date=pendulum.now("UTC").add(days=14),
        ))
        assert horizon.get_sprint_count() == 1
        assert horizon.needs_planning() is True  # Only 1, need 2

    def test_needs_planning_satisfied(self):
        """Test needs_planning when sufficient sprints planned."""
        horizon = PlanningHorizon()
        # Add 2 sprints far enough in future
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
        assert horizon.get_sprint_count() == 2
        assert horizon.needs_planning() is False

    def test_needs_planning_not_far_enough(self):
        """Test needs_planning when sprints not far enough ahead."""
        horizon = PlanningHorizon()
        # Add 2 sprints, but ending soon (< 14 days)
        horizon.add_sprint_plan(SprintPlan(
            sprint_number=8,
            start_date=pendulum.now("UTC").add(days=1),
            end_date=pendulum.now("UTC").add(days=8),
        ))
        horizon.add_sprint_plan(SprintPlan(
            sprint_number=9,
            start_date=pendulum.now("UTC").add(days=8),
            end_date=pendulum.now("UTC").add(days=12),  # Only 12 days ahead
        ))
        assert horizon.get_sprint_count() == 2
        assert horizon.needs_planning() is True  # Not far enough ahead

    def test_get_next_sprint_number_empty(self):
        """Test calculating next sprint number with no sprints."""
        horizon = PlanningHorizon()
        assert horizon.get_next_sprint_number(7) == 8

    def test_get_next_sprint_number_with_sprints(self):
        """Test calculating next sprint number with existing sprints."""
        horizon = PlanningHorizon()
        horizon.add_sprint_plan(SprintPlan(
            sprint_number=8,
            start_date=pendulum.now("UTC"),
            end_date=pendulum.now("UTC").add(days=7),
        ))
        assert horizon.get_next_sprint_number(7) == 9

        horizon.add_sprint_plan(SprintPlan(
            sprint_number=9,
            start_date=pendulum.now("UTC").add(days=7),
            end_date=pendulum.now("UTC").add(days=14),
        ))
        assert horizon.get_next_sprint_number(7) == 10

    def test_activate_sprint(self):
        """Test activating a sprint."""
        horizon = PlanningHorizon()
        horizon.add_sprint_plan(SprintPlan(
            sprint_number=8,
            start_date=pendulum.now("UTC"),
            end_date=pendulum.now("UTC").add(days=7),
        ))
        plan = horizon.activate_sprint(8)
        assert plan is not None
        assert plan.status == SprintPlanStatus.ACTIVE
        assert horizon.get_active_plan() == plan

    def test_activate_nonexistent_sprint(self):
        """Test activating sprint that doesn't exist."""
        horizon = PlanningHorizon()
        plan = horizon.activate_sprint(99)
        assert plan is None

    def test_complete_sprint(self):
        """Test completing a sprint."""
        horizon = PlanningHorizon()
        horizon.add_sprint_plan(SprintPlan(
            sprint_number=8,
            start_date=pendulum.now("UTC"),
            end_date=pendulum.now("UTC").add(days=7),
        ))
        horizon.activate_sprint(8)
        plan = horizon.complete_sprint(8)
        assert plan is not None
        assert plan.status == SprintPlanStatus.COMPLETED

    def test_get_active_plan(self):
        """Test getting active sprint plan."""
        horizon = PlanningHorizon()
        # Add planned sprint
        horizon.add_sprint_plan(SprintPlan(
            sprint_number=8,
            start_date=pendulum.now("UTC"),
            end_date=pendulum.now("UTC").add(days=7),
        ))
        assert horizon.get_active_plan() is None

        # Activate it
        horizon.activate_sprint(8)
        active = horizon.get_active_plan()
        assert active is not None
        assert active.sprint_number == 8

    def test_cleanup_old_sprints(self):
        """Test cleaning up old completed sprints."""
        horizon = PlanningHorizon()
        # Add old completed sprint
        old_sprint = SprintPlan(
            sprint_number=5,
            start_date=pendulum.now("UTC").subtract(days=60),
            end_date=pendulum.now("UTC").subtract(days=53),
            status=SprintPlanStatus.COMPLETED,
        )
        horizon.future_sprints.append(old_sprint)

        # Add recent completed sprint
        recent_completed = SprintPlan(
            sprint_number=7,
            start_date=pendulum.now("UTC").subtract(days=20),
            end_date=pendulum.now("UTC").subtract(days=13),
            status=SprintPlanStatus.COMPLETED,
        )
        horizon.future_sprints.append(recent_completed)

        # Add planned sprint
        horizon.add_sprint_plan(SprintPlan(
            sprint_number=8,
            start_date=pendulum.now("UTC"),
            end_date=pendulum.now("UTC").add(days=7),
        ))

        removed = horizon.cleanup_old_sprints(days=30)
        assert removed == 1
        assert len(horizon.future_sprints) == 2
        # Old sprint removed, recent completed and planned remain
        sprint_numbers = [s.sprint_number for s in horizon.future_sprints]
        assert 5 not in sprint_numbers
        assert 7 in sprint_numbers
        assert 8 in sprint_numbers


class TestVelocityTracker:
    """Tests for VelocityTracker and SprintVelocityRecord."""

    def test_create_velocity_record(self):
        """Test creating velocity record."""
        record = SprintVelocityRecord(
            sprint_number=7,
            committed=20,
            completed=18
        )
        assert record.sprint_number == 7
        assert record.committed == 20
        assert record.completed == 18
        assert record.status == "completed"

    def test_velocity_record_completion_rate(self):
        """Test completion rate calculation."""
        record = SprintVelocityRecord(
            sprint_number=7,
            committed=20,
            completed=18
        )
        assert record.completion_rate == 0.9

        # Zero committed
        record_zero = SprintVelocityRecord(
            sprint_number=8,
            committed=0,
            completed=0
        )
        assert record_zero.completion_rate == 0.0

    def test_record_sprint(self):
        """Test recording sprint velocity."""
        tracker = VelocityTracker()
        tracker.record_sprint(7, committed=20, completed=18)
        assert len(tracker.sprint_history) == 1
        assert tracker.sprint_history[0].sprint_number == 7
        assert tracker.sprint_history[0].completed == 18

    def test_record_sprint_update_existing(self):
        """Test updating existing sprint record."""
        tracker = VelocityTracker()
        tracker.record_sprint(7, committed=20, completed=18)
        tracker.record_sprint(7, committed=20, completed=20)  # Updated
        assert len(tracker.sprint_history) == 1
        assert tracker.sprint_history[0].completed == 20

    def test_get_average_velocity(self):
        """Test calculating average velocity from last 3 sprints."""
        tracker = VelocityTracker()
        tracker.record_sprint(5, committed=20, completed=18)
        tracker.record_sprint(6, committed=22, completed=20)
        tracker.record_sprint(7, committed=24, completed=22)

        avg = tracker.get_average_velocity(last_n_sprints=3)
        assert avg == 20  # (18+20+22)/3 = 20

    def test_get_average_velocity_fewer_sprints(self):
        """Test average velocity with fewer sprints than requested."""
        tracker = VelocityTracker()
        tracker.record_sprint(6, committed=20, completed=18)
        tracker.record_sprint(7, committed=22, completed=22)

        avg = tracker.get_average_velocity(last_n_sprints=3)
        assert avg == 20  # (18+22)/2 = 20

    def test_velocity_excludes_in_progress(self):
        """Test that in-progress sprint is excluded from average."""
        tracker = VelocityTracker()
        tracker.record_sprint(5, committed=20, completed=18)
        tracker.record_sprint(6, committed=22, completed=20)
        tracker.record_sprint(7, committed=24, completed=5, status="in_progress")

        avg = tracker.get_average_velocity(last_n_sprints=3)
        assert avg == 19  # (18+20)/2 = 19, not including in_progress

    def test_get_completion_rate(self):
        """Test calculating average completion rate."""
        tracker = VelocityTracker()
        tracker.record_sprint(5, committed=20, completed=18)  # 90%
        tracker.record_sprint(6, committed=20, completed=20)  # 100%
        tracker.record_sprint(7, committed=20, completed=16)  # 80%

        rate = tracker.get_completion_rate(last_n_sprints=3)
        assert rate == pytest.approx(0.9, rel=0.01)  # (0.9+1.0+0.8)/3 = 0.9

    def test_capacity_recommendation(self):
        """Test capacity recommendation (80% of avg)."""
        tracker = VelocityTracker()
        tracker.record_sprint(5, committed=20, completed=20)
        tracker.record_sprint(6, committed=20, completed=20)
        tracker.record_sprint(7, committed=20, completed=20)

        capacity = tracker.get_capacity_recommendation()
        assert capacity == 16  # 20 * 0.8 = 16

    def test_capacity_recommendation_custom_buffer(self):
        """Test capacity recommendation with custom buffer."""
        tracker = VelocityTracker()
        tracker.record_sprint(5, committed=20, completed=20)
        tracker.record_sprint(6, committed=20, completed=20)
        tracker.record_sprint(7, committed=20, completed=20)

        capacity = tracker.get_capacity_recommendation(buffer_percentage=0.9)
        assert capacity == 18  # 20 * 0.9 = 18

    def test_empty_velocity(self):
        """Test velocity with no history."""
        tracker = VelocityTracker()
        assert tracker.get_average_velocity() == 0
        assert tracker.get_completion_rate() == 0.0
        assert tracker.get_capacity_recommendation() == 0

    def test_velocity_only_in_progress(self):
        """Test velocity when only in-progress sprints exist."""
        tracker = VelocityTracker()
        tracker.record_sprint(7, committed=24, completed=10, status="in_progress")
        assert tracker.get_average_velocity() == 0
        assert tracker.get_capacity_recommendation() == 0
