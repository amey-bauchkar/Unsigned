"""Controlled narration — a full account of what happened, generated only from Unsigned's own lexicon.

The narrative is produced by a fixed grammar over the fact graph. Every word the committee reads
is drawn from LEXICON, which is built from the grammar's own fragments at import time. The
student's text is never consulted here; it cannot be, because this module never receives it.

`narrate()` enforces the invariant at runtime: if any emitted token is outside the lexicon,
it raises LexiconViolation rather than release it. `evaluate.py` and the tests count violations
over the whole corpus (the number must be 0).
"""
from __future__ import annotations

import math
import re
from typing import List

from .facts import (ACTS, ACTOR_COUNTS, ACTOR_ROLES, AMOUNTS, CONSEQUENCES, DIGITAL, DURATIONS, FREQUENCIES, Facts)


class LexiconViolation(RuntimeError):
    pass


SUBJECT = {
    ("seniors", "one"): "A senior student", ("seniors", "few"): "A few senior students",
    ("seniors", "group"): "A group of senior students", ("seniors", "unknown"): "Senior students",
    ("peers", "one"): "A classmate", ("peers", "few"): "A few classmates", ("peers", "group"): "A group of classmates",
    ("peers", "unknown"): "Classmates",
    ("staff", "one"): "A member of staff", ("staff", "few"): "Members of staff", ("staff", "group"): "Members of staff",
    ("staff", "unknown"): "A member of staff",
    ("unknown", "one"): "Someone", ("unknown", "few"): "A few people", ("unknown", "group"): "A group of people",
    ("unknown", "unknown"): "Someone",
}
# verb phrases; {dur} and {amt} are filled from closed bands
ACT_PHRASE = {
    "forced_standing": "made the reporter stand{dur}",
    "forced_introductions": "forced the reporter to give repeated introductions",
    "forced_performance": "made the reporter perform on demand",
    "forced_errands": "made the reporter run errands",
    "sleep_deprivation": "prevented the reporter from sleeping",
    "verbal_abuse": "used abusive and insulting language",
    "threats": "threatened the reporter",
    "physical_violence": "physically assaulted the reporter",
    "pushing": "pushed the reporter",
    "money_demand": "demanded money{amt}",
    "taking_belongings": "took the reporter's belongings",
    "phone_confiscation": "took the reporter's phone",
    "recording": "recorded the reporter",
    "sharing_online": "shared material about the reporter online",
    "exclusion": "excluded the reporter socially",
    "unwanted_contact": "touched the reporter inappropriately",
    "sexual_comments": "made sexual or body-related comments",
    "summoning": "summoned the reporter repeatedly",
    "room_intrusion": "entered the reporter's room uninvited",
    "substance_coercion": "pressured the reporter to consume alcohol or other substances",
    "public_humiliation": "humiliated the reporter in front of others",
    "confinement": "prevented the reporter from leaving",
}
DUR_PHRASE = {"under_30m": " for under half an hour", "30m_2h": " for up to two hours", "2h_5h": " for two to five hours",
              "over_5h": " for more than five hours", "unknown": ""}
AMT_PHRASE = {"none": "", "under_100": " (under one hundred rupees)", "100_500": " (one hundred to five hundred rupees)",
              "500_2000": " (five hundred to two thousand rupees)", "over_2000": " (more than two thousand rupees)",
              "some": " (an unspecified amount)"}
PLACE_PHRASE = {
    "hostel_a": "in Hostel A", "hostel_b": "in Hostel B", "hostel_c": "in Hostel C",
    "hostel_a_floor1": "on the first floor of Hostel A", "hostel_a_floor2": "on the second floor of Hostel A", "hostel_a_floor3": "on the third floor of Hostel A",
    "hostel_b_floor1": "on the first floor of Hostel B", "hostel_b_floor2": "on the second floor of Hostel B", "hostel_b_floor3": "on the third floor of Hostel B",
    "hostels": "in a hostel", "canteen": "in the canteen", "mess": "in the mess", "library": "in the library", "ground": "on the ground",
    "common_areas": "in a common area", "classroom": "in a classroom", "lab": "in a laboratory", "corridor": "in a corridor",
    "academic": "in the academic block", "bus": "on the bus", "gate": "at the gate", "transit": "on the way to or from campus",
    "online": "online", "campus": "on campus", "unknown": "",
}
TIME_PHRASE = {"morning": "in the morning", "afternoon": "in the afternoon", "evening": "in the evening", "night": "at night",
               "day": "during the day", "night_or_evening": "in the evening or at night", "any": "", "unknown": ""}
FREQ_SENTENCE = {"once": "This is reported as a single incident.", "repeated": "This has happened more than once.",
                 "daily": "This is happening every day.", "unknown": ""}
