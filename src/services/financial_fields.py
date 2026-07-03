"""Cost Type & Work Category — financial-classification custom fields.

Single source of truth for the two Jira custom fields and the weighted,
correlated distribution used to populate them. Shared by:
  - the live simulation (``JiraClient.create_issue``)
  - the one-off backfill (``scripts/distribute_cost_work_fields.py``)

Distribution model
------------------
Work Category is the anchor (weighted); Cost Type is *conditional* on it so the
seeded data mirrors a real organization's spend mix:

    Work Category:  Strategic 25%  ·  Tactical 35%  ·  Core and Maintenance 40%
    Cost Type | WC: Strategic -> 80% Discretionary, Tactical -> 50/50,
                    Core and Maintenance -> 10% Discretionary

When a parent Work Category is supplied (e.g. a new Story under an Epic), the
child inherits it ``INHERIT_PROBABILITY``% of the time for coherent roll-ups.
"""

from __future__ import annotations

import random
from typing import Optional

# ── Field + option ids (discovered live via GET /rest/api/3/field) ──────────
COST_TYPE_FIELD = "customfield_10106"
WORK_CATEGORY_FIELD = "customfield_10107"

COST = {"Discretionary": "10020", "Non-Discretionary": "10021"}
WORK_CAT = {"Strategic": "10022", "Tactical": "10023", "Core and Maintenance": "10024"}

# ── Distribution model ──────────────────────────────────────────────────────
WORK_CAT_WEIGHTS = [("Strategic", 25), ("Tactical", 35), ("Core and Maintenance", 40)]
COST_GIVEN_WC = {"Strategic": 80, "Tactical": 50, "Core and Maintenance": 10}  # P(Discretionary) %
INHERIT_PROBABILITY = 85  # % chance a child keeps its parent's Work Category

# ── Issue-type scope (which created issues receive the fields) ───────────────
# Deliverable work gets the fields; goal-level types (Objective/Key Result/
# Initiative) do not.
FINANCIAL_FIELD_ISSUE_TYPES = frozenset({"Story", "Task", "Epic", "Bug"})
# Of those, the types whose CREATE screen includes the fields (verified via
# createmeta). Bug's create screen omits them, so for Bug the fields are set
# immediately AFTER creation via an edit instead of in the create payload.
CREATE_TIME_ISSUE_TYPES = frozenset({"Story", "Task", "Epic"})

_module_rng = random.Random()


def weighted_choice(rng: random.Random, weights: list[tuple[str, int]]) -> str:
    population = [v for v, _ in weights]
    w = [n for _, n in weights]
    return rng.choices(population, weights=w, k=1)[0]


def cost_for(rng: random.Random, work_category: str) -> str:
    """Pick a Cost Type conditional on the issue's Work Category."""
    pct = COST_GIVEN_WC[work_category]
    return "Discretionary" if rng.randint(1, 100) <= pct else "Non-Discretionary"


def roll_work_category(
    rng: Optional[random.Random] = None,
    parent_work_category: Optional[str] = None,
) -> str:
    """Choose a Work Category, inheriting the parent's value when supplied."""
    r = rng or _module_rng
    if parent_work_category in WORK_CAT and r.randint(1, 100) <= INHERIT_PROBABILITY:
        return parent_work_category
    return weighted_choice(r, WORK_CAT_WEIGHTS)


def financial_fields(
    rng: Optional[random.Random] = None,
    parent_work_category: Optional[str] = None,
) -> dict:
    """Return a Jira fields dict ready to merge into a create/update payload.

    ``{WORK_CATEGORY_FIELD: {"id": ...}, COST_TYPE_FIELD: {"id": ...}}``
    """
    r = rng or _module_rng
    wc = roll_work_category(r, parent_work_category)
    cost = cost_for(r, wc)
    return {
        WORK_CATEGORY_FIELD: {"id": WORK_CAT[wc]},
        COST_TYPE_FIELD: {"id": COST[cost]},
    }
