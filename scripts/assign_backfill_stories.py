"""
Phase 2: Assign the 192 backfilled stories to persona members.

Story->assignee picking rules:
  - The story's Atlassian Team field determines which persona team (alpha/beta).
  - Eligible roles: developers + tech_lead (PMs and QAs excluded).
  - Story points decide which seniority level inside the team takes the story.
  - Round-robin within each (team, points) bucket for deterministic, balanced output.

Modes:
  (default)  Dry-run: writes data/backfill_assign_preview.json, no Jira writes.
  --apply    Pushes assignee updates to Jira.
  --limit N  Process only the first N unassigned stories.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from src.services.jira_client import JiraClient  # noqa: E402

from _backfill_common import (  # noqa: E402
    ATLASSIAN_TEAM_TO_PERSONA_TEAM,
    DATA_DIR,
    STORY_POINTS_FIELD,
    TEAM_FIELD,
    load_personas,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("assign")

PREVIEW_PATH = DATA_DIR / "backfill_assign_preview.json"
LOG_PATH = DATA_DIR / "backfill_assign_log.jsonl"
LABEL = "backfill-stories"
PARALLEL_WORKERS = 8

# Eligible roles for story assignment. PM and QA intentionally excluded -
# they get their own Tasks in Phase 3.
ELIGIBLE_ROLES = {"developer", "tech_lead"}

# Per-points candidate rotations keyed by persona team.
# Values are persona agent_ids (keys in personas.yaml -> agents).
# Round-robin within each list.
ROTATIONS: dict[str, dict[int, list[str]]] = {
    "alpha": {
        2:  ["alpha_dev_mid",     "alpha_dev_mid",    "alpha_dev_senior"],
        3:  ["alpha_dev_mid",     "alpha_dev_senior", "alpha_dev_mid",     "alpha_tech_lead"],
        5:  ["alpha_dev_senior",  "alpha_tech_lead",  "alpha_dev_mid",     "alpha_dev_senior", "alpha_tech_lead"],
        8:  ["alpha_tech_lead",   "alpha_dev_senior"],
        13: ["alpha_tech_lead",   "alpha_dev_senior"],
    },
    "beta": {
        2:  ["beta_dev_junior",   "beta_dev_junior",  "beta_dev_senior"],
        3:  ["beta_dev_junior",   "beta_dev_senior",  "beta_dev_junior"],
        5:  ["beta_dev_senior",   "beta_dev_junior",  "beta_dev_senior"],
        8:  ["beta_dev_senior"],
        13: ["beta_dev_senior"],
    },
}


def build_persona_index(personas: dict) -> dict[str, dict]:
    """Map agent_id -> {jira_account_id, display_name, team, role}."""
    out = {}
    for agent_id, cfg in personas.get("agents", {}).items():
        if cfg.get("role") not in ELIGIBLE_ROLES and cfg.get("role") not in {"pm", "qa"}:
            continue
        out[agent_id] = {
            "agent_id": agent_id,
            "jira_account_id": cfg.get("jira_account_id"),
            "display_name": cfg.get("display_name"),
            "team": cfg.get("team"),
            "role": cfg.get("role"),
        }
    return out


def discover_unassigned_stories(jira: JiraClient, limit: int | None) -> list[dict]:
    """Paginated discovery against Jira Cloud's token-paginated /search/jql endpoint."""
    import os
    import urllib.request
    import urllib.parse
    import base64
    import ssl
    import json as _json

    project = jira.project_key
    jql = (
        f"project = {project} "
        f"AND labels = {LABEL} "
        f"AND assignee is EMPTY "
        f"ORDER BY key ASC"
    )

    auth = base64.b64encode(f"{jira.email}:{jira.api_token}".encode()).decode()
    base = jira.url.rstrip("/")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    all_issues: list = []
    next_token: str | None = None
    while True:
        params = {
            "jql": jql,
            "fields": f"summary,{TEAM_FIELD},{STORY_POINTS_FIELD}",
            "maxResults": 100,
        }
        if next_token:
            params["nextPageToken"] = next_token
        url = f"{base}/rest/api/3/search/jql?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, context=ctx) as r:
            data = _json.loads(r.read())
        all_issues.extend(data.get("issues", []))
        if data.get("isLast", True) or not data.get("nextPageToken"):
            break
        next_token = data["nextPageToken"]

    stories = []
    for issue in all_issues:
        fields = issue.get("fields", {})
        team_field = fields.get(TEAM_FIELD)
        team_uuid = team_field.get("id") if isinstance(team_field, dict) else None
        points = fields.get(STORY_POINTS_FIELD)
        try:
            points_int = int(points) if points is not None else None
        except (TypeError, ValueError):
            points_int = None
        stories.append({
            "key": issue["key"],
            "summary": fields.get("summary") or "",
            "team_uuid": team_uuid,
            "points": points_int,
        })
    if limit is not None:
        stories = stories[:limit]
    return stories