ONGOING_SENTENCE = "It is still going on."
PUBLIC_SENTENCE = "Other students were present."
DIGITAL_PHRASE = {"video": "a video", "photo": "photographs", "messaging_group": "a messaging group", "direct_messages": "direct messages"}
CONSEQ_PHRASE = {"fear": "fear", "sleep_loss": "loss of sleep", "injury": "a physical injury", "missed_classes": "missing classes",
                 "cant_focus": "difficulty concentrating on studies", "isolation": "feeling isolated",
                 "mental_distress": "mental distress"}
DISTRESS_SENTENCE = {"none": "The reporter does not express personal distress.", "low": "The reporter expresses some distress.",
                     "high": "The reporter expresses serious distress."}
URGENCY_PHRASE = {"routine": "Urgency: routine.", "soon": "Urgency: soon.", "immediate": "Urgency: immediate."}
NO_ACT_SENTENCE = "The reporter describes a situation without a specific act identified."


def _join(items: List[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def narrate(f: Facts, distress: str = "none", urgency: str = "routine") -> str:
    """Deterministic narrative from facts only. Same facts -> same words, always."""
    subj = SUBJECT.get((f.actor_role, f.actor_count), "Someone")
    acts = [a for a in f.acts if a in ACT_PHRASE]
    phrases = [ACT_PHRASE[a].format(dur=DUR_PHRASE.get(f.duration, ""), amt=AMT_PHRASE.get(f.amount, "")) for a in acts]
    where = " ".join(x for x in (PLACE_PHRASE.get(f.location, ""), TIME_PHRASE.get(f.time_bucket, "")) if x)
    sentences: List[str] = []
    if phrases:
        s = f"{subj} {_join(phrases)}"
        if where:
            s += f" {where}"
        sentences.append(s + ".")
    else:
        sentences.append(NO_ACT_SENTENCE + (f" It took place {where}." if where else ""))
    if f.digital:
        sentences.append(f"{_join([DIGITAL_PHRASE[d] for d in f.digital if d in DIGITAL_PHRASE]).capitalize()} {'were' if len(f.digital) > 1 or f.digital == ['photo'] or f.digital == ['direct_messages'] else 'was'} involved.")
    if FREQ_SENTENCE.get(f.frequency):
        sentences.append(FREQ_SENTENCE[f.frequency])
    if f.ongoing:
        sentences.append(ONGOING_SENTENCE)
    if f.public:
        sentences.append(PUBLIC_SENTENCE)
    if f.consequences:
        sentences.append(f"The reporter describes {_join([CONSEQ_PHRASE[c] for c in f.consequences if c in CONSEQ_PHRASE])}.")
    sentences.append(f"{DISTRESS_SENTENCE.get(distress, DISTRESS_SENTENCE['none'])} {URGENCY_PHRASE.get(urgency, URGENCY_PHRASE['routine'])}")
    text = " ".join(sentences)
    bad = foreign_tokens(text)
    if bad:
        raise LexiconViolation(f"tokens outside the lexicon: {bad}")
    return text


# ----------------------------------------------------------------------------- the lexicon
def _tokens(s: str) -> List[str]:
    return re.findall(r"[a-z]+(?:'[a-z]+)?|[a-z]+-[a-z]+", s.lower())


def _build_lexicon() -> frozenset:
    words = set()
    for src in (SUBJECT.values(), ACT_PHRASE.values(), DUR_PHRASE.values(), AMT_PHRASE.values(), PLACE_PHRASE.values(),
                TIME_PHRASE.values(), FREQ_SENTENCE.values(), DIGITAL_PHRASE.values(), CONSEQ_PHRASE.values(),
                DISTRESS_SENTENCE.values(), URGENCY_PHRASE.values(),
                [ONGOING_SENTENCE, PUBLIC_SENTENCE, NO_ACT_SENTENCE, "and were was involved it took place"]):
        for s in src:
            words.update(_tokens(s))
    return frozenset(words)


LEXICON = _build_lexicon()


def foreign_tokens(text: str) -> List[str]:
    return [t for t in _tokens(text) if t not in LEXICON]


def narrative_capacity_bits() -> float:
    """Upper bound on the information a narrative can carry: the size of the fact space.
    Includes the card fields the sentence also encodes (distress, urgency)."""
    n = (2 ** len(ACTS)) * len(ACTOR_ROLES) * len(ACTOR_COUNTS) * len(FREQUENCIES) * len(DURATIONS) * len(AMOUNTS) \
        * (2 ** len(DIGITAL)) * (2 ** len(CONSEQUENCES)) * 2 * 2 * len(PLACE_PHRASE) * len(TIME_PHRASE) * 3 * 3
    return math.log2(n)


if __name__ == "__main__":
    f = Facts(acts=["forced_standing", "money_demand", "recording"], actor_role="seniors", actor_count="group",
              location="hostel_b", time_bucket="night", frequency="repeated", duration="2h_5h", amount="100_500",
              digital=["video", "messaging_group"], consequences=["fear", "sleep_loss"], ongoing=True)
    print(narrate(f, "high", "soon"))
    print(f"lexicon: {len(LEXICON)} words · narrative capacity ≈ {narrative_capacity_bits():.1f} bits")
