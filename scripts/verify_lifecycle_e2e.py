"""End-to-end verification of the sprint-planning fixes against REAL Jira.

Proves three things and prints a clear PASS/FAIL for each:

  1. Sprint planning works  -> forces one sprint plan and confirms a real Jira
     sprint was created AND populated with items; shows the queued lifecycle
     steps carry real agent owners and the wide execution window.
  2. Moving things in Jira works -> drives ONE active-sprint ticket through the
     lifecycle using the SAME code path a tick uses (orchestrator._execute_action),
     reading the ticket's real Jira status back after each step.
  3. It happened per the script -> the ticket advances in the scripted order
     (pick up -> review -> complete review -> QA), by the scripted agent roles.

Run INSIDE the container (after rebuild):
    docker-compose exec jira-simulator python scripts/verify_lifecycle_e2e.py

This WRITES to real Jira (creates a sprint, moves a ticket) and calls the LLM.
"""

import asyncio
import sys

import pendulum

from src.main import app
from src.orchestrator import ScenarioOrchestrator
from src.services.team_resolver import get_team_roster
from src.state import load_state
from src.time import RealClock

# Workflow rank (mirrors ReconciliationEngine.STATUS_ORDER, incl. aliases).
# Keys lower-cased because the real board uses UPPERCASE names (CODE REVIEW, TESTING).
_RANK = {
    "to do": 0, "in progress": 1,
    "code review": 2, "in review": 2,
    "ready for qa": 3, "testing": 3,
    "done": 4, "closed": 4, "resolved": 4,
}


def rank(status, default=-1):
    return _RANK.get((status or "").strip().lower(), default)

# (action_type, expected starting rank, target rank, scripted role)
SCRIPT = [
    ("pick_up_task", 0, 1, "developer"),
    ("progress_to_review", 1, 2, "developer"),
    ("complete_review", 2, 3, "tech_lead"),
    ("qa_approve", 3, 4, "qa"),
]

PASS, FAIL, INFO = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m", "info"


def hdr(t):
    print("\n" + "=" * 70 + f"\n{t}\n" + "=" * 70)


def status_of(jira, key):
    return jira.get_issue(key).fields.status.name


