"""Fact extraction — the student's story as a graph of closed-vocabulary facts.

Every fact value comes from a finite set defined here. Numbers are banded. Free text never
enters a fact. This is what makes the regenerated narrative (narrate.py) style-free by
construction: it can only ever say things this module can represent.

Spans (the student's own words that triggered a fact) are returned for the privacy
preview — shown to the student, never stored, never sent to the committee.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

# ----------------------------------------------------------------------------- closed sets
ACTS = [
    "forced_standing", "forced_introductions", "forced_performance", "forced_errands", "sleep_deprivation",
    "verbal_abuse", "threats", "physical_violence", "pushing", "money_demand", "taking_belongings",
    "phone_confiscation", "recording", "sharing_online", "exclusion", "unwanted_contact", "sexual_comments",
    "summoning", "room_intrusion", "substance_coercion", "public_humiliation", "confinement",
]
ACT_TO_TYPE = {
    "forced_standing": "coercion_forced_acts", "forced_introductions": "coercion_forced_acts",
    "forced_performance": "coercion_forced_acts", "forced_errands": "coercion_forced_acts",
    "sleep_deprivation": "coercion_forced_acts", "summoning": "coercion_forced_acts",
    "room_intrusion": "coercion_forced_acts", "substance_coercion": "coercion_forced_acts", "confinement": "coercion_forced_acts",
    "verbal_abuse": "verbal_abuse", "threats": "verbal_abuse", "public_humiliation": "verbal_abuse",
    "physical_violence": "physical", "pushing": "physical",
    "money_demand": "extortion_financial", "taking_belongings": "extortion_financial", "phone_confiscation": "extortion_financial",
    "recording": "cyber", "sharing_online": "cyber",
    "exclusion": "exclusion_social",
    "unwanted_contact": "sexual_harassment", "sexual_comments": "sexual_harassment",
}
ACTOR_ROLES = ["seniors", "peers", "staff", "unknown"]
ACTOR_COUNTS = ["one", "few", "group", "unknown"]
FREQUENCIES = ["once", "repeated", "daily", "unknown"]
DURATIONS = ["under_30m", "30m_2h", "2h_5h", "over_5h", "unknown"]
AMOUNTS = ["none", "under_100", "100_500", "500_2000", "over_2000", "some"]
DIGITAL = ["video", "photo", "messaging_group", "direct_messages"]
CONSEQUENCES = ["fear", "sleep_loss", "injury", "missed_classes", "cant_focus", "isolation", "mental_distress"]

# ----------------------------------------------------------------------------- cue lexicons (normalised text)
ACT_CUES: Dict[str, str] = {
    r"\b(khade|khada|khadi|stand(ing)?|ubha|ubhe|ubhi|ubhan|ubhaa|ubh\w+|khade rakh\w*)\b": "forced_standing",
    r"\b(intro|introduction|introduce|introductions|parichay)\b": "forced_introductions",
    r"\b(dance|naach|nacho|sing|gaana|gao|perform|act|mimicry|propose)\b": "forced_performance",
    r"\b(errand|errands|chai lao|lao|le aao|kaam karwa|kaam karva|bring us)\b": "forced_errands",
    r"\b(sone nahi de|sone nahi di|so nahi de|sone nai de|not let (us|me) sleep|kept (us|me) awake|jaagte rakha|jagaya|jagate|jaga ke|zopu det nahi|zopu dile nahi|wake us|uthate)\b": "sleep_deprivation",
    r"\b(gaali|gali|galiya|abuse|abusive|insult|insulting|bakwas|chidhana|chidhate|mock(ed|ing)?|comments?|shivya)\b": "verbal_abuse",
    r"\b(threat|threaten(ed|ing)?|dhamki|dhamkaya|dhamkate|dhamkavtat|warn(ed)?|dekh lenge|dekh lunga|bhugatna|consequences|aggressive(ly)?|gussa|chilla\w*|shout(ed|ing)?|scream(ed|ing)?|oradtat|ordatat)\b": "threats",
    r"\b(thappad|maara|mara|marte|maarte|hit|slap(ped)?|beat|beaten|punch(ed)?|kick(ed)?|marhan|maarla|maarle|threw|throw(n|ing)?|feka|phenka|fek diya|paani feka|water on me|choked|strangl\w*|burn\w*|jalaya|laat|laath)\b": "physical_violence",
    r"\b(push(ed)?|dhakka|dhakkela|shove(d)?)\b": "pushing",
    r"\b(paise|paisa|money|treats?|pay|recharge|rupees?|rs|rupaye|rupye|udhaar|contribution|maagit\w*|magit\w*|maang\w*|mang\w*|demand(ed|ing)?)\b": "money_demand",
    r"\b(took|le gaye|le liya|chheen|cheen|snatch(ed)?|charger|laptop le|bag le|nele|ghetla)\b": "taking_belongings",
    r"\b(phone le|phone liya|phone cheen|took my phone|phone confiscat|mobile le)\b": "phone_confiscation",
    r"\b(video|photo|record(ed|ing)?|screenshot|clip|reel|filmed)\b": "recording",
    r"\b(whatsapp|insta|instagram|group me|group pe|group madhe|shared|share kiya|forward|viral|posted|story)\b": "sharing_online",
    r"\b(ignore|alag|exclude|excluded|bahishkar|nobody talks|koi baat|boycott|alone|akela|akeli|ekta)\b": "exclusion",
    r"\b(touch(ed|ing)?|chhu|chhua|inappropriate|grab(bed)?|hug|pakad)\b": "unwanted_contact",
    r"\b(ganda|dirty|sexual|body shaming|figure|dress|kapde|looks|vulgar|ashleel)\b": "sexual_comments",
    r"\b(come back|wapas aana|bulaya|bulate|bulaate|bolaya|report karo|aana hai|summon(ed)?)\b": "summoning",
    r"\b(room me aake|room me ghus|room pe aake|entered (my|our) room|room madhe|barged)\b": "room_intrusion",
    r"\b(locked|lock kar|band kar diya|band karke|bahar nahi (jaane|jane) d\w*|jaane nahi d\w*|jane nahi d\w*|nikalne nahi|wouldn.?t let (me|us) (leave|go)|not let (me|us) (leave|go)|didn.?t let (me|us) (leave|go)|kondun|kondla|confined|trapped|kept (me|us) in)\b": "confinement",
    r"\b(drink|daaru|sharab|beer|alcohol|smoke|cigarette|weed|ganja|pilaya|peene)\b": "substance_coercion",
    r"\b(sabke saamne|sabke samne|sbke samne|sbke saamne|sab ke saamne|sagle samor|saglya samor|in front of everyone|in front of others|in front of all|publicly|humiliat(ed|ion)|sharminda|embarrass(ed|ing)?)\b": "public_humiliation",
}
ACTOR_CUES: Dict[str, str] = {
    r"\b(senior|seniors|srs|final\s*year|third\s*year|te|be|te wale|final year wale)\b": "seniors",
    r"\b(classmate|classmates|batchmate|batchmates|roommate|roommates|friends?|same class)\b": "peers",
    r"\b(warden|professor|sir|faculty|staff|guard|hod)\b": "staff",
}
COUNT_CUES: List[Tuple[str, str]] = [
    (r"\b(ek senior|one senior|a senior|ek ladka|one guy|ek banda|one of them|a final year)\b", "one"),
    (r"\b(do teen|2 3|two or three|couple of|few|kuch)\b", "few"),
    (r"\b(seniors|group|gang|bahut log|sab|everyone|sabhi|log|they all|bunch)\b", "group"),
]
FREQ_CUES: List[Tuple[str, str]] = [
    (r"\b(roz|daily|har din|every day|everyday|har raat|every night|rojcha|roj)\b", "daily"),
    (r"\b(phir se|again|repeatedly|baar baar|bar bar|second time|third time|<num> time|<num>nd time|<num>rd time|har baar|every time|regularly|weekly|har hafte|punha|parat)\b", "repeated"),
    (r"\b(kal|yesterday|aaj|today|last night|ek baar|once|one time)\b", "once"),
]
ONGOING_CUES = r"\b(abhi bhi|still|ab bhi|continuing|chalu|ongoing|going on|har raat|daily|roz|ajun)\b"
DURATION_CUES: List[Tuple[str, str]] = [
    (r"\b(<num>\s*(ghante|ghanta|hours?|hrs?|taas|tas))\b", "__hours__"),
    (r"\b(<num>\s*(minute|minutes|min|mins|minat))\b", "__minutes__"),
    (r"\b(saari raat|poori raat|whole night|all night|raat bhar|ratra bhar)\b", "over_5h"),
]
DIGITAL_CUES: Dict[str, str] = {
    r"\b(video|clip|reel|filmed|recording)\b": "video",
    r"\b(photo|photos|pic|pics|screenshot|selfie)\b": "photo",
    r"\b(whatsapp|group|insta|instagram|telegram|story|posted|viral)\b": "messaging_group",
    r"\b(dm|dms|message|messages|msg|texting|calls?)\b": "direct_messages",
}
CONSEQUENCE_CUES: Dict[str, str] = {
    r"\b(dar|darr|bhiti|scared|afraid|fear|panic|ghabra|khatra|dar lagta|dar lag)\b": "fear",
    r"\b(neend nahi|neend nai|nind nahi|cant sleep|can't sleep|not sleeping|sleep nahi|so nahi pa|zop yet nahi|zop nahi|sleepless|neend aati|neend)\b": "sleep_loss",
    r"\b(chot|injury|injured|hurt|bleeding|khoon|fracture|cant walk|can't walk|limping|dard|pain|sujan)\b": "injury",
    r"\b(class miss|missed class|classes|attendance|bunk|lecture miss|nahi ja pa)\b": "missed_classes",
    r"\b(focus|concentrate|padhai|study|studies|dhyan|abhyas)\b": "cant_focus",
    r"\b(akela|akeli|alone|isolated|ekta|nobody|koi nahi)\b": "isolation",
    r"\b(takleef|taklif|pareshan|tension|stress(ed)?|depress\w*|mentally|mental|anxiety|anxious|rona|roti hu|rota hu|cry(ing)?|cried|tras|tanav|vaatate|vatate)\b": "mental_distress",
}
PUBLIC_CUES = r"\b(sabke saamne|sabke samne|sbke samne|sbke saamne|sab ke saamne|sagle samor|saglya samor|in front of everyone|in front of others|in front of all|publicly|sab dekh|everyone saw|sagle)\b"

_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")


@dataclass
class Facts:
    acts: List[str] = field(default_factory=list)
    actor_role: str = "unknown"
    actor_count: str = "unknown"
    location: str = "unknown"
    time_bucket: str = "unknown"
    frequency: str = "unknown"
    duration: str = "unknown"
    amount: str = "none"
    digital: List[str] = field(default_factory=list)
    consequences: List[str] = field(default_factory=list)
    public: bool = False
    ongoing: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Facts":
        f = Facts()
        for k, v in (d or {}).items():
            if hasattr(f, k):
                setattr(f, k, v)
        return f

    def types(self) -> List[str]:
        return sorted({ACT_TO_TYPE[a] for a in self.acts if a in ACT_TO_TYPE})


def _amount_band(rupees: float) -> str:
    return "under_100" if rupees < 100 else "100_500" if rupees <= 500 else "500_2000" if rupees <= 2000 else "over_2000"


def _duration_band(hours: float) -> str:
    return "under_30m" if hours < 0.5 else "30m_2h" if hours <= 2 else "2h_5h" if hours <= 5 else "over_5h"


NUMBER_WORDS = {
    "ek": 1, "one": 1, "do": 2, "two": 2, "teen": 3, "three": 3, "char": 4, "chaar": 4, "four": 4, "paanch": 5, "panch": 5,
    "five": 5, "che": 6, "chhe": 6, "six": 6, "saat": 7, "seven": 7, "aath": 8, "eight": 8, "nau": 9, "nine": 9, "das": 10,
    "ten": 10, "sau": 100, "hundred": 100, "hazaar": 1000, "hazar": 1000, "thousand": 1000, "half": 0.5, "aadha": 0.5, "adha": 0.5,
    "dedh": 1.5, "dhai": 2.5, "ardha": 0.5, "don": 2, "tin": 3, "paach": 5, "daha": 10, "shambhar": 100, "hajar": 1000,
}
_NUM_WORD_RE = re.compile(r"\b(" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")\b(?=\s+\w)", re.I)


def _words_to_digits(text: str) -> str:
    """'three hours' -> '3 hours', 'paanch sau rupees' -> '5 100 rupees' (then '5 100' -> 500 below)."""
    t = _NUM_WORD_RE.sub(lambda m: str(NUMBER_WORDS[m.group(1).lower()]), text)
    t = re.sub(r"\b(\d+)\s+(100|1000)\b", lambda m: str(int(m.group(1)) * int(m.group(2))), t)   # "5 100" -> 500
    return t


def _numbers_before(raw_text: str, unit_pattern: str) -> List[float]:
    """Numbers in the RAW text that precede a unit (raw text keeps the digits the normaliser replaces)."""
    out = []
    raw_text = _words_to_digits(raw_text)
    for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s*(?:" + unit_pattern + r")\b", raw_text.lower()):
        try:
            out.append(float(m.group(1).replace(",", "")))
        except ValueError:
            pass
    return out


def extract_facts(norm_text: str, raw_text: str, location: str, time_bucket: str) -> Tuple[Facts, Dict[str, List[str]]]:
    """Build the fact graph from the normalised text (cues) and the raw text (numbers)."""
    spans: Dict[str, List[str]] = {}
    f = Facts(location=location, time_bucket=time_bucket)

    def hits(gaz: Dict[str, str], key: str) -> List[str]:
        found = []
        for pat, label in gaz.items():
            m = re.search(pat, norm_text)
            if m:
                found.append(label); spans.setdefault(key, []).append(m.group(0))
        return found

    f.acts = sorted(set(hits(ACT_CUES, "acts")))
    roles = hits(ACTOR_CUES, "actor")
    f.actor_role = "seniors" if "seniors" in roles else (roles[0] if roles else "unknown")
    for pat, label in COUNT_CUES:
        if re.search(pat, norm_text):
            f.actor_count = label; break
    if f.actor_count == "unknown" and f.actor_role == "seniors":
        f.actor_count = "group"
    for pat, label in FREQ_CUES:
        if re.search(pat, norm_text):
            f.frequency = label; break
    f.ongoing = bool(re.search(ONGOING_CUES, norm_text)) or f.frequency == "daily"   # "every day" is, by definition, ongoing

    hours = _numbers_before(raw_text, r"ghante|ghanta|hours?|hrs?|taas|tas")
    mins = _numbers_before(raw_text, r"minutes?|mins?|minat")
    if hours:
        f.duration = _duration_band(max(hours)); spans.setdefault("duration", []).append(f"{int(max(hours))} hours")
    elif mins:
        f.duration = _duration_band(max(mins) / 60); spans.setdefault("duration", []).append(f"{int(max(mins))} minutes")
    else:
        for pat, label in DURATION_CUES:
            m = re.search(pat, norm_text)
            if m and not label.startswith("__"):
                f.duration = label; spans.setdefault("duration", []).append(m.group(0)); break

    rupees = _numbers_before(raw_text, r"rupees?|rs\.?|rupaye|rupye|rupaiye|rupaya|rupaiya|₹|inr|/-")
    rupees += [float(m.group(1)) for m in re.finditer(r"(?:₹|rs\.?\s*)(\d+)", raw_text.lower())]
    if rupees:
        f.amount = _amount_band(max(rupees)); spans.setdefault("amount", []).append(f"{int(max(rupees))} rupees")
    elif "money_demand" in f.acts or "taking_belongings" in f.acts:
        f.amount = "some"

    f.digital = sorted(set(hits(DIGITAL_CUES, "digital")))
    f.consequences = sorted(set(hits(CONSEQUENCE_CUES, "consequences")))
    f.public = bool(re.search(PUBLIC_CUES, norm_text))
    if f.public and "public_humiliation" not in f.acts and f.acts:
        f.acts = sorted(set(f.acts) | {"public_humiliation"})
    return f, spans


def apply_override(f: Facts, override: Optional[dict]) -> Facts:
    """Student edits from the privacy preview — validated against the closed sets, never free text."""
    if not override:
        return f
    g = Facts.from_dict(f.to_dict())
    if "acts" in override:
        g.acts = sorted({a for a in override["acts"] if a in ACTS})
    if "actor_role" in override and override["actor_role"] in ACTOR_ROLES:
        g.actor_role = override["actor_role"]
    if "actor_count" in override and override["actor_count"] in ACTOR_COUNTS:
        g.actor_count = override["actor_count"]
    if "frequency" in override and override["frequency"] in FREQUENCIES:
        g.frequency = override["frequency"]
    if "duration" in override and override["duration"] in DURATIONS:
        g.duration = override["duration"]
    if "amount" in override and override["amount"] in AMOUNTS:
        g.amount = override["amount"]
    if "digital" in override:
        g.digital = sorted({d for d in override["digital"] if d in DIGITAL})
    if "consequences" in override:
        g.consequences = sorted({c for c in override["consequences"] if c in CONSEQUENCES})
    for b in ("public", "ongoing"):
        if b in override:
            setattr(g, b, bool(override[b]))
    from .card import LOCATION_HIERARCHY, TIME_HIERARCHY
    if override.get("location") in LOCATION_HIERARCHY:
        g.location = override["location"]
    if override.get("time_bucket") in TIME_HIERARCHY:
        g.time_bucket = override["time_bucket"]
    return g


def options() -> dict:
    """Closed option lists for the student's fact editor."""
    from .card import LOCATION_HIERARCHY, TIME_HIERARCHY
    return {
        "acts": ACTS, "actor_role": ACTOR_ROLES, "actor_count": ACTOR_COUNTS, "frequency": FREQUENCIES,
        "duration": DURATIONS, "amount": AMOUNTS, "digital": DIGITAL, "consequences": CONSEQUENCES,
        "location": [k for k in LOCATION_HIERARCHY if k not in ("campus",)], "time_bucket": [k for k in TIME_HIERARCHY if k != "any"],
    }
