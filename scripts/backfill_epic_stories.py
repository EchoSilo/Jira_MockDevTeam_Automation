"""
Backfill user stories under epics that have an Initiative as their parent.

Discovers all epics in the configured project whose parent is an Initiative,
skips any that already have child issues, generates 3-5 stories per epic via
Anthropic Haiku, and (in --apply mode) creates them in Jira via the bulk
endpoint with parent set to the epic key.

Modes:
  (default)  Dry-run: writes data/backfill_preview.json, no Jira writes.
  --apply    Pushes generated stories to Jira via bulk create.
  --limit N  Process only the first N target epics (testing).

Idempotency: a single JQL re-checks Jira for existing children each run.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Make src/ importable when running this script directly.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from src.services.jira_client import JiraClient  # noqa: E402
from src.services.llm_service import LLMService  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("backfill")

DATA_DIR = ROOT / "data"
PREVIEW_PATH = DATA_DIR / "backfill_preview.json"
LOG_PATH = DATA_DIR / "backfill_log.jsonl"
BULK_BATCH_SIZE = 50
LABEL = "backfill-stories"

STORY_POINTS_FIELD = "customfield_10032"
TEAM_FIELD = "customfield_10001"

# Atlassian Team UUIDs in the ESCRUM project (discovered live via Jira API).
TEAMS = [
    {"id": "c8e13bd1-35c0-4738-bfe1-1da505356454", "name": "EchoSilo Team 1"},
    {"id": "a42c6077-db04-4c8d-a716-9b109d36d1d7", "name": "EchoSilo Team 2"},
]

VALID_STORY_POINTS = {1, 2, 3, 5, 8, 13}


def discover_target_epics(jira: JiraClient) -> list[dict]:
    """Find epics in the project whose parent is an Initiative."""
    project = jira.project_key
    jql = (
        f"project = {project} "
        f"AND issuetype = Epic "
        f"AND parent is not EMPTY "
        f"ORDER BY key ASC"
    )
    issues = jira._client.search_issues(
        jql,
        fields="summary,description,parent",
        maxResults=500,
    )
    epics = []
    for issue in issues:
        parent = getattr(issue.fields, "parent", None)
        parent_key = parent.key if parent is not None else None
        parent_type = (
            parent.fields.issuetype.name
            if parent is not None and hasattr(parent.fields, "issuetype")
            else None
        )
        # Only keep epics whose parent is an Initiative (defensive - JQL already filters parent != empty,
        # but we want to confirm it really is an Initiative and not some other hierarchy item).
        if parent_type and parent_type.lower() != "initiative":
            continue
        epics.append({
            "key": issue.key,
            "summary": issue.fields.summary or "",
            "description": (issue.fields.description or "") if hasattr(issue.fields, "description") else "",
            "parent_key": parent_key,
        })
    return epics


def fetch_initiative_summaries(jira: JiraClient, initiative_keys: list[str]) -> dict[str, str]:
    """Batch-fetch summaries for the parent Initiatives in one JQL call."""
    if not initiative_keys:
        return {}
    keys_csv = ",".join(initiative_keys)
    jql = f"key in ({keys_csv})"
    issues = jira._client.search_issues(jql, fields="summary", maxResults=500)
    return {i.key: (i.fields.summary or "") for i in issues}


def epics_with_existing_children(jira: JiraClient, epic_keys: list[str]) -> set[str]:
    """One JQL: which of these epic keys already have at least one child?"""
    if not epic_keys:
        return set()
    keys_csv = ",".join(epic_keys)
    jql = f"parent in ({keys_csv})"
    issues = jira._client.search_issues(jql, fields="parent", maxResults=2000)
    parents = set()
    for issue in issues:
        parent = getattr(issue.fields, "parent", None)
        if parent is not None:
            parents.add(parent.key)
    return parents


def build_story_field_list(plan: list[dict], project_key: str) -> list[dict]:
    """Flatten the per-epic plan into a list of Jira-create field dicts.

    Each story gets:
      - parent: its epic
      - priority (from LLM)
      - story points (from LLM, snapped to Fibonacci; default 3)
      - team: round-robin across configured TEAMS to vary distribution
    """
    valid_priorities = {"Highest", "High", "Medium", "Low", "Lowest"}
    field_list = []
    team_idx = 0
    for entry in plan:
        epic_key = entry["epic_key"]
        for story in entry["planned_stories"]:
            priority = story.get("priority") or "Medium"
            if priority not in valid_priorities:
                priority = "Medium"

            raw_points = story.get("story_points")
            try:
                points = int(raw_points) if raw_points is not None else 3
            except (TypeError, ValueError):
                points = 3
            if points not in VALID_STORY_POINTS:
                # Snap to nearest Fibonacci.
                points = min(VALID_STORY_POINTS, key=lambda v: abs(v - points))

            team = TEAMS[team_idx % len(TEAMS)]
            team_idx += 1

            field_list.append({
                "project": {"key": project_key},
                "summary": story["summary"],
                "description": story.get("description", ""),
                "issuetype": {"name": "Story"},
                "parent": {"key": epic_key},
                "priority": {"name": priority},
                "labels": [LABEL],
                STORY_POINTS_FIELD: points,
                TEAM_FIELD: team["id"],
            })
    return field_list


def chunked(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def cmd_dry_run(jira: JiraClient, llm: LLMService, limit: int | None) -> int:
    epics = discover_target_epics(jira)
    logger.info("Discovered %d epics with Initiative parent", len(epics))
    if not epics:
        logger.warning("No target epics found - nothing to do.")
        return 0

    initiative_keys = sorted({e["parent_key"] for e in epics if e["parent_key"]})
    initiatives = fetch_initiative_summaries(jira, initiative_keys)
    logger.info("Fetched %d initiative summaries", len(initiatives))

    epic_keys = [e["key"] for e in epics]
    already = epics_with_existing_children(jira, epic_keys)
    if already:
        logger.info("Skipping %d epics that already have children: %s", len(already), sorted(already))

    eligible = [e for e in epics if e["key"] not in already]
    if limit is not None:
        eligible = eligible[:limit]
    logger.info("Generating stories for %d eligible epics", len(eligible))

    plan: list[dict] = []
    failures: list[dict] = []
    for idx, epic in enumerate(eligible, start=1):
        initiative_summary = initiatives.get(epic["parent_key"], "")
        logger.info(
            "[%d/%d] %s  (initiative=%s)  %s",
            idx, len(eligible), epic["key"], epic["parent_key"], epic["summary"][:60],
        )
        try:
            stories = llm.generate_stories_for_epic(
                epic_key=epic["key"],
                epic_summary=epic["summary"],
                epic_description=epic["description"],
                initiative_summary=initiative_summary,
            )
        except Exception as e:
            logger.error("  LLM failure for %s: %s", epic["key"], e)
            failures.append({"epic_key": epic["key"], "error": str(e)})
            continue
        plan.append({
            "epic_key": epic["key"],
            "epic_summary": epic["summary"],
            "initiative_key": epic["parent_key"],
            "initiative_summary": initiative_summary,
            "planned_stories": stories,
        })

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_PATH.write_text(
        json.dumps({"plan": plan, "failures": failures}, indent=2),
        encoding="utf-8",
    )
    total_stories = sum(len(p["planned_stories"]) for p in plan)
    logger.info(
        "Dry-run complete. Epics planned: %d  Stories planned: %d  Failures: %d",
        len(plan), total_stories, len(failures),
    )
    logger.info("Preview written to %s", PREVIEW_PATH)
    return 0


def cmd_apply(jira: JiraClient, llm: LLMService, limit: int | None, regenerate: bool) -> int:
    project_key = jira.project_key

    if regenerate or not PREVIEW_PATH.exists():
        logger.info("No preview file (or --regenerate) - generating stories now.")
        rc = cmd_dry_run(jira, llm, limit)
        if rc != 0:
            return rc

    payload = json.loads(PREVIEW_PATH.read_text(encoding="utf-8"))
    plan: list[dict] = payload.get("plan", [])
    if not plan:
        logger.warning("Preview is empty - nothing to apply.")
        return 0

    # Re-check Jira to skip epics that already have children (live idempotency).
    epic_keys = [p["epic_key"] for p in plan]
    already = epics_with_existing_children(jira, epic_keys)
    if already:
        logger.info("Skipping %d epics that already have children at apply time", len(already))
        plan = [p for p in plan if p["epic_key"] not in already]

    if limit is not None:
        plan = plan[:limit]

    field_list = build_story_field_list(plan, project_key)
    if not field_list:
        logger.warning("No stories to create after filtering.")
        return 0

    logger.info("Creating %d stories across %d epics in %d batch(es) of <=%d",
                len(field_list), len(plan), (len(field_list) + BULK_BATCH_SIZE - 1) // BULK_BATCH_SIZE, BULK_BATCH_SIZE)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    created_count = 0
    error_count = 0
    with LOG_PATH.open("a", encoding="utf-8") as logf:
        for batch_idx, batch in enumerate(chunked(field_list, BULK_BATCH_SIZE), start=1):
            logger.info("Batch %d: creating %d issues...", batch_idx, len(batch))
            try:
                results = jira.create_issues_bulk(batch)
            except Exception as e:
                logger.error("Bulk create batch %d failed entirely: %s", batch_idx, e)
                error_count += len(batch)
                for f in batch:
                    logf.write(json.dumps({"status": "batch_error", "error": str(e), "input": f}) + "\n")
                continue

            for f, r in zip(batch, results):
                issue = r.get("issue") if isinstance(r, dict) else None
                error = r.get("error") if isinstance(r, dict) else None
                parent_key = f.get("parent", {}).get("key", "?")
                if issue is not None:
                    new_key = getattr(issue, "key", None) or (issue.get("key") if isinstance(issue, dict) else None)
                    created_count += 1
                    logger.info("  %s -> %s  %s", parent_key, new_key, f["summary"][:60])
                    logf.write(json.dumps({
                        "status": "created",
                        "epic_key": parent_key,
                        "story_key": new_key,
                        "summary": f["summary"],
                    }) + "\n")
                else:
                    error_count += 1
                    logger.error("  %s FAILED: %s", parent_key, error)
                    logf.write(json.dumps({
                        "status": "error",
                        "epic_key": parent_key,
                        "error": error,
                        "summary": f["summary"],
                    }) + "\n")

    logger.info("Apply complete. Created: %d  Errors: %d  Log: %s", created_count, error_count, LOG_PATH)
    return 0 if error_count == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--apply", action="store_true",
                        help="Push generated stories to Jira (default is dry-run).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N target epics.")
    parser.add_argument("--regenerate", action="store_true",
                        help="In --apply mode, regenerate stories instead of using existing preview.")
    args = parser.parse_args()

    jira = JiraClient()
    llm = LLMService()

    if args.apply:
        return cmd_apply(jira, llm, limit=args.limit, regenerate=args.regenerate)
    return cmd_dry_run(jira, llm, limit=args.limit)


if __name__ == "__main__":
    sys.exit(main())