def plan_assignments(stories: list[dict], persona_index: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """Return (planned, skipped). Each planned entry has assignee details inline."""
    # Counters for round-robin within each (persona_team, points) bucket.
    counters: dict[tuple[str, int], int] = defaultdict(int)
    planned: list[dict] = []
    skipped: list[dict] = []

    for story in stories:
        team_uuid = story["team_uuid"]
        persona_team = ATLASSIAN_TEAM_TO_PERSONA_TEAM.get(team_uuid)
        if not persona_team:
            skipped.append({**story, "reason": f"unknown team_uuid={team_uuid}"})
            continue

        points = story["points"] or 3  # default to 3 if missing
        # Snap to a valid rotation key
        rotation_map = ROTATIONS[persona_team]
        if points not in rotation_map:
            points = min(rotation_map.keys(), key=lambda v: abs(v - points))
        rotation = rotation_map[points]

        idx = counters[(persona_team, points)]
        counters[(persona_team, points)] = idx + 1
        agent_id = rotation[idx % len(rotation)]
        persona = persona_index.get(agent_id)
        if not persona or not persona.get("jira_account_id"):
            skipped.append({**story, "reason": f"missing persona/account_id for {agent_id}"})
            continue

        planned.append({
            "key": story["key"],
            "summary": story["summary"],
            "team_uuid": team_uuid,
            "persona_team": persona_team,
            "points": points,
            "assignee_agent_id": agent_id,
            "assignee_account_id": persona["jira_account_id"],
            "assignee_name": persona["display_name"],
        })
    return planned, skipped


def print_distribution(planned: list[dict]) -> None:
    by_assignee = Counter(p["assignee_name"] for p in planned)
    by_team = Counter(p["persona_team"] for p in planned)
    by_points = Counter(p["points"] for p in planned)
    logger.info("Planned: %d stories", len(planned))
    logger.info("  by team:     %s", dict(by_team))
    logger.info("  by points:   %s", dict(sorted(by_points.items())))
    logger.info("  by assignee:")
    for name, n in by_assignee.most_common():
        logger.info("    %-20s %d", name, n)


def cmd_dry_run(jira: JiraClient, limit: int | None) -> int:
    personas = load_personas()
    persona_index = build_persona_index(personas)
    stories = discover_unassigned_stories(jira, limit)
    logger.info("Discovered %d unassigned backfilled stories", len(stories))
    if not stories:
        logger.warning("Nothing to assign.")
        return 0

    planned, skipped = plan_assignments(stories, persona_index)
    print_distribution(planned)
    if skipped:
        logger.warning("Skipped %d stories:", len(skipped))
        for s in skipped[:10]:
            logger.warning("  %s -> %s", s["key"], s["reason"])

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_PATH.write_text(
        json.dumps({"planned": planned, "skipped": skipped}, indent=2),
        encoding="utf-8",
    )
    logger.info("Preview written to %s", PREVIEW_PATH)
    return 0


def cmd_apply(jira: JiraClient, limit: int | None) -> int:
    personas = load_personas()
    persona_index = build_persona_index(personas)
    stories = discover_unassigned_stories(jira, limit)
    logger.info("Discovered %d unassigned backfilled stories", len(stories))
    if not stories:
        logger.info("Nothing to assign.")
        return 0

    planned, skipped = plan_assignments(stories, persona_index)
    print_distribution(planned)
    if skipped:
        logger.warning("Skipping %d stories (see preview).", len(skipped))

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Applying %d assignments with %d workers...", len(planned), PARALLEL_WORKERS)

    success = 0
    failed = 0

    def _assign_one(p: dict) -> tuple[dict, Exception | None]:
        try:
            jira.assign_issue(p["key"], p["assignee_account_id"])
            return p, None
        except Exception as e:
            return p, e

    with LOG_PATH.open("a", encoding="utf-8") as logf:
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as ex:
            futures = [ex.submit(_assign_one, p) for p in planned]
            for fut in as_completed(futures):
                p, err = fut.result()
                if err is None:
                    success += 1
                    logger.info("  %s -> %s (%s, %dpt)", p["key"], p["assignee_name"], p["persona_team"], p["points"])
                    logf.write(json.dumps({"status": "assigned", **p}) + "\n")
                else:
                    failed += 1
                    logger.error("  %s FAILED -> %s: %s", p["key"], p["assignee_name"], err)
                    logf.write(json.dumps({"status": "error", "error": str(err), **p}) + "\n")

    logger.info("Apply complete. Assigned: %d  Failed: %d", success, failed)
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--apply", action="store_true",
                        help="Push assignee updates to Jira (default is dry-run).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N unassigned stories.")
    args = parser.parse_args()

    jira = JiraClient()
    if args.apply:
        return cmd_apply(jira, limit=args.limit)
    return cmd_dry_run(jira, limit=args.limit)


if __name__ == "__main__":
    sys.exit(main())
