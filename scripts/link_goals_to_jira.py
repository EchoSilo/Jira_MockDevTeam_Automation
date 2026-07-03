"""Link Atlas Goals Key Results (ECHOSILO-*) to their child Jira Initiatives (ESCRUM-*).

Hierarchy: Goal -> Sub-Goal (Objective) -> Sub-Goal (Key Result) -> [Jira Links] -> Initiative, ...

Usage:
    python scripts/link_goals_to_jira.py           # dry-run (preview only)
    python scripts/link_goals_to_jira.py --apply   # unlink old + link new
"""

from __future__ import annotations

import argparse
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
CLOUD_ID = "4d7e8213-5cb0-4d12-a133-296c7b7c257a"
CONTAINER_ARI = f"ari:cloud:townsquare::site/{CLOUD_ID}"
GQL_URL = f"{JIRA_URL}/gateway/api/graphql"
GQL_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "X-ExperimentalApi": "opt-in",
}

# ──────────────────────────────────────────────────────────────
# OLD (wrong) links — previously applied; will be unlinked first
# ──────────────────────────────────────────────────────────────
OLD_LINKS: list[tuple[str, str]] = [
    # Objectives linked to Jira Objective issues (wrong — remove)
    ("ECHOSILO-6",  "ESCRUM-1791"),
    ("ECHOSILO-13", "ESCRUM-1790"),
    ("ECHOSILO-14", "ESCRUM-1795"),
    ("ECHOSILO-2",  "ESCRUM-1792"),
    ("ECHOSILO-15", "ESCRUM-1794"),
    ("ECHOSILO-16", "ESCRUM-1787"),
    ("ECHOSILO-5",  "ESCRUM-1793"),
    ("ECHOSILO-3",  "ESCRUM-1831"),
    # KRs linked to Jira KR issues (wrong — remove)
    ("ECHOSILO-7",  "ESCRUM-1809"),
    ("ECHOSILO-8",  "ESCRUM-1808"),
    ("ECHOSILO-9",  "ESCRUM-1810"),
    ("ECHOSILO-18", "ESCRUM-1796"),
    ("ECHOSILO-19", "ESCRUM-1797"),
    ("ECHOSILO-20", "ESCRUM-1813"),
    ("ECHOSILO-21", "ESCRUM-1800"),
    ("ECHOSILO-22", "ESCRUM-1801"),
    ("ECHOSILO-23", "ESCRUM-1802"),
    ("ECHOSILO-24", "ESCRUM-1798"),
    ("ECHOSILO-25", "ESCRUM-1799"),
    ("ECHOSILO-26", "ESCRUM-1814"),
    ("ECHOSILO-27", "ESCRUM-1803"),
    ("ECHOSILO-28", "ESCRUM-1804"),
    ("ECHOSILO-29", "ESCRUM-1805"),
    ("ECHOSILO-30", "ESCRUM-1788"),
    ("ECHOSILO-31", "ESCRUM-1824"),
    ("ECHOSILO-32", "ESCRUM-1806"),
    ("ECHOSILO-33", "ESCRUM-1806"),
    ("ECHOSILO-34", "ESCRUM-1807"),
    ("ECHOSILO-35", "ESCRUM-1825"),
    ("ECHOSILO-4",  "ESCRUM-1829"),
]

# ──────────────────────────────────────────────────────────────
# NEW links — Atlas KR -> list of Jira Initiatives beneath it
# ──────────────────────────────────────────────────────────────
GOAL_TO_INITIATIVES: list[tuple[str, list[str]]] = [
    # Specialized Training KRs (under ECHOSILO-6 Objective)
    ("ECHOSILO-7",  ["ESCRUM-1827", "ESCRUM-1830", "ESCRUM-1833", "ESCRUM-1836"]),
    ("ECHOSILO-8",  ["ESCRUM-1826", "ESCRUM-1829", "ESCRUM-1832", "ESCRUM-1835"]),
    ("ECHOSILO-9",  ["ESCRUM-1828", "ESCRUM-1831", "ESCRUM-1834", "ESCRUM-1837", "ESCRUM-1885"]),
    # Personalized Workout KRs (under ECHOSILO-13 Objective)
    ("ECHOSILO-18", ["ESCRUM-1811", "ESCRUM-1813"]),
    ("ECHOSILO-19", ["ESCRUM-1812"]),
    ("ECHOSILO-20", ["ESCRUM-1813"]),   # Workout Completion -> Personalized Workout Plans
    # Health Tracking KRs (under ECHOSILO-14 Objective)
    ("ECHOSILO-21", ["ESCRUM-1816"]),
    ("ECHOSILO-22", ["ESCRUM-1817", "ESCRUM-1818"]),
    ("ECHOSILO-23", ["ESCRUM-1819"]),
    # Community KRs (under ECHOSILO-2 Objective)
    ("ECHOSILO-24", ["ESCRUM-1814"]),
    ("ECHOSILO-25", ["ESCRUM-1815"]),
    ("ECHOSILO-26", ["ESCRUM-1814"]),   # Social Sharing Actions -> Social Sharing initiative
    # Gamification KRs (under ECHOSILO-15 Objective)
    ("ECHOSILO-27", ["ESCRUM-1820", "ESCRUM-1822"]),
    ("ECHOSILO-28", ["ESCRUM-1823"]),
    ("ECHOSILO-29", ["ESCRUM-1821"]),
    # Platform Adoption KRs (under ECHOSILO-16 Objective)
    # ECHOSILO-30 skipped — no child Initiatives exist in Jira
    ("ECHOSILO-31", ["ESCRUM-1824"]),
    # Launch & Scale KRs (under ECHOSILO-5 Objective)
    ("ECHOSILO-32", ["ESCRUM-1824"]),
    ("ECHOSILO-33", ["ESCRUM-1824"]),
    ("ECHOSILO-34", ["ESCRUM-1825"]),
    ("ECHOSILO-35", ["ESCRUM-1825"]),
    # AI for Seniors sub-goal KR
    ("ECHOSILO-4",  ["ESCRUM-1829"]),
]


