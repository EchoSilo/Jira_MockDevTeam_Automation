"""Per-agent Jira client registry for per-agent attribution.

Each simulated agent authenticates to Jira with its OWN email + API token so
issue-level actions (comments, transitions, work logs, assignments) are recorded
in Jira under the correct person instead of a single shared admin account.

Credentials live in the environment as ``JIRA_EMAIL_<NAME>`` /
``JIRA_API_TOKEN_<NAME>`` where ``<NAME>`` is the agent's ``display_name`` from
personas.yaml, upper-snake-cased (e.g. "James Park" -> ``JAMES_PARK``).

The registry builds one ``ResilientJiraClient(LoggedJiraClient(...))`` per agent,
lazily and cached, and falls back to a supplied default (admin) client whenever an
agent has no credentials (e.g. ``release_manager``), the agent id is ``None``, or
client construction fails. It is intended to be a long-lived startup singleton so
the per-agent HTTP sessions persist across ticks.
"""

import logging
import os
from typing import Optional

from ..logging.logged_jira_client import LoggedJiraClient
from ..reconciliation.circuit_breaker import ResilientJiraClient

logger = logging.getLogger(__name__)


class AgentClientRegistry:
    """Resolve and cache a per-agent Jira client keyed by agent_id."""

    def __init__(self, personas: dict, log_writer, url: Optional[str] = None):
        self._personas = personas or {}
        self._log_writer = log_writer
        self._url = url or os.environ.get("JIRA_URL")
        self._cache: dict[str, ResilientJiraClient] = {}
        # agent_id -> "per-agent" | "fallback:<reason>" (for reporting)
        self._status: dict[str, str] = {}
        # Agents with definitively no credentials — the only permanent skip.
        self._no_creds: set[str] = set()

    @staticmethod
    def _env_name(display_name: str) -> str:
        return display_name.upper().replace(" ", "_")

    def _creds_for(self, agent_id: str) -> Optional[tuple[str, str]]:
        """Return (email, api_token) for an agent, or None if not fully configured."""
        agent = self._personas.get("agents", {}).get(agent_id, {})
        display_name = agent.get("display_name")
        if not display_name:
            return None
        name = self._env_name(display_name)
        email = os.environ.get(f"JIRA_EMAIL_{name}")
        token = os.environ.get(f"JIRA_API_TOKEN_{name}")
        if not email or not token:
            return None
        return email, token

    def resolve(self, agent_id: Optional[str], default_client):
        """Return the acting agent's client, or ``default_client`` as a fallback.

        Falls back to ``default_client`` when agent_id is None, the agent has no
        credentials, or client construction previously failed.
        """
        if not agent_id:
            return default_client

        cached = self._cache.get(agent_id)
        if cached is not None:
            return cached

        # Only "no credentials" is a permanent skip; transient build/validation
        # issues stay retryable so an agent is never silently disabled forever.
        if agent_id in self._no_creds:
            return default_client

        creds = self._creds_for(agent_id)
        if creds is None:
            self._no_creds.add(agent_id)
            self._status[agent_id] = "fallback:no-creds"
            return default_client

        email, token = creds
        try:
            client = ResilientJiraClient(
                LoggedJiraClient(
                    log_writer=self._log_writer,
                    email=email,
                    api_token=token,
                    url=self._url,
                )
            )
        except Exception as exc:  # never let a bad token break execution
            logger.warning(
                "Per-agent Jira client build failed for %s (%s); using admin fallback",
                agent_id,
                exc,
            )
            self._status[agent_id] = "fallback:error"
            return default_client

        self._cache[agent_id] = client
        self._status[agent_id] = "per-agent"
        return client

    def preflight(self) -> dict[str, str]:
        """Build + validate every agent's client at startup and log a report.

        For each agent with credentials, authenticate and confirm the token maps to
        the expected Jira account (accountId in personas). Agents without creds are
        recorded as fallbacks. Returns the agent_id -> status map.
        """
        agents = self._personas.get("agents", {})
        logger.info("Per-agent Jira attribution preflight (%d agents):", len(agents))
        for agent_id, cfg in agents.items():
            display_name = cfg.get("display_name", agent_id)
            expected_account = cfg.get("jira_account_id")
            creds = self._creds_for(agent_id)
            if creds is None:
                self._status[agent_id] = "fallback:no-creds"
                logger.info("  %-16s %-16s -> fallback (no token)", agent_id, display_name)
                continue
            client = self.resolve(agent_id, None)
            if client is None:
                logger.info("  %-16s %-16s -> fallback (build error)", agent_id, display_name)
                continue
            try:
                me = client.get_current_user() or {}
                account_id = me.get("accountId")
                got_name = me.get("displayName")
                if expected_account and account_id and account_id != expected_account:
                    logger.warning(
                        "  %-16s %-16s -> per-agent BUT accountId mismatch "
                        "(token=%s, personas=%s)",
                        agent_id, display_name, account_id, expected_account,
                    )
                    self._status[agent_id] = "per-agent:account-mismatch"
                else:
                    logger.info(
                        "  %-16s %-16s -> per-agent OK (%s)",
                        agent_id, display_name, got_name or account_id,
                    )
            except Exception as exc:
                # Report the validation problem but keep the cached client — the
                # write path will surface a real auth failure loudly if the token
                # is genuinely bad, rather than silently attributing to admin.
                self._status[agent_id] = "per-agent:unverified"
                logger.warning(
                    "  %-16s %-16s -> per-agent (validation skipped: %s)",
                    agent_id, display_name, exc,
                )
        return dict(self._status)
