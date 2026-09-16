"""Transparent decision rules applied AFTER the classifier and the fact graph.

These are not tuned to any dataset. They encode two things a human reader does instinctively:

  1. A campus-services complaint (mess, wifi, printer, AC, timetable...) with no ragging act and no
     personal consequence is not a ragging report — however strongly the text is worded.
  2. A sarcastic report of a real act ("wow such a warm welcome, 3 hours standing") is a distressed
     report, however cheerful its surface.

Every rule that fires is recorded in the card's `why` so the committee (and a judge) can see it.
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

from .facts import Facts

MUNDANE_CUES = re.compile(
    r"\b(mess|canteen|khana|khaana|jevan|food|thanda|cold again|wifi|wi fi|internet|network|printer|xerox|ac|a c|"
    r"air condition\w*|fan|light nahi|lights?|electricity|bijli|paani|pani|water cooler|water|cooler|library|"
    r"timetable|time table|notice board|portal|attendance|erp|website|bus|shuttle|gym|projector|classroom|lab|"
    r"id card|fees|fee|form|schedule|exam|hostel room|room allot\w*|laundry|cleaning|garbage|toilet|bathroom|"
    r"washroom|lift|elevator|parking|mahag|expensive|price|rate|charger point|plug|socket|samosa|chai|tea|coffee)\b"
)
SARCASM_CUES = re.compile(
    r"(\?\?|\bhmm\b|\bwow\b|\bgreat\b|\blovely\b|\bamazing\b|\bhilarious\b|\bbrilliant\b|\bwah\b|\bwaah\b|"
    r"mazaa aa gaya|maza aa gaya|what a surprise|so kind|thanks a lot|love how|such a warm|great tradition|"
    r"very professional|obviously|honestly|as a joke|fine i guess|what a welcome|kya welcome|kya baat)"
)
NEGATION_CUES = re.compile(
    r"\b(kahich\s*karat\s*nahi|kahi\s*karat\s*nahi|kahi\s*nahi|kahich\s*nahi|kahi\s*zala?\s*nahi|kahich\s*zala?\s*nahi|"
    r"kuch\s*nahi\s*karte|kuch\s*nahi\s*kiya|kuch\s*nahi\s*hua|kuch\s*nahi|kuch\s*nhi|koi\s*dikkat\s*nahi|koi\s*problem\s*nahi|"
    r"sab\s*theek|sab\s*thik|pareshan\s*nahi|traas\s*det\s*nahi|tras\s*det\s*nahi|traas\s*nahi|tras\s*nahi|"
    r"nothing\s*happened|do\s*nothing|did\s*nothing|does\s*nothing|didn.?t\s*do\s*anything|haven.?t\s*done\s*anything|"
    r"no\s*ragging|no\s*problem|all\s*good|nobody\s*(harasses|harassed|troubles|bothers)|not\s*ragging)\b",
    re.IGNORECASE
)


def apply_rules(norm_text: str, pred: Dict, facts: Facts) -> Tuple[Dict, List[str]]:
    """Return (adjusted prediction, list of rules that fired)."""
    fired: List[str] = []
    has_act = bool(facts.acts)
    has_consequence = bool(facts.consequences)
    mundane = bool(MUNDANE_CUES.search(norm_text))
    sarcastic = bool(SARCASM_CUES.search(norm_text))
    negation = bool(NEGATION_CUES.search(norm_text))
    p = dict(pred)

    if not has_act and not has_consequence and (mundane or negation):
        reason = "statement indicates no incident occurred with no act and no consequence -> not a ragging report" if negation else "campus-services complaint with no act and no personal consequence -> not a ragging report"
        if p.get("distress") != "none" or p.get("urgency") != "routine" or p.get("types") != ["none"]:
            fired.append(reason)
        p["distress"], p["urgency"], p["types"] = "none", "routine", ["none"]

    if sarcastic and has_act:
        p["sarcasm"] = "1"
        if p.get("distress") != "high":
            fired.append("sarcastic wording about a real act -> distress high")
            p["distress"] = "high"
        if p.get("urgency") == "routine":
            p["urgency"] = "soon"

    if has_act and p.get("distress") == "none":
        fired.append("a ragging act is described -> distress at least low")
        p["distress"] = "low"

    return p, fired
