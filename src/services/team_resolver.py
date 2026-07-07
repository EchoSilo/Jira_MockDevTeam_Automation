"""Derive persona teams from Jira Team membership.

The simulator keys everything off the internal team key (``alpha`` / ``beta``),
but which persona belongs to which team is the source of truth in Jira: each
persona's ``jira_account_id`` is a member of an Atlassian Team. This module
resolves that membership into the internal key and injects it into the personas
dict, so every existing ``config.get("team")`` reader works unchanged.

The binding between internal key and Jira team lives in ``personas["teams"][key]
["jira_team_id"]``. Membership (account -> team) comes from Jira via
``JiraClient.get_account_team_map``. A disk cache (``data/team_map_cache.json``)
holds the last good resolution so a transient Jira outage doesn't wipe team
assignments; the independent re-parsers of personas.yaml replay it offline.
"""

import json
import logging
from pathlib import Path
from typing import Optional

import pendulum

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = "data/team_map_cache.json"


def get_team_roster(personas: dict, team: str) -> dict:
    """Return a team's agent ids organized by role.

    Shape: ``{"pm": id|None, "tech_lead": id|None, "developer": [ids],
    "qa": id|None}``. Roles other than pm/tech_lead/qa bucket into
    ``developer``. This is the single source of truth for team rosters; both
    the Analyzer (opportunity detection) and the SprintPlanner (assigning
    owners to scheduled lifecycle steps) resolve rosters through here.
    """
    roster = {
        "pm": None,
        "tech_lead": None,
        "developer": [],
        "qa": None,
    }
    for agent_id, config in (personas.get("agents") or {}).items():
        if config.get("team") == team:
            role = config.get("role", "developer")
            if role in ("pm", "tech_lead", "qa"):
                roster[role] = agent_id
            else:
                roster["developer"].append(agent_id)
    return roster


def _team_binding(personas: dict) -> dict:
    """Return {jira_team_id -> internal_key} from the personas teams block."""
    binding = {}
    for key, meta in (personas.get("teams") or {}).items():
        team_ari = (meta or {}).get("jira_team_id")
        if team_ari:
            binding[team_ari] = key
    return binding


def resolve_persona_teams(
    personas: dict,
    jira_client,
    cache_path: str = DEFAULT_CACHE_PATH,
) -> dict:
    """Resolve each persona's team from Jira membership and mutate ``personas``.

    Sets ``agent["team"]`` for every agent whose ``jira_account_id`` maps to a
    bound Jira team, and populates ``personas["teams"][key]["display_name"]``
    from Jira. Writes the resolution to ``cache_path`` as the last-good copy.

    Only overrides a persona's team on a positive key match — a partial/empty
    Jira map can never null-out an existing key. Raises on Jira failure so the
    caller can fall back to the cache.

    Returns a small report dict for logging.
    """
    team_ari_to_key = _team_binding(personas)
    account_map, team_meta = jira_client.get_account_team_map()

    resolved: dict[str, str] = {}   # account_id -> key
    unmapped: list[str] = []        # agent ids with an account but no bound team

    for agent_id, config in (personas.get("agents") or {}).items():
        account_id = config.get("jira_account_id")
        if not account_id:
            continue  # e.g. release_manager (org-wide, team null)
        team_ari = account_map.get(account_id)
        key = team_ari_to_key.get(team_ari) if team_ari else None
        if key:
            if config.get("team") and config["team"] != key:
                logger.warning(
                    "Persona %s team override: yaml=%r -> jira=%r",
                    agent_id, config.get("team"), key,
                )
            config["team"] = key
            resolved[account_id] = key
        else:
            unmapped.append(agent_id)
            logger.warning(
                "Persona %s (account %s) not found in any bound Jira team",
                agent_id, account_id,
            )

    # Populate display names from Jira on the teams block.
    key_display: dict[str, str] = {}
    for team_ari, key in team_ari_to_key.items():
        name = team_meta.get(team_ari)
        if name:
            personas["teams"][key]["display_name"] = name
            key_display[key] = name

    _write_cache(cache_path, resolved, key_display)

    report = {
        "resolved": len(resolved),
        "unmapped": unmapped,
        "teams": key_display,
    }
    return report


def apply_persona_team_cache(
    personas: dict,
    cache_path: str = DEFAULT_CACHE_PATH,
) -> bool:
    """Apply the last-good resolution from disk — no Jira call.

    Used by the independent re-parsers of personas.yaml so they don't each need
    a JiraClient. Returns False if there is no usable cache.
    """
    data = _read_cache(cache_path)
    if not data:
        return False

    account_to_key = data.get("account_to_key") or {}
    key_display = data.get("key_display") or {}

    for config in (personas.get("agents") or {}).values():
        account_id = config.get("jira_account_id")
        key = account_to_key.get(account_id) if account_id else None
        if key:
            config["team"] = key

    for key, name in key_display.items():
        if key in (personas.get("teams") or {}):
            personas["teams"][key]["display_name"] = name

    return True


def _write_cache(cache_path: str, account_to_key: dict, key_display: dict) -> None:
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "resolved_at": pendulum.now("UTC").isoformat(),
        "account_to_key": account_to_key,
        "key_display": key_display,
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)


def _read_cache(cache_path: str) -> Optional[dict]:
    path = Path(cache_path)
    if not path.exists():
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not read team map cache %s: %s", cache_path, e)
        return None
