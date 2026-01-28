"""Tests for scenario scheduler and virtual clock."""

import pytest
import pendulum


class TestVirtualClock:
    """Tests for VirtualClock simulation time advancement."""

    def test_now_returns_simulation_time(self):
        """VirtualClock.now() returns current simulation time."""
        from src.scheduling.virtual_clock import VirtualClock

        start_time = pendulum.datetime(2026, 2, 1, 9, 0, tz="UTC")
        clock = VirtualClock(start_time=start_time)

        assert clock.now() == start_time

    def test_advance_adds_default_tick_duration(self):
        """VirtualClock.advance() adds tick_duration_hours (default 0.75)."""
        from src.scheduling.virtual_clock import VirtualClock

        start_time = pendulum.datetime(2026, 2, 1, 9, 0, tz="UTC")
        clock = VirtualClock(start_time=start_time)

        new_time = clock.advance()

        expected = start_time.add(hours=0.75)
        assert new_time == expected
        assert clock.now() == expected

    def test_advance_adds_custom_hours(self):
        """VirtualClock.advance(hours=X) adds X hours to simulation time."""
        from src.scheduling.virtual_clock import VirtualClock

        start_time = pendulum.datetime(2026, 2, 1, 9, 0, tz="UTC")
        clock = VirtualClock(start_time=start_time)

        new_time = clock.advance(hours=2.5)

        expected = start_time.add(hours=2.5)
        assert new_time == expected
        assert clock.now() == expected

    def test_set_time_jumps_to_specific_time(self):
        """VirtualClock.set_time() jumps to specific time."""
        from src.scheduling.virtual_clock import VirtualClock

        start_time = pendulum.datetime(2026, 2, 1, 9, 0, tz="UTC")
        clock = VirtualClock(start_time=start_time)

        new_time = pendulum.datetime(2026, 2, 5, 14, 30, tz="UTC")
        clock.set_time(new_time)

        assert clock.now() == new_time

    def test_custom_tick_duration(self):
        """VirtualClock accepts custom tick_duration_hours."""
        from src.scheduling.virtual_clock import VirtualClock

        start_time = pendulum.datetime(2026, 2, 1, 9, 0, tz="UTC")
        clock = VirtualClock(start_time=start_time, tick_duration_hours=1.0)

        new_time = clock.advance()

        expected = start_time.add(hours=1.0)
        assert new_time == expected

    def test_advance_accumulates(self):
        """Multiple advance() calls accumulate time."""
        from src.scheduling.virtual_clock import VirtualClock

        start_time = pendulum.datetime(2026, 2, 1, 9, 0, tz="UTC")
        clock = VirtualClock(start_time=start_time)

        clock.advance()  # +0.75 hours
        clock.advance()  # +0.75 hours
        clock.advance(hours=1.0)  # +1.0 hours

        expected = start_time.add(hours=0.75 + 0.75 + 1.0)
        assert clock.now() == expected


