"""A1 — the stylometry attacker. Part of the product, not just the evaluation.

Standard PAN-style authorship attribution: character n-gram TF-IDF + explicit
style features -> logistic regression. Two uses:
  * attribute(text)  -> which known author wrote this, with probability
  * link(text_a, text_b) -> same-author probability (pairwise linkability)

The attacker is trained on the *adversary's* knowledge (known writing samples),
never on anything Unsigned stores. In the demo the judge's earlier sample is
added as a reference author — "as a warden with your assignments would have".
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

import joblib
import numpy as np
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF]")
_FUNCTION_WORDS = [
    "ki", "ke", "ka", "ko", "se", "me", "mein", "par", "pe", "aur", "ya", "to", "toh", "hai", "h", "the", "a",
    "and", "but", "so", "like", "just", "very", "bahut", "bhi", "na", "nahi", "nhi", "yaar", "bhai", "bro",
    "please", "pls", "plz", "sir", "maam", "madam", "ahe", "ani", "mala", "tula", "kay", "nako",
]


def style_features(text: str) -> np.ndarray:
    """Hand-crafted style profile: punctuation, casing, emoji, length, function words."""
    n_chars = max(len(text), 1)
    words = re.findall(r"\w+", text)
    n_words = max(len(words), 1)
    feats = [
        text.count("!") / n_chars, text.count("?") / n_chars, text.count(".") / n_chars,
        text.count(",") / n_chars, text.count("...") / n_chars,
        len(re.findall(r"!{2,}", text)) / n_words, len(re.findall(r"\?{2,}", text)) / n_words,
        sum(c.isupper() for c in text) / n_chars,
        sum(w.isupper() and len(w) > 1 for w in words) / n_words,
        len(_EMOJI_RE.findall(text)) / n_words,
        np.mean([len(w) for w in words]) if words else 0.0,
        n_words, len(re.split(r"[.!?]+", text)),
        len(re.findall(r"(.)\1{2,}", text)) / n_words,             # sooo, !!!
        len(re.findall(r"\b\w{1,2}\b", text)) / n_words,            # abbreviation habit (u, r, h)
        text.count("\n") / n_chars,
    ]
    lowered = text.lower()
    feats += [len(re.findall(rf"\b{re.escape(fw)}\b", lowered)) / n_words for fw in _FUNCTION_WORDS]
    return np.array(feats, dtype=float)


class StyleAttacker:
    def __init__(self) -> None:
        self.char_vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 5), min_df=1, sublinear_tf=True, lowercase=False)
        self.scaler = StandardScaler()
        self.clf = LogisticRegression(max_iter=3000, C=2.0, class_weight="balanced")
        self.authors: List[str] = []
        self.fitted = False

    def _fit_X(self, texts: List[str]):
        S = self.scaler.fit_transform(np.vstack([style_features(t) for t in texts]))
        return hstack([self.char_vec.fit_transform(texts), csr_matrix(S)]).tocsr()

    def _X(self, texts: List[str]):
        S = self.scaler.transform(np.vstack([style_features(t) for t in texts]))
        return hstack([self.char_vec.transform(texts), csr_matrix(S)]).tocsr()

    def fit(self, texts: List[str], authors: List[str]) -> "StyleAttacker":
        X = self._fit_X(texts)
        self.clf.fit(X, authors)
        self.authors = list(self.clf.classes_)
        self.fitted = True
        return self

    def attribute(self, text: str) -> Tuple[str, float, Dict[str, float]]:
        """Best-guess author, its probability, and the full distribution."""
        proba = self.clf.predict_proba(self._X([text]))[0]
        k = int(np.argmax(proba))
        return self.authors[k], float(proba[k]), dict(zip(self.authors, map(float, proba)))

    def link(self, text_a: str, text_b: str) -> float:
        """Same-author probability: agreement of the two attribution distributions."""
        pa = self.clf.predict_proba(self._X([text_a]))[0]
        pb = self.clf.predict_proba(self._X([text_b]))[0]
        return float(np.dot(pa, pb) / (np.linalg.norm(pa) * np.linalg.norm(pb) + 1e-9))

    def chance(self) -> float:
        return 1.0 / max(len(self.authors), 1)

    def save(self, path: str) -> None:
        joblib.dump(self, path)

    @staticmethod
    def load(path: str) -> "StyleAttacker":
        return joblib.load(path)


def leave_one_out_accuracy(texts: List[str], authors: List[str]) -> float:
    """Attribution accuracy@1 with each text held out in turn (authors need >=2 texts)."""
    n = len(texts)
    correct = 0
    for i in range(n):
        tr = [j for j in range(n) if j != i]
        att = StyleAttacker().fit([texts[j] for j in tr], [authors[j] for j in tr])
        guess, _, _ = att.attribute(texts[i])
        correct += int(guess == authors[i])
    return correct / n


def pairwise_linkability_auc(attacker: StyleAttacker, texts: List[str], authors: List[str], max_pairs: int = 4000) -> float:
    """AUC of link() for same-author vs different-author pairs (held-out texts)."""
    from sklearn.metrics import roc_auc_score
    rng = np.random.default_rng(0)
    idx = [(i, j) for i in range(len(texts)) for j in range(i + 1, len(texts))]
    if len(idx) > max_pairs:
        idx = [idx[k] for k in rng.choice(len(idx), max_pairs, replace=False)]
    y = [int(authors[i] == authors[j]) for i, j in idx]
    if len(set(y)) < 2:
        return float("nan")
    s = [attacker.link(texts[i], texts[j]) for i, j in idx]
    return float(roc_auc_score(y, s))
