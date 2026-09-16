"""N1 — lexical normaliser.

This is a *pre-processor for classification*, not the privacy mechanism.
The privacy mechanism is that raw text is never released (see card.py, audit.py).
Normalising helps the classifier generalise across spelling variants and lets us
report how much an attacker loses from normalisation alone (spoiler: not enough).
"""
from __future__ import annotations

import re
import unicodedata

from .translit import transliterate

# Common roman-script Hindi/Marathi spelling variants → canonical form.
# Extend from the corpus as annotators notice variants.
SPELLING_VARIANTS = {
    "nhi": "nahi", "nai": "nahi", "nahin": "nahi", "nhe": "nahi",
    "kyu": "kyun", "kyon": "kyun", "q": "kyun",
    "h": "hai", "hn": "hai", "hain": "hai", "hy": "hai",
    "krte": "karte", "krta": "karta", "krti": "karti", "kr": "kar", "kro": "karo",
    "pls": "please", "plz": "please", "plss": "please",
    "u": "you", "ur": "your", "r": "are", "y": "why", "b4": "before",
    "bht": "bahut", "bhot": "bahut", "bohot": "bahut", "bahot": "bahut",
    "mujhe": "mujhe", "muje": "mujhe", "mjhe": "mujhe",
    "yaar": "yaar", "yr": "yaar",
    "sr": "senior", "srs": "seniors", "senoirs": "seniors",
    "hostal": "hostel", "hostl": "hostel",
    "raat": "raat", "rat": "raat", "ratri": "raat",
    "kal": "kal", "kaal": "kal",
    "aaj": "aaj", "aj": "aaj",
    "thik": "theek", "thk": "theek", "theek": "theek",
    "nako": "nako", "naahi": "nahi",
    # transliterated Devanagari forms (translit.py) -> the romanised spellings the cues know
    "seeniyar": "senior", "siniyar": "senior", "seniyar": "senior", "siniyars": "seniors", "seeniyars": "seniors", "seniyars": "seniors",
    "veediyo": "video", "vidiyo": "video", "photo": "photo", "photon": "photo",
    "bheetee": "bhiti", "bheeti": "bhiti", "bhitee": "bhiti", "khoop": "khup", "khup": "khup",
    "rupaye": "rupees", "rupaiye": "rupees", "rupaya": "rupees", "rupye": "rupees",
    "men": "me", "mein": "me", "raatri": "raat", "ratri": "raat",
}
_WORD_FINAL_AA = re.compile(r"aa")

_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF⭐⭕️]+"
)
_REPEAT_RE = re.compile(r"(.)\1{2,}")           # sooooo -> soo
_PUNCT_RUN_RE = re.compile(r"([!?.,])\1+")     # !!! -> !
_MULTI_SPACE_RE = re.compile(r"\s+")
_DIGIT_RE = re.compile(r"\d+")


def normalize(text: str) -> str:
    """Return a normalised version of *text* for classification/extraction."""
    t = transliterate(text)                      # Devanagari -> roman, so one set of cues covers both scripts
    t = unicodedata.normalize("NFKC", t)
    t = _EMOJI_RE.sub(" ", t)
    t = t.lower()
    t = _WORD_FINAL_AA.sub("a", t)               # rakhaa -> rakha, malaa -> mala
    t = _REPEAT_RE.sub(r"\1\1", t)
    t = _PUNCT_RUN_RE.sub(r"\1", t)
    t = _DIGIT_RE.sub(" <num> ", t)
    tokens = re.findall(r"<num>|[a-zऀ-ॿ]+|[!?.,]", t)
    tokens = [SPELLING_VARIANTS.get(tok, tok) for tok in tokens]
    return _MULTI_SPACE_RE.sub(" ", " ".join(tokens)).strip()


if __name__ == "__main__":  # tiny self-check
    print(normalize("Wow such a WARM welcome from srs 😂😂 3 ghante khade rakha... nhi bola kisi ko!!!"))
