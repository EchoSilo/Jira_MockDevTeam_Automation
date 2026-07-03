"""Set realistic status spread across Initiative/Epic/Story hierarchy.

Rules:
  - Done epics: all child stories → Done, epic → Done
  - In-progress epics: first 60% stories → Done, 1 story → In Progress, rest stay To Do
  - Initiative: → In Progress if any epics were touched

Usage:
    python scripts/set_statuses.py           # dry-run (preview only)
    python scripts/set_statuses.py --apply   # execute transitions
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
import os

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

JIRA_URL = os.environ["JIRA_URL"].rstrip("/")
JIRA_AUTH = (os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"])
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}

TRANSITION_IN_PROGRESS = "21"
TRANSITION_DONE = "31"

# (initiative_key, n_done_epics, n_in_progress_epics)
# Epics sorted by key ascending; first n_done → Done, next n_ip → In Progress, rest untouched.
INITIATIVE_PLAN: list[tuple[str, int, int]] = [
    ("ESCRUM-1811", 2, 0),  # User Profiling and Onboarding — 2 done, 1 untouched
    ("ESCRUM-1828", 2, 1),  # Athlete-Specific Training Phase 3 — 2 done, 1 in-progress
    ("ESCRUM-1812", 1, 1),  # AI Interaction and Feedback — 1 done, 1 in-progress
    ("ESCRUM-1813", 1, 1),  # Personalized Workout Plans — 1 done, 1 in-progress
    ("ESCRUM-1821", 1, 2),  # Achievement and Rewards Phase 2 — 1 done, 2 in-progress
    ("ESCRUM-1824", 0, 2),  # App Launch Preparation — 0 done, 2 in-progress
]


# ──────────────────────────────────────────────────────────────
# Jira REST helpers
# ──────────────────────────────────────────────────────────────

def fetch_children(parent_key: str, issuetype: str) -> list[str]:
    """Return child issue keys (sorted ascending) for a given parent."""
    jql = (
        f'project = ESCRUM AND issuetype = "{issuetype}" '
        f"AND parent = {parent_key} ORDER BY key ASC"
    )
    resp = requests.post(
        f"{JIRA_URL}/rest/api/3/search/jql",
        json={"jql": jql, "fields": ["key", "status"], "maxResults": 100},
        auth=JIRA_AUTH,
        headers=HEADERS,
    )
    resp.raise_for_status()
    return [i["key"] for i in resp.json().get("issues", [])]


def current_status(issue_key: str) -> str:
    """Return the current status name for an issue."""
    resp = requests.get(
        f"{JIRA_URL}/rest/api/3/issue/{issue_key}",
        params={"fields": "status"},
        auth=JIRA_AUTH,
        headers={"Accept": "application/json"},
    )
    if resp.status_code == 200:
        return resp.json()["fields"]["status"]["name"]
    return "unknown"


def do_transition(issue_key: str, transition_id: str, apply: bool) -> bool:
    """Transition an issue to the given status. Returns True on success (or dry-run)."""
    status_label = "Done" if transition_id == TRANSITION_DONE else "In Progress"
    if not apply:
        print(f"    DRY  {issue_key} -> {status_label}")
        return True
    resp = requests.post(
        f"{JIRA_URL}/rest/api/3/issue/{issue_key}/transitions",
        json={"transition": {"id": transition_id}},
        auth=JIRA_AUTH,
        headers=HEADERS,
    )
    if resp.status_code in (200, 204):
        print(f"    OK   {issue_key} -> {status_label}")
        return True
    print(f"    FAIL {issue_key} -> {status_label}  (HTTP {resp.status_code}: {resp.text[:80]})")
    return False


# ──────────────────────────────────────────────────────────────
# Core processing
# ──────────────────────────────────────────────────────────────

def process_epic_done(epic_key: str, apply: bool, counters: dict) -> None:
    stories = fetch_children(epic_key, "Story")
    print(f"  Epic {epic_key} -> Done  ({len(stories)} stories)")
    for story in stories:
        ok = do_transition(story, TRANSITION_DONE, apply)
        counters["ok" if ok else "fail"] += 1
        if apply:
            time.sleep(0.3)
    ok = do_transition(epic_key, TRANSITION_DONE, apply)
    counters["ok" if ok else "fail"] += 1
    if apply:
        time.sleep(0.3)


def process_epic_in_progress(epic_key: str, apply: bool, counters: dict) -> None:
    stories = fetch_children(epic_key, "Story")
    n = len(stories)
    n_done = math.floor(n * 0.6)
    n_ip = 1 if n > n_done else 0
    print(
        f"  Epic {epic_key} -> In Progress  "
        f"({n_done}/{n} stories Done, {n_ip} In Progress, {n - n_done - n_ip} To Do)"
    )
    for i, story in enumerate(stories):
        if i < n_done:
            ok = do_transition(story, TRANSITION_DONE, apply)
        elif i == n_done and n_ip:
            ok = do_transition(story, TRANSITION_IN_PROGRESS, apply)
        else:
            print(f"    SKIP {story} (stays To Do)")
            ok = True
        counters["ok" if ok else "fail"] += 1
        if apply:
            time.sleep(0.3)
    ok = do_transition(epic_key, TRANSITION_IN_PROGRESS, apply)
    counters["ok" if ok else "fail"] += 1
    if apply:
        time.sleep(0.3)


def process_initiative(
    initiative_key: str,
    n_done: int,
    n_ip: int,
    apply: bool,
    counters: dict,
) -> None:
    epics = fetch_children(initiative_key, "Epic")
    print(
        f"\nInitiative {initiative_key}  "
        f"({len(epics)} epics: {n_done} done, {n_ip} in-progress, "
        f"{max(0, len(epics) - n_done - n_ip)} untouched)"
    )

    for i, epic_key in enumerate(epics):
        if i < n_done:
            process_epic_done(epic_key, apply, counters)
        elif i < n_done + n_ip:
            process_epic_in_progress(epic_key, apply, counters)
        else:
            print(f"  Epic {epic_key} -> (untouched, stays To Do)")

    # Transition initiative to In Progress if any epics were touched
    if n_done + n_ip > 0 and n_done + n_ip <= len(epics) or (n_done + n_ip > 0):
        ok = do_transition(initiative_key, TRANSITION_IN_PROGRESS, apply)
        counters["ok" if ok else "fail"] += 1
        if apply:
            time.sleep(0.3)


# ──────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Set status spread across Jira hierarchy")
    parser.add_argument("--apply", action="store_true", help="Execute transitions (default: dry-run)")
    args = parser.parse_args()

    if not args.apply:
        print("DRY-RUN mode — no changes will be made. Pass --apply to execute.\n")

    counters = {"ok": 0, "fail": 0}

    for initiative_key, n_done, n_ip in INITIATIVE_PLAN:
        try:
            process_initiative(initiative_key, n_done, n_ip, args.apply, counters)
        except Exception as exc:
            print(f"\nERROR processing {initiative_key}: {exc}")
            counters["fail"] += 1

    mode = "DRY-RUN" if not args.apply else "DONE"
    print(f"\n{mode}: {counters['ok']} OK, {counters['fail']} failed")
    if not args.apply:
        print("Run with --apply to execute.")
    return 0 if counters["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
