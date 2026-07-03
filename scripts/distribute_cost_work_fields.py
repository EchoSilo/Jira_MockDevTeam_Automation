"""Randomly distribute Cost Type & Work Category across the deliverable backlog.

Two new single-select custom fields were added to the ESCRUM project for
financial / productivity analytics. This one-off script backfills them across
all deliverable work (Epic + Story + Task) with a *realistic, correlated*
distribution so the seeded data resembles a real organization's spend mix.

Model
-----
  - Work Category is the anchor, weighted at the Epic level and inherited by
    children, so each Epic's stories roll up coherently:
        Strategic 25%  ·  Tactical 35%  ·  Core and Maintenance 40%
    A Story/Task inherits its parent Epic's Work Category 85% of the time;
    15% of the time it re-rolls (realistic drift). Orphans roll independently.
  - Cost Type is conditional on the final Work Category (capital vs run-the-business):
        Strategic            -> Discretionary 80% / Non-Discretionary 20%
        Tactical             -> Discretionary 50% / Non-Discretionary 50%
        Core and Maintenance -> Discretionary 10% / Non-Discretionary 90%

Every choice is driven by a random.Random seeded from md5(issue_key) (epics
seeded from the epic key), so the assignment is a pure function of the keys:
the dry-run preview exactly matches --apply, and re-runs are stable/idempotent.

Usage
-----
    python scripts/distribute_cost_work_fields.py                 # dry-run preview
    python scripts/distribute_cost_work_fields.py --apply --limit 20   # test batch
    python scripts/distribute_cost_work_fields.py --apply         # full backfill
"""

from __future__ import annotations

import argparse
import hashlib
import os
import random
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

JIRA_URL = os.environ["JIRA_URL"].rstrip("/")
JIRA_AUTH = (os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"])
PROJECT_KEY = os.environ.get("PROJECT_KEY", "ESCRUM")
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}

# ── Field + option ids (discovered live via GET /rest/api/3/field) ──────────
COST_TYPE_FIELD = "customfield_10106"
WORK_CATEGORY_FIELD = "customfield_10107"

COST = {"Discretionary": "10020", "Non-Discretionary": "10021"}
WORK_CAT = {"Strategic": "10022", "Tactical": "10023", "Core and Maintenance": "10024"}

# ── Distribution model ──────────────────────────────────────────────────────
WORK_CAT_WEIGHTS = [("Strategic", 25), ("Tactical", 35), ("Core and Maintenance", 40)]

# P(Discretionary) given the Work Category; remainder is Non-Discretionary.
COST_GIVEN_WC = {
    "Strategic": 80,
    "Tactical": 50,
    "Core and Maintenance": 10,
}

INHERIT_PROBABILITY = 85  # % chance a child keeps its parent Epic's Work Category

SCOPE_TYPES = ("Epic", "Story", "Task")


# ── Deterministic RNG keyed by issue key ────────────────────────────────────

def rng_for(key: str) -> random.Random:
    """A stable per-key RNG (md5-seeded; avoids Python's salted built-in hash)."""
    seed = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)
    return random.Random(seed)


def weighted_choice(rng: random.Random, weights: list[tuple[str, int]]) -> str:
    population = [v for v, _ in weights]
    w = [n for _, n in weights]
    return rng.choices(population, weights=w, k=1)[0]


def cost_for(rng: random.Random, work_category: str) -> str:
    pct = COST_GIVEN_WC[work_category]
    return "Discretionary" if rng.randint(1, 100) <= pct else "Non-Discretionary"


# ── Jira REST ───────────────────────────────────────────────────────────────

def fetch_scope_issues() -> list[dict]:
    """Paginated fetch of all in-scope issues with their parent + current values."""
    type_csv = ", ".join(SCOPE_TYPES)
    jql = (
        f"project = {PROJECT_KEY} AND issuetype IN ({type_csv}) ORDER BY key ASC"
    )
    fields = ["issuetype", "parent", COST_TYPE_FIELD, WORK_CATEGORY_FIELD]
    out: list[dict] = []
    token: str | None = None
    while True:
        body: dict = {"jql": jql, "fields": fields, "maxResults": 100}
        if token:
            body["nextPageToken"] = token
        resp = requests.post(
            f"{JIRA_URL}/rest/api/3/search/jql",
            json=body, auth=JIRA_AUTH, headers=HEADERS,
        )
        resp.raise_for_status()
        data = resp.json()
        out.extend(data.get("issues", []))
        token = data.get("nextPageToken")
        if not token or data.get("isLast"):
            break
    return out


