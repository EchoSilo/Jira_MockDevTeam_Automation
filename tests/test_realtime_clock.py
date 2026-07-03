"""Phase 2 (keystone) tests: real-time-paced scheduler clock.

The simulator is real-time paced. The scheduler must track REAL wall-clock time so its
notion of "now" agrees with the pacing gates (e.g. the 24h in-progress minimum) instead of
racing ahead of them via a compressed virtual clock. These tests lock in that behavior:

- RealtimeClock.now() returns real time; advance()/set_time() are no-ops (real time
  advances by itself, so no tick can compress or jump it).
- A Scheduler on a RealtimeClock evaluates due/overdue actions against real time, and
  advance_tick() cannot make a future-dated action due.
"""

import pendulum
import pytest

from src.scheduling.models import ScheduledAction
from src.scheduling.persistence import ScheduledActionStore
from src.scheduling.scheduler import Scheduler
from src.scheduling.virtual_clock import RealtimeClock, VirtualClock


def test_realtimeclock_now_tracks_real_time():
    clock = RealtimeClock()
    before = pendulum.now("UTC")
    now = clock.now()
    after = pendulum.now("UTC")
    assert before <= now <= after


def test_realtimeclock_advance_is_noop():
    """advance() must NOT jump time forward — real time advances on its own."""
    clock = RealtimeClock()
    t1 = clock.now()
    returned = clock.advance()          # historically jumped +0.75h
    returned2 = clock.advance(hours=99)  # explicit hours must also be ignored
    t2 = clock.now()
    # Only real elapsed wall-time (milliseconds) may separate these — never hours.
    assert (t2 - t1).total_hours() < 1
    assert (returned2 - returned).total_hours() < 1


def test_realtimeclock_set_time_is_noop():
    clock = RealtimeClock()
    clock.set_time(pendulum.datetime(2000, 1, 1, tz="UTC"))  # must be ignored
    assert clock.now().year >= 2026


def test_realtimeclock_is_a_virtualclock_with_tick_duration():
    """Drop-in compatibility: still a VirtualClock and still exposes tick_duration_hours."""
    clock = RealtimeClock(tick_duration_hours=0.75)
    assert isinstance(clock, VirtualClock)
    assert clock.tick_duration_hours == 0.75


def test_scheduler_due_actions_evaluated_against_real_time():
    scheduler = Scheduler(store=ScheduledActionStore(db_path=":memory:"),
                          virtual_clock=RealtimeClock())
    now = pendulum.now("UTC")

    past = ScheduledAction(scheduled_time=now.subtract(minutes=5),
                           action_type="pick_up_task", agent_id="dev_1", ticket_key="PROJ-1")
    future = ScheduledAction(scheduled_time=now.add(hours=3),
                             action_type="pick_up_task", agent_id="dev_1", ticket_key="PROJ-2")
    scheduler.schedule_action(past)
    scheduler.schedule_action(future)

    due = scheduler.get_due_actions(max_actions=10)
    due_keys = {a.ticket_key for a in due}
    assert "PROJ-1" in due_keys      # within its window now
    assert "PROJ-2" not in due_keys  # 3h out in real time — not due


def test_advance_tick_cannot_make_future_action_due():
    """The historical double advance_tick() must no longer surface future actions."""
    scheduler = Scheduler(store=ScheduledActionStore(db_path=":memory:"),
                          virtual_clock=RealtimeClock())
    now = pendulum.now("UTC")
    future = ScheduledAction(scheduled_time=now.add(hours=3),
                             action_type="pick_up_task", agent_id="dev_1", ticket_key="PROJ-2")
    scheduler.schedule_action(future)

    scheduler.advance_tick()
    scheduler.advance_tick()  # simulate the old double advance

    assert scheduler.get_due_actions(max_actions=10) == []