class TestScenarioScheduler:
    """Tests for ScenarioScheduler sprint script to calendar conversion."""

    def test_day_1_gets_sprint_start_date(self):
        """Day 1 in script maps to sprint_start_date."""
        from src.planning.scenario_scheduler import ScenarioScheduler

        scheduler = ScenarioScheduler()
        sprint_start = pendulum.datetime(2026, 2, 2, 9, 0, tz="America/New_York")  # Monday

        script = [
            {"day": 1, "type": "pick_up_task", "agent_id": "dev_1", "expected_status": "To Do"}
        ]

        actions = scheduler.convert_scenario_to_actions(
            script, sprint_start, "PROJ-100", "scenario_1"
        )

        assert len(actions) == 1
        action = actions[0]
        assert action.scheduled_time.date() == sprint_start.date()
        assert action.scheduled_time.day_of_week == sprint_start.day_of_week  # Monday

    def test_day_3_gets_sprint_plus_2_days(self):
        """Day 3 in script maps to sprint_start_date + 2 days."""
        from src.planning.scenario_scheduler import ScenarioScheduler

        scheduler = ScenarioScheduler()
        sprint_start = pendulum.datetime(2026, 2, 2, 9, 0, tz="America/New_York")  # Monday

        script = [
            {"day": 3, "type": "progress_task", "agent_id": "dev_1"}
        ]

        actions = scheduler.convert_scenario_to_actions(
            script, sprint_start, "PROJ-100", "scenario_1"
        )

        assert len(actions) == 1
        action = actions[0]
        expected_date = sprint_start.add(days=2).date()  # Wednesday
        assert action.scheduled_time.date() == expected_date

    def test_weekend_action_moved_to_monday(self):
        """Day 6 (Saturday if sprint starts Monday) moves to Monday."""
        from src.planning.scenario_scheduler import ScenarioScheduler

        scheduler = ScenarioScheduler()
        sprint_start = pendulum.datetime(2026, 2, 2, 9, 0, tz="America/New_York")  # Monday

        script = [
            {"day": 6, "type": "qa_approve", "agent_id": "qa_1"}  # Would be Saturday
        ]

        actions = scheduler.convert_scenario_to_actions(
            script, sprint_start, "PROJ-100", "scenario_1"
        )

        assert len(actions) == 1
        action = actions[0]
        # Should be moved to next Monday (weekend skipped)
        assert action.scheduled_time.day_of_week == 0  # Monday
        expected_monday = pendulum.datetime(2026, 2, 9, tz="America/New_York")
        assert action.scheduled_time.date() == expected_monday.date()

    def test_actions_have_randomized_times(self):
        """Actions don't all have :00:00 timestamps."""
        from src.planning.scenario_scheduler import ScenarioScheduler

        scheduler = ScenarioScheduler()
        sprint_start = pendulum.datetime(2026, 2, 2, 9, 0, tz="America/New_York")

        script = [
            {"day": 1, "type": "action_1", "agent_id": "dev_1"},
            {"day": 1, "type": "action_2", "agent_id": "dev_2"},
            {"day": 1, "type": "action_3", "agent_id": "dev_3"},
        ]

        actions = scheduler.convert_scenario_to_actions(
            script, sprint_start, "PROJ-100", "scenario_1"
        )

        # At least one action should have non-zero minutes (very high probability with random)
        times = [a.scheduled_time.time() for a in actions]
        has_variation = any(t.minute != 0 or t.hour != 9 for t in times)
        assert has_variation, "Actions should have randomized times"

    def test_actions_within_business_hours(self):
        """All scheduled actions fall within business hours (9am-5pm)."""
        from src.planning.scenario_scheduler import ScenarioScheduler

        scheduler = ScenarioScheduler()
        sprint_start = pendulum.datetime(2026, 2, 2, 9, 0, tz="America/New_York")

        script = [
            {"day": 1, "type": "action_1", "agent_id": "dev_1"},
            {"day": 2, "type": "action_2", "agent_id": "dev_2"},
            {"day": 3, "type": "action_3", "agent_id": "dev_3"},
        ]

        actions = scheduler.convert_scenario_to_actions(
            script, sprint_start, "PROJ-100", "scenario_1"
        )

        for action in actions:
            local_time = action.scheduled_time.in_timezone("America/New_York")
            assert 9 <= local_time.hour < 17, f"Action at {local_time} outside business hours"
            assert local_time.day_of_week < 5, f"Action on weekend: {local_time}"

    def test_full_week_script_skips_weekends(self):
        """7-day script produces 5 working days of actions."""
        from src.planning.scenario_scheduler import ScenarioScheduler

        scheduler = ScenarioScheduler()
        sprint_start = pendulum.datetime(2026, 2, 2, 9, 0, tz="America/New_York")  # Monday

        script = [
            {"day": i, "type": f"action_{i}", "agent_id": "dev_1"}
            for i in range(1, 8)  # Days 1-7
        ]

        actions = scheduler.convert_scenario_to_actions(
            script, sprint_start, "PROJ-100", "scenario_1"
        )

        # All actions should be on weekdays
        weekdays = [a.scheduled_time.day_of_week for a in actions]
        assert all(day < 5 for day in weekdays), "All actions should be weekdays"

        # Days 1-5 should map to Mon-Fri, days 6-7 should move to next Mon-Tue
        unique_dates = sorted(set(a.scheduled_time.date() for a in actions))
        # Should span Monday-Friday (5 days) + Monday-Tuesday (2 days) = 7 days worth
        # But weekend skipped, so 5 unique working days
        assert len(unique_dates) >= 5, "Should have at least 5 unique working days"

    def test_action_type_and_agent_preserved(self):
        """ScheduledAction preserves action_type and agent_id from script."""
        from src.planning.scenario_scheduler import ScenarioScheduler

        scheduler = ScenarioScheduler()
        sprint_start = pendulum.datetime(2026, 2, 2, 9, 0, tz="America/New_York")

        script = [
            {
                "day": 1,
                "type": "pick_up_task",
                "agent_id": "dev_alpha_1",
                "expected_status": "To Do",
                "params": {"priority": "high"}
            }
        ]

        actions = scheduler.convert_scenario_to_actions(
            script, sprint_start, "PROJ-100", "scenario_1"
        )

        assert len(actions) == 1
        action = actions[0]
        assert action.action_type == "pick_up_task"
        assert action.agent_id == "dev_alpha_1"
        assert action.ticket_key == "PROJ-100"
        assert action.scenario_id == "scenario_1"
        assert action.expected_status == "To Do"
        assert action.params == {"priority": "high"}

    def test_multiple_actions_on_same_day_have_different_times(self):
        """Multiple actions on same day get distributed throughout the day."""
        from src.planning.scenario_scheduler import ScenarioScheduler

        scheduler = ScenarioScheduler()
        sprint_start = pendulum.datetime(2026, 2, 2, 9, 0, tz="America/New_York")

        script = [
            {"day": 1, "type": f"action_{i}", "agent_id": f"dev_{i}"}
            for i in range(5)
        ]

        actions = scheduler.convert_scenario_to_actions(
            script, sprint_start, "PROJ-100", "scenario_1"
        )

        # All same date
        dates = [a.scheduled_time.date() for a in actions]
        assert len(set(dates)) == 1, "All actions on same day"

        # Different times (with very high probability due to randomization)
        times = [a.scheduled_time.time() for a in actions]
        unique_times = set(times)
        assert len(unique_times) > 1, "Actions should have different times"

    def test_scenario_id_and_ticket_key_set(self):
        """ScenarioScheduler sets scenario_id and ticket_key on actions."""
        from src.planning.scenario_scheduler import ScenarioScheduler

        scheduler = ScenarioScheduler()
        sprint_start = pendulum.datetime(2026, 2, 2, 9, 0, tz="America/New_York")

        script = [{"day": 1, "type": "test_action", "agent_id": "dev_1"}]

        actions = scheduler.convert_scenario_to_actions(
            script, sprint_start, "PROJ-999", "test_scenario_42"
        )

        assert actions[0].ticket_key == "PROJ-999"
        assert actions[0].scenario_id == "test_scenario_42"
