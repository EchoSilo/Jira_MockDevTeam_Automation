---
status: resolved
trigger: "Investigate and fix: Scheduled actions are planned but never executed"
created: 2026-02-16T12:00:00Z
updated: 2026-02-16T12:00:00Z
---

## Current Focus

hypothesis: Actions are scheduled at current_time, but then simulation time advances immediately, making scheduled actions never "due" in the next tick
test: Verify the timing logic in scheduler.advance_tick() and when actions become READY
expecting: To find that scheduled_time < scheduler.current_time (actions are in the past after advance)
next_action: Read TickExecutor and Scheduler code to confirm action selection logic

## Symptoms

expected: When /trigger is called, it should plan AND execute actions within the tick. Actions should result in Jira API calls, agent daily_actions incrementing, and last_run updating.
actual: /trigger plans 2-5 actions per call but actions_taken is always 0, actions_completed is always 0 in logs, no Jira calls made (jira_calls: 0 in log sessions), all agent daily_actions remain 0, last_run never updates after trigger.
errors: No explicit errors - the trigger returns success:true but with 0 actions taken.
reproduction: POST http://localhost:8000/trigger - returns actions_planned: 5 but actions_taken: 0 every time.
started: This appears to have been broken for a while. The last successful simulation with actual Jira actions was Feb 2, 2026.

## Eliminated

## Evidence

- timestamp: 2026-02-16T12:00:00Z
  checked: Trigger response from latest execution
  found: actions_planned=5, actions_taken=0, actions_completed=0, jira_calls=0
  implication: Actions are being scheduled but not executed

- timestamp: 2026-02-16T12:00:00Z
  checked: State file last_run timestamp
  found: Stays at 2026-02-16T06:57:12.618763Z (from sync-reset, not trigger)
  implication: The trigger endpoint is not updating state after execution

- timestamp: 2026-02-16T12:00:00Z
  checked: Scheduler DB
  found: Previously all actions showed "pending" status, never READY or COMPLETED
  implication: Actions never transition to executable state

- timestamp: 2026-02-16T12:05:00Z
  checked: src/main.py trigger_simulation() flow (lines 747-886)
  found: Line 747 executes ALREADY scheduled actions, Line 854 schedules NEW actions at current_time, Line 884 advances time PAST scheduled_time
  implication: New actions scheduled at T, then time advanced to T+tick_duration, making them never "due"

## Resolution

root_cause: Actions are scheduled at current_time (T), then simulation time advances to T+0.75h, making newly scheduled actions immediately overdue. Next tick finds actions where scheduled_time=T but current_time=T+0.75h, so window_end=T+0.5h < T+0.75h (overdue). Actions get skipped instead of executed.
fix: Changed src/main.py line 854 to schedule actions at next_tick_time (current_time + tick_duration_hours) instead of current_time. This ensures actions are scheduled for the future and can be executed in the next tick.
verification: Tested with 5 consecutive /trigger calls. Results show consistent pattern: Tick N plans actions (actions_planned > 0), Tick N+1 executes them (actions_taken > 0). Observed actions_taken values of 1, 0, 2, 1 across ticks, confirming execution is working.
files_changed: ["src/main.py"]
