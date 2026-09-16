"""Devanagari → roman transliteration, so Hindi/Marathi written in native script reaches the same
cue lexicons as romanised Hinglish. Deliberately simple and dependency-free: a phonetic mapping
with word-final schwa deletion, which is what turns रात into "raat" rather than "raata".

It runs on the raw text before every other step, so cues, number banding and the classifier all
see one script. It is a pre-processor, not a privacy mechanism.
"""
from __future__ import annotations

import re

_VOWELS = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri", "ए": "e", "ऐ": "ai",
    "ओ": "o", "औ": "au", "ऑ": "o", "ऍ": "e", "ऎ": "e", "ऒ": "o",
}
_MATRAS = {
    "ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
    "ॉ": "o", "ॅ": "e", "ॆ": "e", "ॊ": "o",
}
_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh",
    "ष": "sh", "स": "s", "ह": "h", "ळ": "l", "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "d", "ढ़": "dh", "फ़": "f", "य़": "y",
}
_DIGITS = {chr(0x0966 + i): str(i) for i in range(10)}
_VIRAMA, _NUKTA, _ANUSVARA, _CHANDRABINDU, _VISARGA = "्", "़", "ं", "ँ", "ः"
_DEV = re.compile(r"[ऀ-ॿ]")


def has_devanagari(text: str) -> bool:
    return bool(_DEV.search(text))


def _is_cons(ch: str) -> bool:
    return ch in _CONSONANTS


def transliterate(text: str) -> str:
    """Replace every Devanagari run with its phonetic roman form; leave everything else untouched.

    Schwa deletion follows the usual Hindi rule: a consonant's inherent 'a' is dropped word-finally, and
    in the middle of a word when an earlier vowel exists and the next consonant carries its own vowel
    sign (धमकी -> dhamki, सामने -> saamne), while रखा stays rakha and थप्पड़ stays thappad."""
    if not has_devanagari(text):
        return text
    out = []
    i, n = 0, len(text)
    had_vowel = False                       # within the current Devanagari word
    while i < n:
        ch = text[i]
        if not _DEV.match(ch):
            had_vowel = False
        if _is_cons(ch):
            base, i = _CONSONANTS[ch], i + 1
            if i < n and text[i] == _NUKTA:
                i += 1
            nxt = text[i] if i < n else ""
            if nxt in _MATRAS:
                out.append(base + _MATRAS[nxt]); i += 1; had_vowel = True
            elif nxt == _VIRAMA:
                out.append(base); i += 1
            elif nxt in (_ANUSVARA, _CHANDRABINDU):
                out.append(base + "a"); had_vowel = True
            else:
                # inherent 'a': keep unless (a) word ends here, or (b) medial schwa before a consonant that carries a vowel sign
                after_next = text[i + 1] if i + 1 < n else ""          # i already points at nxt
                if after_next == _NUKTA:
                    after_next = text[i + 2] if i + 2 < n else ""
                word_ends = (not nxt) or not _DEV.match(nxt)
                medial_drop = had_vowel and _is_cons(nxt) and (after_next in _MATRAS)
                if word_ends or medial_drop:
                    out.append(base)
                else:
                    out.append(base + "a"); had_vowel = True
            continue
        if ch in _VOWELS:
            out.append(_VOWELS[ch]); i += 1; had_vowel = True; continue
        if ch in _MATRAS:
            out.append(_MATRAS[ch]); i += 1; had_vowel = True; continue
        if ch in (_ANUSVARA, _CHANDRABINDU):
            out.append("n"); i += 1; continue
        if ch == _VISARGA:
            out.append("h"); i += 1; continue
        if ch in (_VIRAMA, _NUKTA, "‌", "‍"):
            i += 1; continue
        if ch in _DIGITS:
            out.append(_DIGITS[ch]); i += 1; continue
        if ch == "।":
            out.append("."); i += 1; continue
        out.append(ch); i += 1
    return re.sub(r"ee\b", "i", "".join(out))    # धमकी -> dhamki, भी -> bhi (word-final ī is written i in Hinglish)


if __name__ == "__main__":
    for s in ["सीनियर ने हॉस्टल में रात को ३ घंटे खड़े रखा और ५०० रुपये मांगे, वीडियो भी बनाया",
              "सिनियर्स नी मला उभं केलं आणि पैसे मागितले, खूप भीती वाटते",
              "mixed: seniors ne पैसे maange"]:
        print(transliterate(s))
