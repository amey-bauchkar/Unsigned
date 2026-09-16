"""X0 — gazetteer/regex extractor: normalised text -> card fields.

Deliberately simple and transparent. Every extracted field carries the span
that produced it so the console can show "why" without showing the text.
Extend the gazetteers from the corpus; a span model (X1) may replace this
later only if it beats it on annotated fields.
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

# location cue -> location leaf
LOCATION_GAZETTEER: Dict[str, str] = {
    r"\bhostel\s*a\b": "hostel_a", r"\ba\s*hostel\b": "hostel_a",
    r"\bhostel\s*b\b": "hostel_b", r"\bb\s*hostel\b": "hostel_b",
    r"\bhostel\s*c\b": "hostel_c",
    r"\b(second|<num>)\s*floor\b": "__floor__",       # refines a hostel leaf if one was found
    r"\bhostel\b": "hostels",
    r"\bcanteen\b": "canteen", r"\bmess\b": "mess", r"\blibrary\b": "library",
    r"\bground\b": "ground", r"\bfield\b": "ground",
    r"\bclass(room)?\b": "classroom", r"\blab\b": "lab", r"\bcorridor\b": "corridor",
    r"\bbus\b": "bus", r"\bgate\b": "gate",
    r"\b(whatsapp|insta|instagram|group|online|dm|call)\b": "online",
}
TIME_GAZETTEER: Dict[str, str] = {
    r"\b(raat|night|midnight|<num>\s*baje\s*raat|late)\b": "night",
    r"\b(subah|morning)\b": "morning",
    r"\b(dopahar|afternoon|lunch)\b": "afternoon",
    r"\b(shaam|sham|evening|sandhyakali)\b": "evening",
}
ACTOR_GAZETTEER: Dict[str, str] = {
    r"\b(senior|seniors|final\s*year|third\s*year|te|be)\b": "seniors",
    r"\b(classmate|classmates|batchmate|batchmates|roommate|friends?)\b": "peers",
}
# behaviour cue -> closed-vocabulary behaviour
BEHAVIOUR_GAZETTEER: Dict[str, str] = {
    r"\b(khade|khada|stand(ing)?|ubha)\b": "forced_standing",
    r"\b(intro|introduction|introduce)\b": "forced_introductions",
    r"\b(gaali|gali|abuse|abusive|insult|bakwas|chidhana|mock(ed|ing)?)\b": "verbal_abuse",
    r"\b(thappad|maara|mara|hit|slap|beat|push(ed)?|dhakka)\b": "physical_violence",
    r"\b(paise|paisa|money|treat|pay|recharge|rupees?|rs|rupaye)\b": "money_demand",
    r"\b(photo|video|record(ed|ing)?|screenshot)\b": "recording",
    r"\b(ignore|alag|exclude|bahishkar|nobody talks|koi baat)\b": "exclusion",
    r"\b(touch|chhu|inappropriate|comment on body|ganda)\b": "unwanted_contact",
    r"\b(threat|dhamki|dhamkaya|warn(ed)?)\b": "threats",
    r"\b(sleep|sone|neend|so nahi)\b": "sleep_deprivation",
    r"\b(took|le gaye|le liya|chheen|cheen|snatch(ed)?|charger|phone le)\b": "taking_belongings",
    r"\b(come back|wapas aana|bulaya|bulate|bulaate)\b": "summoning",
}
BEHAVIOUR_TO_TYPE = {
    "forced_standing": "coercion_forced_acts", "forced_introductions": "coercion_forced_acts",
    "sleep_deprivation": "coercion_forced_acts",
    "verbal_abuse": "verbal_abuse", "threats": "verbal_abuse",
    "physical_violence": "physical", "money_demand": "extortion_financial",
    "recording": "cyber", "exclusion": "exclusion_social", "unwanted_contact": "sexual_harassment",
    "taking_belongings": "extortion_financial", "summoning": "coercion_forced_acts",
}


def _first_match(gaz: Dict[str, str], text: str) -> List[Tuple[str, str]]:
    hits = []
    for pat, label in gaz.items():
        m = re.search(pat, text)
        if m:
            hits.append((label, m.group(0)))
    return hits


def extract(norm_text: str) -> dict:
    """Return extracted fields + the spans that justified them (for the 'why' card)."""
    loc_hits = _first_match(LOCATION_GAZETTEER, norm_text)
    location, loc_span = "unknown", ""
    floor = any(lbl == "__floor__" for lbl, _ in loc_hits)
    for lbl, span in loc_hits:
        if lbl == "__floor__":
            continue
        # prefer the most specific hostel leaf
        if location == "unknown" or (lbl.startswith("hostel_") and lbl != "hostels"):
            location, loc_span = lbl, span
    if floor and location in ("hostel_a", "hostel_b"):
        location = f"{location}_floor2"          # floor refinement (demo hierarchy)

    time_hits = _first_match(TIME_GAZETTEER, norm_text)
    time_bucket, time_span = (time_hits[0] if time_hits else ("unknown", ""))

    actor_hits = _first_match(ACTOR_GAZETTEER, norm_text)
    actor_role, actor_span = (actor_hits[0] if actor_hits else ("unknown", ""))

    beh_hits = _first_match(BEHAVIOUR_GAZETTEER, norm_text)
    behaviours = sorted({lbl for lbl, _ in beh_hits})
    types_from_beh = sorted({BEHAVIOUR_TO_TYPE[b] for b in behaviours})

    return {
        "location": location, "time_bucket": time_bucket, "actor_role": actor_role,
        "behaviours": behaviours, "types_from_behaviours": types_from_beh,
        "spans": {"location": loc_span, "time": time_span, "actor": actor_span,
                  "behaviours": [s for _, s in beh_hits]},
    }


if __name__ == "__main__":
    from .normalize import normalize
    print(extract(normalize("Seniors ne hostel B second floor pe raat ko 3 ghante khade rakha aur gaali di, paise bhi maange")))