async def main():
    async with app.router.lifespan_context(app):
        jira = app.state.jira
        personas = app.state.personas
        planner = app.state.sprint_planner
        scheduler = app.state.scheduler

        state = load_state()
        active = jira.get_active_sprint()
        if not active:
            print(f"{FAIL}: no active sprint on the board; cannot verify.")
            return 1
        state.sprint.inject_jira_sprint(active, current_time=pendulum.now("UTC"))
        print(f"Active sprint: {active.get('name')} (id={active.get('id')})")

        overall_ok = True

        # ---------- PART 1: sprint planning ----------
        hdr("PART 1 - Does sprint planning create & populate a real Jira sprint?")
        futures_before = {s["id"] for s in jira.get_future_sprints(max_results=20)}
        # Isolate the steps THIS run queues from any stale pre-fix rows in scheduler.db.
        pre_ids = {a.action_id for a in scheduler.queue._heap}
        result = planner.plan_next_sprint(state, pm_agent_id="alpha_pm")

        if not result.get("success"):
            print(f"{FAIL}: plan_next_sprint did not succeed: {result.get('error')}")
            overall_ok = False
        else:
            name = result.get("sprint_name")
            items_added = result.get("items_added", 0)
            committed = result.get("sprint_plan", {}).get("committed_items", [])
            futures_after = {s["id"] for s in jira.get_future_sprints(max_results=20)}
            created = futures_after - futures_before

            print(f"  planned sprint name : {name}")
            print(f"  committed items     : {len(committed)} -> {committed}")
            print(f"  new future sprint(s): {sorted(created) or '(none new - may have reused)'}")
            print(f"  items added to Jira : {items_added}")

            p1 = bool(created or name) and items_added >= 1
            print(f"  {PASS if p1 else FAIL}: sprint created and populated in Jira")
            overall_ok = overall_ok and p1

        # Show the queued lifecycle steps prove real owners + wide window
        # (only the ones THIS run created, ignoring stale pre-fix db rows).
        scripted = [
            a for a in scheduler.queue._heap
            if a.scenario_id and a.action_id not in pre_ids
        ]
        if scripted:
            ownerless = [a for a in scripted if not a.agent_id]
            windows = {a.window_minutes for a in scripted}
            print(f"\n  queued lifecycle steps: {len(scripted)}")
            for a in sorted(scripted, key=lambda x: x.scheduled_time)[:8]:
                print(f"    {a.scheduled_time.format('MM-DD HH:mm')}  {a.action_type:<20} "
                      f"agent={a.agent_id or '(NONE)':<14} window={a.window_minutes}m")
            p1b = not ownerless and windows == {480}
            print(f"  {PASS if p1b else FAIL}: every step has a real owner "
                  f"(ownerless={len(ownerless)}) and wide window (windows={windows})")
            overall_ok = overall_ok and p1b

        # ---------- PART 2 & 3: real transitions in scripted order ----------
        hdr("PART 2 & 3 - Do tickets move in Jira, in the scripted order?")
        roster = get_team_roster(personas, "alpha")
        owners = {
            "developer": (roster["developer"] or [None])[0],
            "tech_lead": roster["tech_lead"] or (roster["developer"] or [None])[0],
            "qa": roster["qa"] or roster["tech_lead"],
        }
        print(f"  roster: dev={owners['developer']} tech_lead={owners['tech_lead']} qa={owners['qa']}")

        sprint_issues = jira.get_sprint_issues(active["id"], issue_types=["Story", "Bug", "Task"])
        # Prefer a ticket in 'To Do' so we can show the full arc.
        candidates = sorted(
            sprint_issues, key=lambda i: rank(i.fields.status.name, 9)
        )
        target = next((i for i in candidates if rank(i.fields.status.name, 9) < 4), None)
        if not target:
            print(f"{FAIL}: no non-Done ticket in the active sprint to drive.")
            return 1

        key = target.key
        start_status = status_of(jira, key)
        start_rank = rank(start_status, 0)
        print(f"  driving ticket: {key}  (starts at '{start_status}', rank {start_rank})")

        orch = ScenarioOrchestrator(
            jira_client=jira,
            llm_service=app.state.llm,
            personas=personas,
            templates=app.state.templates,
            settings=app.state.settings,
            clock=RealClock(),
            agent_registry=app.state.agent_clients,
        )

        steps_to_run = [s for s in SCRIPT if s[1] >= start_rank]
        prev_rank = start_rank
        order_ok = True
        moved_any = False

        for action_type, exp_start, target_rank, role in steps_to_run:
            agent_id = owners.get(role)
            action = {
                "type": action_type,
                "ticket_key": key,
                "agent_id": agent_id,
                "scenario_id": None,
            }
            print(f"\n  -> step '{action_type}' by {role} ({agent_id})")
            try:
                res = await orch._execute_action(action, state)
            except Exception as e:  # pylint: disable=broad-except
                print(f"     {FAIL}: executor raised: {e}")
                order_ok = False
                break

            new_status = status_of(jira, key)
            new_rank = rank(new_status, prev_rank)
            skipped = res.get("skipped")
            err = res.get("error")
            print(f"     result: status now '{new_status}' (rank {new_rank})"
                  f"{'  SKIPPED=' + str(res.get('reason')) if skipped else ''}"
                  f"{'  ERROR=' + str(err) if err else ''}")

            advanced = new_rank > prev_rank
            reached = new_rank >= target_rank
            if advanced:
                moved_any = True
            step_ok = reached and not err
            print(f"     {PASS if step_ok else FAIL}: expected to reach rank {target_rank} "
                  f"('{action_type}') -> {'reached' if reached else 'did NOT reach'}")
            order_ok = order_ok and step_ok
            if new_rank < prev_rank:
                print(f"     {FAIL}: ticket REGRESSED ({prev_rank} -> {new_rank}) - out of order")
                order_ok = False
            prev_rank = new_rank

        end_status = status_of(jira, key)
        print(f"\n  final: {key} '{start_status}' -> '{end_status}'")
        print(f"  {PASS if moved_any else FAIL}: ticket actually moved in Jira (Part 2)")
        print(f"  {PASS if order_ok else FAIL}: moved in scripted order to the end (Part 3)")
        overall_ok = overall_ok and moved_any and order_ok

        hdr("SUMMARY")
        print(f"  {PASS if overall_ok else FAIL}: overall verification")
        return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