# ──────────────────────────────────────────────────────────────
# GraphQL helpers
# ──────────────────────────────────────────────────────────────

LINK_MUTATION = """
mutation LinkWorkItem($input: TownsquareGoalsLinkWorkItemInput!) {
  goals_linkWorkItem(input: $input) {
    success
    errors { message }
  }
}
"""

UNLINK_MUTATION_PRIMARY = """
mutation UnlinkWorkItem($input: TownsquareGoalsUnlinkWorkItemInput!) {
  goals_unlinkWorkItem(input: $input) {
    success
    errors { message }
  }
}
"""

UNLINK_MUTATION_FALLBACK = """
mutation UnlinkWorkItem($input: TownsquareGoalsRemoveWorkItemLinkInput!) {
  goals_removeWorkItemLink(input: $input) {
    success
    errors { message }
  }
}
"""

_unlink_mutation: str = UNLINK_MUTATION_PRIMARY
_unlink_field: str = "goals_unlinkWorkItem"
_unlink_fallback_tried: bool = False
UNLINK_UNAVAILABLE: bool = False


def gql(query: str, variables: dict | None = None) -> dict:
    payload: dict = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = requests.post(GQL_URL, json=payload, auth=JIRA_AUTH, headers=GQL_HEADERS)
    return resp.json()


def fetch_all_goal_ids() -> dict[str, str]:
    """Return {echosilo_key: goal_ari} for all Atlas Goals."""
    result = gql(
        """query FetchGoals {
          goals_search(containerId: \""""
        + CONTAINER_ARI
        + """\", first: 100) {
            edges { node { id key } }
          }
        }"""
    )
    goals = result.get("data", {}).get("goals_search", {}).get("edges", [])
    return {e["node"]["key"]: e["node"]["id"] for e in goals}


def fetch_jira_numeric_id(issue_key: str) -> str | None:
    """Return the numeric Jira issue ID for building its ARI."""
    resp = requests.get(
        f"{JIRA_URL}/rest/api/3/issue/{issue_key}",
        params={"fields": "id"},
        auth=JIRA_AUTH,
        headers={"Accept": "application/json"},
    )
    if resp.status_code == 200:
        return resp.json()["id"]
    return None


def link_goal_to_issue(goal_ari: str, issue_key: str, numeric_id: str) -> tuple[bool, str]:
    """Call goals_linkWorkItem; returns (success, status)."""
    work_item_ari = f"ari:cloud:jira:{CLOUD_ID}:issue/{numeric_id}"
    result = gql(LINK_MUTATION, {"input": {"goalId": goal_ari, "workItemId": work_item_ari}})
    if result.get("errors"):
        msg = result["errors"][0]["message"]
        print(f"    GQL error ({issue_key}): {msg[:120]}")
        return False, "gql_error"
    payload = result.get("data", {}).get("goals_linkWorkItem", {})
    if payload.get("success"):
        return True, "ok"
    errs = payload.get("errors", [])
    msg = errs[0]["message"] if errs else "unknown"
    if "already" in msg.lower() or "duplicate" in msg.lower() or "exists" in msg.lower():
        return True, "already_linked"
    print(f"    API error ({issue_key}): {msg[:120]}")
    return False, "api_error"


