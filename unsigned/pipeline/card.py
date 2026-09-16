"""Incident card — the ONLY thing that ever leaves the sanitiser.

A card is a tuple of categorical fields plus a narrative generated from a
template over those fields. No author style can enter it, because nothing
free-form from the student is copied into it. The number of distinct cards
bounds the information the channel can carry: log2(#cards) bits.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

DISTRESS = ["none", "low", "high"]
URGENCY = ["routine", "soon", "immediate"]
TYPES = [
    "verbal_abuse", "physical", "coercion_forced_acts", "exclusion_social",
    "sexual_harassment", "extortion_financial", "cyber", "none",
]
ACTOR_ROLES = ["seniors", "peers", "unknown"]
MAX_TYPES_PER_CARD = 3

# Generalisation hierarchies: leaf -> parent, ... -> root. Extend per college.
LOCATION_HIERARCHY: Dict[str, Optional[str]] = {
    "hostel_a_floor1": "hostel_a", "hostel_a_floor2": "hostel_a", "hostel_a_floor3": "hostel_a",
    "hostel_b_floor1": "hostel_b", "hostel_b_floor2": "hostel_b", "hostel_b_floor3": "hostel_b",
    "hostel_a": "hostels", "hostel_b": "hostels", "hostel_c": "hostels", "hostels": "campus",
    "canteen": "common_areas", "mess": "common_areas", "library": "common_areas",
    "ground": "common_areas", "common_areas": "campus",
    "classroom": "academic", "lab": "academic", "corridor": "academic", "academic": "campus",
    "bus": "transit", "gate": "transit", "transit": "campus",
    "online": None, "campus": None, "unknown": None,
}
TIME_HIERARCHY: Dict[str, Optional[str]] = {
    "morning": "day", "afternoon": "day", "evening": "night_or_evening",
    "night": "night_or_evening", "day": "any", "night_or_evening": "any", "any": None, "unknown": None,
}
LOCATION_LEAVES = sorted(k for k in LOCATION_HIERARCHY)
TIME_LEAVES = sorted(k for k in TIME_HIERARCHY)


@dataclass
class Card:
    distress: str
    urgency: str
    types: List[str]
    location: str
    time_bucket: str
    actor_role: str
    behaviours: List[str] = field(default_factory=list)   # closed vocabulary from extract.py
    generalisation_steps: List[str] = field(default_factory=list)
    why: Dict[str, List[str]] = field(default_factory=dict)  # explanation features per head
    detail: Optional[str] = None                             # legacy field (unused); narrative comes from facts
    facts: Dict = field(default_factory=dict)                # closed-vocabulary fact graph (facts.py); no free text

    def narrative(self) -> str:
        """Style-free by construction: generated from the fact graph through the closed lexicon
        (narrate.py); falls back to the categorical template when no facts are present."""
        if self.facts:
            from .facts import Facts
            from .narrate import narrate
            return narrate(Facts.from_dict(self.facts), self.distress, self.urgency)
        return self.template_narrative()

    def template_narrative(self) -> str:
        """The minimal categorical sentence (the null template used by the audit)."""
        types = [t.replace("_", " ") for t in self.types if t != "none"] or ["an unspecified concern"]
        beh = f" Behaviours noted: {', '.join(b.replace('_', ' ') for b in self.behaviours)}." if self.behaviours else ""
        return (
            f"Reported: {', '.join(types)} involving {self.actor_role} at {self.location.replace('_', ' ')} "
            f"during {self.time_bucket.replace('_', ' ')}. Reporter distress: {self.distress}; urgency: {self.urgency}.{beh}"
        )

    def key(self) -> tuple:
        """The (location, time, types) combination that k-anonymity is enforced on."""
        return (self.location, self.time_bucket, tuple(sorted(self.types)))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["narrative"] = self.narrative()
        return d


def channel_capacity_bits(n_locations: int = len(LOCATION_LEAVES), n_times: int = len(TIME_LEAVES)) -> float:
    """log2 of the number of distinct cards the schema can express.

    Types: multi-label of up to MAX_TYPES_PER_CARD out of len(TYPES) classes.
    This is an upper bound on the information ANY card can carry about anything,
    including the author. Displayed on the Evidence tab.
    """
    n_type_combos = sum(math.comb(len(TYPES), r) for r in range(1, MAX_TYPES_PER_CARD + 1))
    n_cards = len(DISTRESS) * len(URGENCY) * n_type_combos * n_locations * n_times * len(ACTOR_ROLES)
    return math.log2(n_cards)


if __name__ == "__main__":
    c = Card("high", "soon", ["coercion_forced_acts"], "hostel_b", "night", "seniors", ["forced_standing"])
    print(c.narrative())
    print(f"channel capacity: {channel_capacity_bits():.1f} bits")
