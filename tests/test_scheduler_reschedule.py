"""Tests for the wide execution window + reschedule-on-miss behavior that keeps
scheduled sprint lifecycle steps from being silently skipped."""

import pendulum
import pytest

from src.scheduling import Scheduler, ScheduledAction, ActionStatus
from src.scheduling.persistence import ScheduledActionStore
from src.scheduling.virtual_clock import VirtualClock

# America/New_York business hours; use ET so timestamps land in-window deterministically.
TZ = "America/New_York"


def _scheduler(tmp_path, start):
    store = ScheduledActionStore(str(tmp_path / "scheduler.db"))
    clock = VirtualClock(start)
    return Scheduler(store=store, virtual_clock=clock, scenario_max_reschedules=3)


def _action(scheduled_time, *, scenario_id=None, window=480, ticket="ESCRUM-1"):
    return ScheduledAction(
        scheduled_time=scheduled_time,
        action_type="pick_up_task",
        agent_id="alpha_dev1",
        ticket_key=ticket,
        scenario_id=scenario_id,
        window_minutes=window,
    )


class TestWideWindow:
    def test_due_across_many_ticks(self, tmp_path):
        """A wide window keeps a step due across many ~45-min ticks."""
        start = pendulum.datetime(2026, 2, 4, 9, 0, tz=TZ)  # Wed 9am ET
        sched = _scheduler(tmp_path, start)
        sched.schedule_action(_action(start, scenario_id="s1", window=480))

        due_hits = 0
        for _ in range(10):  # 10 * 45min = 7.5h, all within the 8h window
            if sched.get_due_actions(max_actions=5):
                due_hits += 1
            sched.clock.advance(0.75)
        assert due_hits >= 8

    def test_narrow_window_is_missed(self, tmp_path):
        """A 30-min window is overshot by a 45-min tick cadence."""
        start = pendulum.datetime(2026, 2, 4, 9, 0, tz=TZ)
        sched = _scheduler(tmp_path, start)
        sched.schedule_action(_action(start, scenario_id="s1", window=30))

        sched.clock.advance(0.75)  # +45min, past the 30-min window
        assert sched.get_due_actions(max_actions=5) == []


class TestRescheduleOnMiss:
    def test_scenario_action_reschedules_not_skips(self, tmp_path):
        """An overdue scenario step is re-dated (still PENDING), not skipped."""
        start = pendulum.datetime(2026, 2, 4, 9, 0, tz=TZ)
        sched = _scheduler(tmp_path, start)
        action = _action(start, scenario_id="s1", window=480)
        sched.schedule_action(action)

        # Jump past the window (to 6pm ET, after hours)
        sched.clock.set_time(pendulum.datetime(2026, 2, 4, 18, 0, tz=TZ))
        skipped = sched.mark_overdue_as_skipped()

        assert skipped == 0
        assert action.status == ActionStatus.PENDING
        assert action.params.get("reschedule_count") == 1
        # Re-dated into the future (next business morning)
        assert action.scheduled_time > pendulum.datetime(2026, 2, 4, 18, 0, tz=TZ)

    def test_non_scenario_action_still_skips(self, tmp_path):
        """A plain (non-scenario) overdue action keeps skip-on-overdue behavior."""
        start = pendulum.datetime(2026, 2, 4, 9, 0, tz=TZ)
        sched = _scheduler(tmp_path, start)
        action = _action(start, scenario_id=None, window=30)
        sched.schedule_action(action)

        sched.clock.set_time(pendulum.datetime(2026, 2, 4, 18, 0, tz=TZ))
        skipped = sched.mark_overdue_as_skipped()

        assert skipped == 1
        assert action.status == ActionStatus.SKIPPED

    def test_reschedule_cap_eventually_skips(self, tmp_path):
        """After scenario_max_reschedules, the step is finally skipped."""
        start = pendulum.datetime(2026, 2, 4, 9, 0, tz=TZ)
        sched = _scheduler(tmp_path, start)
        action = _action(start, scenario_id="s1", window=60)
        sched.schedule_action(action)

        # Repeatedly push the clock well past each new window.
        for _ in range(5):
            sched.clock.set_time(action.scheduled_time.add(hours=12))
            sched.mark_overdue_as_skipped()

        assert action.params.get("reschedule_count") == 3  # capped
        assert action.status == ActionStatus.SKIPPED


class TestScheduledTicketKeys:
    def test_returns_pending_ticket_keys(self, tmp_path):
        start = pendulum.datetime(2026, 2, 4, 9, 0, tz=TZ)
        sched = _scheduler(tmp_path, start)
        sched.schedule_action(_action(start, scenario_id="s1", ticket="ESCRUM-1"))
        sched.schedule_action(_action(start, scenario_id="s1", ticket="ESCRUM-2"))

        keys = sched.get_scheduled_ticket_keys()
        assert keys == {"ESCRUM-1", "ESCRUM-2"}

    def test_excludes_completed(self, tmp_path):
        start = pendulum.datetime(2026, 2, 4, 9, 0, tz=TZ)
        sched = _scheduler(tmp_path, start)
        a = _action(start, scenario_id="s1", ticket="ESCRUM-1")
        sched.schedule_action(a)
        sched.mark_action_completed(a.action_id, {"ok": True})

        assert sched.get_scheduled_ticket_keys() == set()
