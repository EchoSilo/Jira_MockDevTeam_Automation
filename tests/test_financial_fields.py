"""Tests for Cost Type / Work Category auto-population on issue creation.

Covers:
- The distribution helpers in src/services/financial_fields.py
- JiraClient.create_issue injecting the fields for deliverable work, deferring
  the write for Bug (whose create screen omits the fields), and skipping
  non-deliverable issue types.
"""

import random
from unittest.mock import Mock

from src.services import financial_fields as ff
from src.services.jira_client import JiraClient

VALID_WC_IDS = set(ff.WORK_CAT.values())
VALID_COST_IDS = set(ff.COST.values())


# ── distribution helpers ─────────────────────────────────────────────────────

def test_financial_fields_returns_valid_option_ids():
    out = ff.financial_fields()
    assert set(out) == {ff.WORK_CATEGORY_FIELD, ff.COST_TYPE_FIELD}
    assert out[ff.WORK_CATEGORY_FIELD]["id"] in VALID_WC_IDS
    assert out[ff.COST_TYPE_FIELD]["id"] in VALID_COST_IDS


def test_cost_type_is_conditional_on_work_category():
    # Strategic skews Discretionary, Core and Maintenance skews Non-Discretionary.
    rng = random.Random(0)
    strategic = [ff.cost_for(rng, "Strategic") for _ in range(2000)]
    core = [ff.cost_for(rng, "Core and Maintenance") for _ in range(2000)]
    assert strategic.count("Discretionary") > strategic.count("Non-Discretionary")
    assert core.count("Non-Discretionary") > core.count("Discretionary")


def test_roll_work_category_inherits_parent_when_dice_low():
    # randint(1,100) returns 1 (<= INHERIT_PROBABILITY) -> inherit parent.
    rng = Mock()
    rng.randint.return_value = 1
    assert ff.roll_work_category(rng, parent_work_category="Strategic") == "Strategic"


def test_roll_work_category_ignores_unknown_parent():
    rng = random.Random(0)
    # An unknown parent value cannot be inherited; result is a valid category.
    assert ff.roll_work_category(rng, parent_work_category="Nonsense") in ff.WORK_CAT


# ── create_issue integration ─────────────────────────────────────────────────

def _client_with_mock():
    """A JiraClient with the underlying jira lib mocked (no real connection)."""
    client = JiraClient.__new__(JiraClient)
    client._client = Mock()
    client.project_key = "TEST"
    return client


def _created_fields(client):
    """The fields dict passed to the underlying create_issue."""
    _, kwargs = client._client.create_issue.call_args
    return kwargs["fields"]


def test_story_gets_fields_in_create_payload():
    client = _client_with_mock()
    client.create_issue("A story", "desc", issue_type="Story")
    fields = _created_fields(client)
    assert fields[ff.WORK_CATEGORY_FIELD]["id"] in VALID_WC_IDS
    assert fields[ff.COST_TYPE_FIELD]["id"] in VALID_COST_IDS


def test_bug_defers_fields_to_post_create_update():
    client = _client_with_mock()
    created = Mock()
    client._client.create_issue.return_value = created

    client.create_issue("A bug", "desc", issue_type="Bug")

    # Not in the create payload (Bug's create screen omits the fields)...
    fields = _created_fields(client)
    assert ff.WORK_CATEGORY_FIELD not in fields
    assert ff.COST_TYPE_FIELD not in fields
    # ...but applied immediately afterward via update.
    _, update_kwargs = created.update.call_args
    assert update_kwargs["fields"][ff.WORK_CATEGORY_FIELD]["id"] in VALID_WC_IDS
    assert update_kwargs["fields"][ff.COST_TYPE_FIELD]["id"] in VALID_COST_IDS


def test_deferred_update_failure_does_not_break_creation():
    client = _client_with_mock()
    created = Mock()
    created.key = "TEST-9"
    created.update.side_effect = RuntimeError("field not on screen")
    client._client.create_issue.return_value = created

    # Should not raise even though the post-create update fails.
    result = client.create_issue("A bug", "desc", issue_type="Bug")
    assert result is created


def test_non_deliverable_type_gets_no_fields():
    client = _client_with_mock()
    client.create_issue("An objective", "desc", issue_type="Objective")
    fields = _created_fields(client)
    assert ff.WORK_CATEGORY_FIELD not in fields
    assert ff.COST_TYPE_FIELD not in fields


def test_opt_out_flag_disables_assignment():
    client = _client_with_mock()
    client.create_issue("A story", "desc", issue_type="Story", assign_financial_fields=False)
    fields = _created_fields(client)
    assert ff.WORK_CATEGORY_FIELD not in fields
    assert ff.COST_TYPE_FIELD not in fields


def test_story_inherits_parent_epic_work_category():
    client = _client_with_mock()
    # Parent epic lookup returns Work Category "Strategic".
    parent = Mock()
    setattr(parent.fields, ff.WORK_CATEGORY_FIELD, Mock(value="Strategic"))
    client._client.issue.return_value = parent

    # Force the inheritance dice to "inherit" by pinning the module rng.
    saved = ff._module_rng
    ff._module_rng = Mock()
    ff._module_rng.randint.return_value = 1  # <= INHERIT_PROBABILITY
    ff._module_rng.choices.return_value = ["Tactical"]  # would-be fallback, unused
    try:
        client.create_issue("A story", "desc", issue_type="Story", parent_key="TEST-1")
    finally:
        ff._module_rng = saved

    fields = _created_fields(client)
    assert fields[ff.WORK_CATEGORY_FIELD]["id"] == ff.WORK_CAT["Strategic"]