def unlink_goal_from_issue(goal_ari: str, issue_key: str, numeric_id: str) -> tuple[bool, str]:
    """Call goals_unlinkWorkItem (with fallback); returns (success, status)."""
    global _unlink_mutation, _unlink_field, _unlink_fallback_tried, UNLINK_UNAVAILABLE
    if UNLINK_UNAVAILABLE:
        return False, "skipped_no_mutation"

    work_item_ari = f"ari:cloud:jira:{CLOUD_ID}:issue/{numeric_id}"
    variables = {"input": {"goalId": goal_ari, "workItemId": work_item_ari}}

    result = gql(_unlink_mutation, variables)

    top_errors = result.get("errors", [])
    if top_errors:
        msg = top_errors[0].get("message", "")
        schema_rejected = any(kw in msg for kw in ("Cannot query field", "Unknown", "did you mean"))
        if schema_rejected and not _unlink_fallback_tried:
            print(f"    Unlink schema rejected ({_unlink_field}), trying fallback...")
            _unlink_mutation = UNLINK_MUTATION_FALLBACK
            _unlink_field = "goals_removeWorkItemLink"
            _unlink_fallback_tried = True
            result = gql(_unlink_mutation, variables)
            top_errors = result.get("errors", [])
            if top_errors:
                msg2 = top_errors[0].get("message", "")
                schema_rejected2 = any(kw in msg2 for kw in ("Cannot query field", "Unknown", "did you mean"))
                if schema_rejected2:
                    print("    WARN: unlink mutation not available in this API — old links NOT removed. Manual cleanup may be needed.")
                    UNLINK_UNAVAILABLE = True
                    return False, "skipped_no_mutation"
                print(f"    GQL error ({issue_key}): {msg2[:120]}")
                return False, "gql_error"
        else:
            print(f"    GQL error ({issue_key}): {msg[:120]}")
            return False, "gql_error"

    payload = result.get("data", {}).get(_unlink_field, {})
    if payload.get("success"):
        return True, "ok"
    errs = payload.get("errors", [])
    msg = errs[0]["message"] if errs else "unknown"
    if "not found" in msg.lower() or "does not exist" in msg.lower() or "no link" in msg.lower():
        return True, "not_linked"  # already absent — treat as success
    print(f"    API error ({issue_key}): {msg[:120]}")
    return False, "api_error"


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-link Atlas Goals KRs to Jira Initiatives")
    parser.add_argument("--apply", action="store_true", help="Execute unlink+link (default: dry-run)")
    args = parser.parse_args()

    print("Fetching Atlas Goal IDs...")
    goal_ids = fetch_all_goal_ids()
    print(f"  Found {len(goal_ids)} Atlas Goals\n")

    # ── Phase A: Unlink old (apply only) ──────────────────────
    unlink_ok = unlink_skip = unlink_fail = 0

    if args.apply:
        print("=== PHASE A: Removing old links ===")
        for echosilo_key, escrum_key in OLD_LINKS:
            goal_ari = goal_ids.get(echosilo_key)
            if not goal_ari:
                print(f"  SKIP  {echosilo_key} not found in Atlas")
                unlink_skip += 1
                continue
            numeric_id = fetch_jira_numeric_id(escrum_key)
            if not numeric_id:
                print(f"  SKIP  {escrum_key} not found in Jira")
                unlink_skip += 1
                continue
            if UNLINK_UNAVAILABLE:
                break
            print(f"  UNLINK  {echosilo_key} -> {escrum_key} ...", end=" ", flush=True)
            ok, status = unlink_goal_from_issue(goal_ari, escrum_key, numeric_id)
            if ok:
                print(f"OK ({status})")
                unlink_ok += 1
            else:
                if status == "skipped_no_mutation":
                    break
                print("FAIL")
                unlink_fail += 1
            time.sleep(5)
        print(f"\nUnlink: {unlink_ok} OK, {unlink_skip} skipped, {unlink_fail} failed\n")
    else:
        print("NOTE: Dry-run skips Phase A (unlink). Run with --apply to remove old links first.\n")

    # ── Phase B: Link new ──────────────────────────────────────
    print("=== PHASE B: Linking KRs to Initiatives ===")
    link_ok = link_skip = link_fail = 0

    for echosilo_key, escrum_keys in GOAL_TO_INITIATIVES:
        goal_ari = goal_ids.get(echosilo_key)
        if not goal_ari:
            print(f"  SKIP  {echosilo_key} not found in Atlas")
            link_skip += len(escrum_keys)
            continue

        for escrum_key in escrum_keys:
            numeric_id = fetch_jira_numeric_id(escrum_key)
            if not numeric_id:
                print(f"  SKIP  {escrum_key} not found in Jira")
                link_skip += 1
                continue

            work_item_tail = f"ari:cloud:jira:{CLOUD_ID}:issue/{numeric_id}"[-30:]
            if not args.apply:
                print(f"  DRY   {echosilo_key} -> {escrum_key}  ({work_item_tail})")
                link_ok += 1
                continue

            print(f"  LINK  {echosilo_key} -> {escrum_key} ...", end=" ", flush=True)
            ok, status = link_goal_to_issue(goal_ari, escrum_key, numeric_id)
            if ok:
                print(f"OK ({status})")
                link_ok += 1
            else:
                print("FAIL")
                link_fail += 1
            time.sleep(5)

    mode = "DRY-RUN" if not args.apply else "DONE"
    print(f"\n{mode} — Link phase: {link_ok} OK, {link_skip} skipped, {link_fail} failed")
    if not args.apply:
        print("Run with --apply to execute.")
    return 0 if (unlink_fail + link_fail) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
