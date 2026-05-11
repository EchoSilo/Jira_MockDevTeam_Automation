"""Shared helpers for the backfill scripts.

Used by:
  - scripts/backfill_epic_stories.py     (Phase 1: stories)
  - scripts/assign_backfill_stories.py    (Phase 2: dev/tech-lead assignment)
  - scripts/backfill_pm_qa_tasks.py       (Phase 3: PM/QA tasks)
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

STORY_POINTS_FIELD = "customfield_10032"
TEAM_FIELD = "customfield_10001"

# Atlassian Team UUIDs in the ESCRUM project (discovered live via Jira API).
TEAMS = [
    {"id": "c8e13bd1-35c0-4738-bfe1-1da505356454", "name": "EchoSilo Team 1"},
    {"id": "a42c6077-db04-4c8d-a716-9b109d36d1d7", "name": "EchoSilo Team 2"},
]
TEAM1_ID = TEAMS[0]["id"]
TEAM2_ID = TEAMS[1]["id"]

# Mapping from persona-team string (in config/personas.yaml) to Atlassian Team UUID.
PERSONA_TEAM_TO_ATLASSIAN_TEAM = {
    "alpha": TEAM1_ID,
    "beta": TEAM2_ID,
}
ATLASSIAN_TEAM_TO_PERSONA_TEAM = {v: k for k, v in PERSONA_TEAM_TO_ATLASSIAN_TEAM.items()}


def discover_target_epics(jira) -> list[dict]:
    """Find epics in the project whose parent is an Initiative.

    Returns a list of dicts: {key, summary, description, parent_key}.
    """
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
        if parent_type and parent_type.lower() != "initiative":
            continue
        epics.append({
            "key": issue.key,
            "summary": issue.fields.summary or "",
            "description": (issue.fields.description or "")
                if hasattr(issue.fields, "description") else "",
            "parent_key": parent_key,
        })
    return epics


def fetch_initiative_summaries(jira, initiative_keys: list[str]) -> dict[str, str]:
    """Batch-fetch summaries for the parent Initiatives in one JQL call."""
    if not initiative_keys:
        return {}
    keys_csv = ",".join(initiative_keys)
    jql = f"key in ({keys_csv})"
    issues = jira._client.search_issues(jql, fields="summary", maxResults=500)
    return {i.key: (i.fields.summary or "") for i in issues}


def load_personas(config_path: Path | None = None) -> dict:
    """Load config/personas.yaml as a dict."""
    import yaml
    p = config_path or (ROOT / "config" / "personas.yaml")
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def chunked(seq, size: int):
    """Yield successive chunks of `seq` with at most `size` items each."""
    for i in range(0, len(seq), size):
        yield seq[i : i + size]
