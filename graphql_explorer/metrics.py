"""
Pulls real productivity/sprint/release metrics from Jira's internal GraphQL gateway.

What works today (verified against this tenant):

    Release health        JiraVersion.statistics              full numbers (Done/InP/ToDo/%Done, estimate coverage)
    Cycle time            JiraIssue.history (fieldId=status)   start = first event to 'indeterminate' category
                                                              end   = last event to 'done' category
    Reopen rate           same history stream                  any 'to' event landing in 'new' after first start
    Estimation coverage   JiraVersionStatistics.percentageEstimated
    Estimation hygiene    JiraIssue.storyPoints / timeOriginalEstimateField
    Sprint commit/finish  JiraIssue.history (fieldId=customfield_10020 = Sprint)
                          requires inline fragment on JiraHistoryGenericFieldValue
    Carryover %           same — find issues with a sprint=X "to" event before sprint X end
                                  that did NOT reach 'done' before X ended

Quirks the gateway enforces:
    * Operation MUST be named (no anonymous queries).
    * Beta / experimental fields require @optIn(to: "<name>") directives.
    * IDs are ARIs: ari:cloud:jira:{cloudId}:project/{id}, ari:cloud:jira-software:{cloudId}:board/{id},
      ari:cloud:jira-software:{cloudId}:sprint/{id}.
    * JiraVersion.statistics(boardId:) wants the board ARI, not just the integer board ID.

Usage:
    python -m graphql_explorer.metrics releases
    python -m graphql_explorer.metrics cycle-time --release "Release January 2026"
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import statistics
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

JIRA_URL = (os.getenv("JIRA_URL") or "").rstrip("/")
JIRA_EMAIL = os.getenv("JIRA_EMAIL") or ""
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN") or ""
PROJECT_KEY = os.getenv("PROJECT_KEY") or ""
GATEWAY = f"{JIRA_URL}/gateway/api/graphql"


def _auth_header() -> dict[str, str]:
    tok = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
    return {
        "Authorization": f"Basic {tok}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-ExperimentalApi": "opt-in",
    }


def _gql(client: httpx.Client, query: str, variables: dict, op: str) -> dict:
    r = client.post(
        GATEWAY,
        headers=_auth_header(),
        json={"operationName": op, "query": query, "variables": variables},
    )
    r.raise_for_status()
    body = r.json()
    if "errors" in body and not body.get("data"):
        raise RuntimeError(json.dumps(body["errors"], indent=2))
    return body


def _tenant_info() -> dict[str, str]:
    """Return cloudId, projectId, boardId — derived from env + REST lookups."""
    with httpx.Client(timeout=15) as c:
        ci = c.get(f"{JIRA_URL}/_edge/tenant_info", headers=_auth_header()).json()
        pr = c.get(
            f"{JIRA_URL}/rest/api/3/project/{PROJECT_KEY}", headers=_auth_header()
        ).json()
        br = c.get(
            f"{JIRA_URL}/rest/agile/1.0/board?projectKeyOrId={PROJECT_KEY}",
            headers=_auth_header(),
        ).json()
        board_id = br["values"][0]["id"] if br.get("values") else None
    return {
        "cloudId": ci["cloudId"],
        "projectId": pr["id"],
        "projectKey": pr["key"],
        "boardId": str(board_id) if board_id else "",
        "boardAri": f"ari:cloud:jira-software:{ci['cloudId']}:board/{board_id}",
    }


def _status_categories() -> dict[str, str]:
    """Return lowercase status name -> category key ('new','indeterminate','done')."""
    with httpx.Client(timeout=15) as c:
        r = c.get(f"{JIRA_URL}/rest/api/3/status", headers=_auth_header())
        return {s["name"].lower(): s["statusCategory"]["key"] for s in r.json()}


# ---------------------------------------------------------------------------
# Releases
# ---------------------------------------------------------------------------
RELEASES_QUERY = """
query Releases($cloudId: ID!, $projectKey: String!, $boardId: ID!) {
  jira_versionsForProjectByKey(cloudId: $cloudId, projectKey: $projectKey, first: 100)
    @optIn(to: "JiraVersionsForProjectByKey") {
    totalCount
    edges {
      node {
        versionId
        name
        status
        startDate
        releaseDate
        overdue
        statistics(boardId: $boardId) {
          totalIssueCount toDo inProgress done
          totalEstimate doneEstimate notDoneEstimate
          percentageCompleted percentageEstimated percentageUnestimated
          estimated notEstimated
        }
      }
    }
  }
}
"""


def releases() -> None:
    info = _tenant_info()
    with httpx.Client(timeout=30) as c:
        data = _gql(
            c,
            RELEASES_QUERY,
            {
                "cloudId": info["cloudId"],
                "projectKey": info["projectKey"],
                "boardId": info["boardAri"],
            },
            "Releases",
        )
    v = data["data"]["jira_versionsForProjectByKey"]
    print(f"{info['projectKey']} — {v['totalCount']} releases")
    print(
        f"{'Name':<32} {'Status':<10} {'Release':<12} {'Issues':>6} "
        f"{'Done':>5} {'InP':>4} {'ToDo':>5} {'%Done':>7} {'%Est':>6}"
    )
    print("-" * 100)
    for e in v["edges"]:
        n = e["node"]
        s = n.get("statistics") or {}
        rd = (n.get("releaseDate") or "")[:10] or "--"
        print(
            f"{(n['name'] or '')[:30]:<32} {(n['status'] or ''):<10} {rd:<12} "
            f"{s.get('totalIssueCount', 0):>6} {s.get('done', 0):>5} "
            f"{s.get('inProgress', 0):>4} {s.get('toDo', 0):>5} "
            f"{round(s.get('percentageCompleted') or 0, 1):>7} "
            f"{round(s.get('percentageEstimated') or 0, 1):>6}"
        )


# ---------------------------------------------------------------------------
# Cycle time (per release)
# ---------------------------------------------------------------------------
CYCLE_QUERY = """
query Cycle($cloudId: ID!, $projectKey: String!) {
  jira_versionsForProjectByKey(cloudId: $cloudId, projectKey: $projectKey, first: 5)
    @optIn(to: "JiraVersionsForProjectByKey") {
    edges { node {
      name
      issues(first: 100) {
        edges { node {
          key summary storyPoints
          statusCategory { key }
          history(first: 200) {
            edges { node {
              fieldId timestamp
              from { ... on JiraHistoryStatusFieldValue { displayValue } }
              to   { ... on JiraHistoryStatusFieldValue { displayValue } }
            } }
          }
        } }
      }
    } }
  }
}
"""


def cycle_time(release_name: str | None = None) -> None:
    info = _tenant_info()
    cats = _status_categories()
    with httpx.Client(timeout=60) as c:
        data = _gql(
            c,
            CYCLE_QUERY,
            {"cloudId": info["cloudId"], "projectKey": info["projectKey"]},
            "Cycle",
        )
    for v in data["data"]["jira_versionsForProjectByKey"]["edges"]:
        rel = v["node"]
        if release_name and rel["name"] != release_name:
            continue
        rows = []
        for e in rel["issues"]["edges"]:
            n = e["node"]
            if n["statusCategory"]["key"] != "done":
                continue
            evts = sorted(
                (h["node"] for h in n["history"]["edges"] if h["node"]["fieldId"] == "status"),
                key=lambda x: x["timestamp"],
            )

            def cat(v: dict | None) -> str | None:
                if not v:
                    return None
                return cats.get((v.get("displayValue") or "").lower())

            first_ip = next((e["timestamp"] for e in evts if cat(e.get("to")) == "indeterminate"), None)
            last_done = next(
                (e["timestamp"] for e in reversed(evts) if cat(e.get("to")) == "done"),
                None,
            )
            if first_ip and last_done and last_done > first_ip:
                days = (last_done - first_ip) / 1000 / 86400
                rows.append(
                    {
                        "key": n["key"],
                        "summary": n["summary"][:50],
                        "sp": n["storyPoints"],
                        "cycle_days": round(days, 2),
                        "transitions": len(evts),
                        "reopened": any(
                            cat(ev.get("to")) == "new" and i > 0 for i, ev in enumerate(evts)
                        ),
                    }
                )
        if not rows:
            print(f"\n{rel['name']}: no done issues with completed cycles")
            continue
        rows.sort(key=lambda r: r["cycle_days"])
        cycles = [r["cycle_days"] for r in rows]
        print(f"\n--- {rel['name']} ({len(rows)} completed cycles) ---")
        for r in rows:
            tag = " (REOPENED)" if r["reopened"] else ""
            print(
                f"  {r['key']:<13} sp={str(r['sp'] or '-'):<5} "
                f"cycle={r['cycle_days']:>7.2f}d  trans={r['transitions']:>3}{tag}  {r['summary']}"
            )
        print(f"  mean={statistics.mean(cycles):.2f}d  median={statistics.median(cycles):.2f}d  "
              f"p90={sorted(cycles)[int(len(cycles)*0.9)]:.2f}d  "
              f"max={max(cycles):.2f}d")
        reopened = sum(1 for r in rows if r["reopened"])
        print(f"  reopened: {reopened}/{len(rows)} ({100*reopened/len(rows):.0f}%)")


# ---------------------------------------------------------------------------
# Sprints (list + state)
# ---------------------------------------------------------------------------
SPRINTS_QUERY = """
query Sprints($boardId: ID!) {
  boardScope(boardId: $boardId) {
    id
    sprints {
      id name goal startDate endDate daysRemaining sprintState
    }
  }
}
"""


def sprints() -> None:
    info = _tenant_info()
    with httpx.Client(timeout=30) as c:
        data = _gql(c, SPRINTS_QUERY, {"boardId": info["boardAri"]}, "Sprints")
    for s in data["data"]["boardScope"]["sprints"] or []:
        sd = (s["startDate"] or "")[:10] or "--"
        ed = (s["endDate"] or "")[:10] or "--"
        print(
            f"[{s['sprintState']:<8}] {s['name']:<25} {sd} to {ed} "
            f"days_left={s['daysRemaining']} goal={(s['goal'] or '')[:60]}"
        )


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["releases", "cycle-time", "sprints", "tenant"])
    ap.add_argument("--release", help="Filter cycle-time to one release name")
    args = ap.parse_args()
    if args.cmd == "tenant":
        print(json.dumps(_tenant_info(), indent=2))
    elif args.cmd == "releases":
        releases()
    elif args.cmd == "cycle-time":
        cycle_time(args.release)
    elif args.cmd == "sprints":
        sprints()


if __name__ == "__main__":
    main()