def apply_update(key: str, wc_name: str, cost_name: str) -> tuple[str, bool, str]:
    """PUT both fields onto one issue. Returns (key, ok, detail)."""
    payload = {
        "fields": {
            WORK_CATEGORY_FIELD: {"id": WORK_CAT[wc_name]},
            COST_TYPE_FIELD: {"id": COST[cost_name]},
        }
    }
    resp = requests.put(
        f"{JIRA_URL}/rest/api/3/issue/{key}",
        json=payload, auth=JIRA_AUTH, headers=HEADERS,
    )
    if resp.status_code in (200, 204):
        return key, True, ""
    return key, False, f"HTTP {resp.status_code}: {resp.text[:120]}"


# ── Assignment ──────────────────────────────────────────────────────────────

def assign_all(issues: list[dict]) -> list[dict]:
    """Return [{key, type, work_category, cost_type}] for every in-scope issue."""
    by_type = Counter(i["fields"]["issuetype"]["name"] for i in issues)
    print(f"In-scope issues: {len(issues)}  {dict(by_type)}")

    # 1) Anchor each Epic's Work Category (seeded by epic key) for inheritance.
    epic_wc: dict[str, str] = {}
    for issue in issues:
        if issue["fields"]["issuetype"]["name"] == "Epic":
            epic_wc[issue["key"]] = weighted_choice(rng_for(issue["key"]), WORK_CAT_WEIGHTS)

    # 2) Decide every issue's final Work Category + conditional Cost Type.
    plan: list[dict] = []
    for issue in issues:
        key = issue["key"]
        itype = issue["fields"]["issuetype"]["name"]
        rng = rng_for(key)
        parent = issue["fields"].get("parent")
        parent_key = parent["key"] if parent else None

        if itype == "Epic":
            wc = epic_wc[key]
        elif parent_key in epic_wc and rng.randint(1, 100) <= INHERIT_PROBABILITY:
            wc = epic_wc[parent_key]            # inherit parent Epic's category
        else:
            wc = weighted_choice(rng, WORK_CAT_WEIGHTS)   # orphan / drift

        cost = cost_for(rng, wc)
        plan.append({"key": key, "type": itype, "work_category": wc, "cost_type": cost})
    return plan


def print_distribution(plan: list[dict]) -> None:
    n = len(plan)
    wc_counts = Counter(p["work_category"] for p in plan)
    cost_counts = Counter(p["cost_type"] for p in plan)
    print("\nWork Category distribution:")
    for name, _ in WORK_CAT_WEIGHTS:
        c = wc_counts.get(name, 0)
        print(f"  {name:22} {c:5}  ({100*c//max(n,1):3}%)")
    print("Cost Type distribution:")
    for name in COST:
        c = cost_counts.get(name, 0)
        print(f"  {name:22} {c:5}  ({100*c//max(n,1):3}%)")


# ── Entry point ─────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Distribute Cost Type & Work Category across the deliverable backlog"
    )
    parser.add_argument("--apply", action="store_true", help="Execute writes (default: dry-run)")
    parser.add_argument("--limit", type=int, default=0, help="Cap to first N issues (test batch)")
    parser.add_argument("--workers", type=int, default=5, help="Parallel write workers")
    args = parser.parse_args()

    if not args.apply:
        print("DRY-RUN mode -- no changes will be made. Pass --apply to execute.\n")

    issues = fetch_scope_issues()
    plan = assign_all(issues)
    if args.limit:
        plan = plan[: args.limit]
        print(f"\n--limit {args.limit}: processing first {len(plan)} issues only")

    print_distribution(plan)

    if not args.apply:
        print("\nPreview (first 25):")
        for p in plan[:25]:
            print(f"  {p['key']:14} {p['type']:6} -> {p['work_category']} / {p['cost_type']}")
        print(f"\nDRY-RUN: {len(plan)} issues would be updated. Run with --apply to execute.")
        return 0

    print(f"\nApplying to {len(plan)} issues with {args.workers} workers...")
    ok = fail = 0
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {
            ex.submit(apply_update, p["key"], p["work_category"], p["cost_type"]): p
            for p in plan
        }
        for fut in as_completed(futures):
            key, success, detail = fut.result()
            if success:
                ok += 1
            else:
                fail += 1
                failures.append(f"  FAIL {key}  {detail}")
            if (ok + fail) % 100 == 0:
                print(f"  ...{ok + fail}/{len(plan)} done ({fail} failed)")

    if failures:
        print("\n".join(failures[:25]))
        if len(failures) > 25:
            print(f"  ...and {len(failures) - 25} more failures")
    print(f"\nDONE: {ok} OK, {fail} failed")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
