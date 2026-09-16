"""Per-fact k-anonymity — every identifying fact is generalised until >= k released cards share it.

Policy (say it on the slide): we generalise *identifiers* — where, when, how much, how long, how
many — and we never suppress *what happened*. A single report of sexual harassment must reach the
committee even if it is the only one; a single report that names "room 214 at 2:40 am" must not.
"""
from __future__ import annotations

import copy
from typing import Dict, List, Optional, Tuple

from ..pipeline.card import Card, LOCATION_HIERARCHY, TIME_HIERARCHY
from ..pipeline.facts import Facts

# value -> coarser value (None = root; stays as is)
AMOUNT_UP = {"under_100": "some", "100_500": "some", "500_2000": "some", "over_2000": "some", "some": None, "none": None}
DURATION_UP = {"under_30m": "unknown", "30m_2h": "unknown", "2h_5h": "unknown", "over_5h": "unknown", "unknown": None}
COUNT_UP = {"one": "unknown", "few": "unknown", "group": "unknown", "unknown": None}
FREQ_UP = {"once": "unknown", "daily": "repeated", "repeated": "unknown", "unknown": None}
IDENTIFIER_FIELDS = ("location", "time_bucket", "amount", "duration", "actor_count", "frequency")


def _up(field_name: str, value: str) -> Optional[str]:
    return {
        "location": LOCATION_HIERARCHY, "time_bucket": TIME_HIERARCHY, "amount": AMOUNT_UP,
        "duration": DURATION_UP, "actor_count": COUNT_UP, "frequency": FREQ_UP,
    }[field_name].get(value)


def _is_under(field_name: str, leaf: str, ancestor: str) -> bool:
    node: Optional[str] = leaf
    steps = 0
    while node is not None and steps < 12:
        steps += 1
        if node == ancestor:
            return True
        node = _up(field_name, node)
    return False


def _support(field_name: str, value: str, released: List[Card]) -> int:
    """How many released cards have this fact at this value or finer."""
    return sum(1 for c in released if c.facts and _is_under(field_name, str(c.facts.get(field_name, "unknown")), value))


def generalise_facts(card: Card, released: List[Card], k: int = 3) -> Tuple[Card, List[Dict]]:
    """Generalise each identifier fact on a COPY of the card until >= k-1 other released cards share it.
    Returns (card_with_generalised_facts, per-fact status list for the preview)."""
    shown = copy.deepcopy(card)
    status: List[Dict] = []
    if not shown.facts:
        return shown, status
    f = shown.facts
    for name in IDENTIFIER_FIELDS:
        original = str(f.get(name, "unknown"))
        value = original
        while value is not None and _support(name, value, released) + 1 < k and _up(name, value) is not None:
            value = _up(name, value)
        if value is None:
            value = original
        f[name] = value
        status.append({"field": name, "original": original, "released": value,
                       "status": "kept" if value == original else "generalised",
                       "support": _support(name, value, released) + 1})
    # the card-level fields mirror the fact graph
    shown.location, shown.time_bucket = f["location"], f["time_bucket"]
    for name in ("acts", "digital", "consequences"):
        for v in f.get(name, []):
            status.append({"field": name, "original": v, "released": v, "status": "kept", "support": None})
    shown.generalisation_steps = [f"{s['field']}: {s['original']} -> {s['released']}" for s in status if s["status"] == "generalised"]
    return shown, status
