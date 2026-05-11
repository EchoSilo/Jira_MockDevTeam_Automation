"""
Phase 3: Generate PM planning + QA test-prep Tasks under each backfill epic.

For each of the 47 target epics:
  - Rotate team per epic (even-index -> Alpha/Team 1, odd-index -> Beta/Team 2).
  - One LLM call (Haiku) returns 1-2 PM tasks + 1-2 QA tasks.
  - Bulk-create as issuetype=Task with parent=epic, label=backfill-pm-qa-tasks,
    Team field set, assignee preset to that team's PM (for pm_tasks) and QA
    (for qa_tasks).

Modes:
  (default)  Dry-run: writes data/backfill_pm_qa_preview.json, no Jira writes.
  --apply    Bulk-creates tasks in Jira.
  --limit N  Process only the first N epics.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from src.services.jira_client import JiraClient  # noqa: E402
from src.services.llm_service import LLMService  # noqa: E402

from _backfill_common import (  # noqa: E402
    DATA_DIR,
    PERSONA_TEAM_TO_ATLASSIAN_TEAM,
    STORY_POINTS_FIELD,
    TEAM_FIELD,
    chunked,
    discover_target_epics,
    fetch_initiative_summaries,
    load_personas,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill-pm-qa")

PREVIEW_PATH = DATA_DIR / "backfill_pm_qa_preview.json"
LOG_PATH = DATA_DIR / "backfill_pm_qa_log.jsonl"
LABEL = "backfill-pm-qa-tasks"
BULK_BATCH_SIZE = 50
VALID_STORY_POINTS = {1, 2, 3, 5, 8, 13}
VALID_PRIORITIES = {"Highest", "High", "Medium", "Low", "Lowest"}

# Per-team PM/QA persona agent_ids (looked up in personas.yaml at runtime).
TEAM_PM_QA = {
    "alpha": {"pm": "alpha_pm", "qa": "alpha_qa"},
    "beta":  {"pm": "beta_pm",  "qa": "beta_qa"},
}


def epics_with_existing_pm_qa(jira: JiraClient, epic_keys: list[str]) -> set[str]:
    """One JQL: which of these epic keys already have a backfill-pm-qa-tasks child?"""
    if not epic_keys:
        return set()
    keys_csv = ",".join(epic_keys)
    jql = f"parent in ({keys_csv}) AND labels = {LABEL}"
    issues = jira._client.search_issues(jql, fields="parent", maxResults=2000)
    parents = set()
    for issue in issues:
        parent = getattr(issue.fields, "parent", None)
        if parent is not None:
            parents.add(parent.key)
    return parents


def snap_points(raw) -> int:
    try:
        v = int(raw) if raw is not None else 3
    except (TypeError, ValueError):
        v = 3
    if v in VALID_STORY_POINTS:
        return v
    return min(VALID_STORY_POINTS, key=lambda x: abs(x - v))


def build_field_list(plan: list[dict], project_key: str, persona_index: dict) -> list[dict]:
    """Flatten the per-epic plan into Jira create-issue field dicts."""
    field_list: list[dict] = []
    for entry in plan:
        epic_key = entry["epic_key"]
        persona_team = entry["persona_team"]
        team_uuid = entry["team_uuid"]
        pm_agent = TEAM_PM_QA[persona_team]["pm"]
        qa_agent = TEAM_PM_QA[persona_team]["qa"]
        pm_account = persona_index[pm_agent]["jira_account_id"]
        qa_account = persona_index[qa_agent]["jira_account_id"]

        for role_key, account_id in (("pm_tasks", pm_account), ("qa_tasks", qa_account)):
            for task in entry["planned_tasks"][role_key]:
                priority = task.get("priority") or "Medium"
                if priority not in VALID_PRIORITIES:
                    priority = "Medium"
                points = snap_points(task.get("story_points"))
                # Note: customfield_10032 (Story Points) is not on the Task screen
                # in this Jira project, so it's intentionally omitted for Tasks.
                # The `points` value lives in the preview JSON for reference only.
                _ = points
                field_list.append({
                    "project": {"key": project_key},
                    "summary": task["summary"],
                    "description": task.get("description", ""),
                    "issuetype": {"name": "Task"},
                    "parent": {"key": epic_key},
                    "priority": {"name": priority},
                    "labels": [LABEL],
                    "assignee": {"accountId": account_id},
                    TEAM_FIELD: team_uuid,
                })
    return field_list


def build_persona_index(personas: dict) -> dict[str, dict]:
    out = {}
    for agent_id, cfg in personas.get("agents", {}).items():
        out[agent_id] = {
            "agent_id": agent_id,
            "jira_account_id": cfg.get("jira_account_id"),
            "display_name": cfg.get("display_name"),
            "team": cfg.get("team"),
            "role": cfg.get("role"),
        }
    return out


def generate_plan(jira: JiraClient, llm: LLMService, limit: int | None) -> tuple[list[dict], list[dict]]:
    epics = discover_target_epics(jira)
    logger.info("Discovered %d epics", len(epics))

    initiative_keys = sorted({e["parent_key"] for e in epics if e["parent_key"]})
    initiatives = fetch_initiative_summaries(jira, initiative_keys)
    logger.info("Fetched %d initiative summaries", len(initiatives))

    epic_keys = [e["key"] for e in epics]
    already = epics_with_existing_pm_qa(jira, epic_keys)
    if already:
        logger.info("Skipping %d epics that already have PM/QA tasks: %s",
                    len(already), sorted(already)[:5])
    eligible = [e for e in epics if e["key"] not in already]
    if limit is not None:
        eligible = eligible[:limit]
    logger.info("Generating PM/QA tasks for %d epics", len(eligible))

    plan: list[dict] = []
    failures: list[dict] = []
    for idx, epic in enumerate(eligible, start=1):
        # Rotate team: 1-based index parity. Odd -> alpha, even -> beta.
        persona_team = "alpha" if idx % 2 == 1 else "beta"
        team_uuid = PERSONA_TEAM_TO_ATLASSIAN_TEAM[persona_team]
        initiative_summary = initiatives.get(epic["parent_key"], "")
        logger.info("[%d/%d] %s  team=%s  %s",
                    idx, len(eligible), epic["key"], persona_team, epic["summary"][:55])
        try:
            tasks = llm.generate_pm_qa_tasks_for_epic(
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
            "persona_team": persona_team,
            "team_uuid": team_uuid,
            "planned_tasks": {
                "pm_tasks": tasks.get("pm_tasks", []),
                "qa_tasks": tasks.get("qa_tasks", []),
            },
        })
    return plan, failures


def summarise_plan(plan: list[dict], persona_index: dict) -> None:
    by_team = Counter(p["persona_team"] for p in plan)
    pm_count = sum(len(p["planned_tasks"]["pm_tasks"]) for p in plan)
    qa_count = sum(len(p["planned_tasks"]["qa_tasks"]) for p in plan)
    per_assignee: Counter = Counter()
    for p in plan:
        pm_agent = TEAM_PM_QA[p["persona_team"]]["pm"]
        qa_agent = TEAM_PM_QA[p["persona_team"]]["qa"]
        per_assignee[persona_index[pm_agent]["display_name"]] += len(p["planned_tasks"]["pm_tasks"])
        per_assignee[persona_index[qa_agent]["display_name"]] += len(p["planned_tasks"]["qa_tasks"])
    logger.info("Epics in plan:    %d  (alpha=%d, beta=%d)",
                len(plan), by_team.get("alpha", 0), by_team.get("beta", 0))
    logger.info("Total tasks:      %d  (pm=%d, qa=%d)", pm_count + qa_count, pm_count, qa_count)
    logger.info("Per assignee:")
    for name, n in per_assignee.most_common():
        logger.info("  %-20s %d", name, n)


def cmd_dry_run(jira: JiraClient, llm: LLMService, limit: int | None) -> int:
    personas = load_personas()
    persona_index = build_persona_index(personas)
    plan, failures = generate_plan(jira, llm, limit)
    summarise_plan(plan, persona_index)
    if failures:
        logger.warning("Failures: %d", len(failures))
        for f in failures[:10]:
            logger.warning("  %s -> %s", f["epic_key"], f["error"][:80])
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_PATH.write_text(
        json.dumps({"plan": plan, "failures": failures}, indent=2),
        encoding="utf-8",
    )
    logger.info("Preview written to %s", PREVIEW_PATH)
    return 0


def cmd_apply(jira: JiraClient, llm: LLMService, limit: int | None, regenerate: bool) -> int:
    project_key = jira.project_key
    personas = load_personas()
    persona_index = build_persona_index(personas)

    if regenerate or not PREVIEW_PATH.exists():
        logger.info("No preview (or --regenerate) - generating now.")
        rc = cmd_dry_run(jira, llm, limit)
        if rc != 0:
            return rc

    payload = json.loads(PREVIEW_PATH.read_text(encoding="utf-8"))
    plan: list[dict] = payload.get("plan", [])
    if not plan:
        logger.warning("Plan empty - nothing to apply.")
        return 0

    # Re-check Jira at apply time to skip epics that already have PM/QA tasks.
    epic_keys = [p["epic_key"] for p in plan]
    already = epics_with_existing_pm_qa(jira, epic_keys)
    if already:
        logger.info("Skipping %d epics that now have PM/QA tasks", len(already))
        plan = [p for p in plan if p["epic_key"] not in already]
    if limit is not None:
        plan = plan[:limit]

    field_list = build_field_list(plan, project_key, persona_index)
    if not field_list:
        logger.warning("No tasks to create.")
        return 0

    logger.info("Creating %d tasks across %d epics in %d batch(es) of <=%d",
                len(field_list), len(plan),
                (len(field_list) + BULK_BATCH_SIZE - 1) // BULK_BATCH_SIZE, BULK_BATCH_SIZE)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    created = 0
    errors = 0
    with LOG_PATH.open("a", encoding="utf-8") as logf:
        for bi, batch in enumerate(chunked(field_list, BULK_BATCH_SIZE), start=1):
            logger.info("Batch %d: creating %d tasks...", bi, len(batch))
            try:
                results = jira.create_issues_bulk(batch)
            except Exception as e:
                logger.error("Batch %d failed entirely: %s", bi, e)
                errors += len(batch)
                for f in batch:
                    logf.write(json.dumps({"status": "batch_error", "error": str(e), "input_summary": f.get("summary")}) + "\n")
                continue
            for f, r in zip(batch, results):
                issue = r.get("issue") if isinstance(r, dict) else None
                err = r.get("error") if isinstance(r, dict) else None
                parent_key = f.get("parent", {}).get("key", "?")
                assignee = f.get("assignee", {}).get("accountId", "?")
                if issue is not None:
                    new_key = getattr(issue, "key", None) or (issue.get("key") if isinstance(issue, dict) else None)
                    created += 1
                    logger.info("  %s -> %s  %s", parent_key, new_key, f["summary"][:55])
                    logf.write(json.dumps({
                        "status": "created", "epic_key": parent_key, "task_key": new_key,
                        "summary": f["summary"], "assignee_account_id": assignee,
                    }) + "\n")
                else:
                    errors += 1
                    logger.error("  %s FAILED: %s", parent_key, err)
                    logf.write(json.dumps({
                        "status": "error", "epic_key": parent_key, "error": err,
                        "summary": f["summary"],
                    }) + "\n")

    logger.info("Apply complete. Created: %d  Errors: %d  Log: %s", created, errors, LOG_PATH)
    return 0 if errors == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--apply", action="store_true",
                        help="Push generated tasks to Jira (default is dry-run).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N target epics.")
    parser.add_argument("--regenerate", action="store_true",
                        help="In --apply mode, regenerate tasks instead of using existing preview.")
    args = parser.parse_args()

    jira = JiraClient()
    llm = LLMService()
    if args.apply:
        return cmd_apply(jira, llm, limit=args.limit, regenerate=args.regenerate)
    return cmd_dry_run(jira, llm, limit=args.limit)


if __name__ == "__main__":
    sys.exit(main())
