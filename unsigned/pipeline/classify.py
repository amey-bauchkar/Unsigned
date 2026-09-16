"""C0 — baseline classifier heads (TF-IDF char+word n-grams -> logistic regression).

Always shipped. Runs on any laptop with no GPU. C1 (fine-tuned encoder,
scripts/train_transformer.py) must beat this on grouped cross-validation to be
switched on; classify() falls back to C0 when no C1 model is present.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

import joblib
import numpy as np
import pandas as pd
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import MultiLabelBinarizer

from .card import DISTRESS, URGENCY, TYPES
from .normalize import normalize

HEADS = ["distress", "urgency", "sarcasm"]     # single-label heads
MULTI_HEAD = "types"                           # multi-label head


class BaselineClassifier:
    def __init__(self) -> None:
        self.char_vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=1, sublinear_tf=True)
        self.word_vec = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=1, sublinear_tf=True)
        self.models: Dict[str, LogisticRegression] = {}
        self.type_models: Dict[str, LogisticRegression] = {}
        self.mlb = MultiLabelBinarizer(classes=TYPES)
        self.fitted = False

    # ---- features ---------------------------------------------------------
    def _fit_features(self, texts: List[str]):
        norm = [normalize(t) for t in texts]
        return hstack([self.char_vec.fit_transform(norm), self.word_vec.fit_transform(norm)]).tocsr()

    def _features(self, texts: List[str]):
        norm = [normalize(t) for t in texts]
        return hstack([self.char_vec.transform(norm), self.word_vec.transform(norm)]).tocsr()

    # ---- training ---------------------------------------------------------
    def fit(self, df: pd.DataFrame) -> "BaselineClassifier":
        """df columns: text, distress, urgency, sarcasm, types (semicolon-separated)."""
        X = self._fit_features(df["text"].tolist())
        for head in HEADS:
            y = df[head].astype(str).tolist()
            if len(set(y)) < 2:  # degenerate head in tiny dev data
                continue
            self.models[head] = LogisticRegression(max_iter=2000, C=4.0, class_weight="balanced").fit(X, y)
        Y = self.mlb.fit_transform([_split_types(s) for s in df[MULTI_HEAD]])
        for j, cls in enumerate(TYPES):
            col = Y[:, j]
            if col.sum() == 0 or col.sum() == len(col):
                continue
            self.type_models[cls] = LogisticRegression(max_iter=2000, C=4.0, class_weight="balanced").fit(X, col)
        self.fitted = True
        return self

    # ---- inference --------------------------------------------------------
    def predict(self, text: str, type_threshold: float = 0.5) -> dict:
        X = self._features([text])
        out: dict = {"why": {}}
        for head in HEADS:
            m = self.models.get(head)
            if m is None:
                out[head] = {"distress": "none", "urgency": "routine", "sarcasm": "0"}[head]
                continue
            proba = m.predict_proba(X)[0]
            k = int(np.argmax(proba))
            out[head] = str(m.classes_[k])
            out[f"{head}_confidence"] = float(proba[k])
            out["why"][head] = self._top_features(m, X, k)
        types, tconf = [], {}
        for cls, m in self.type_models.items():
            p = float(m.predict_proba(X)[0][1])
            tconf[cls] = p
            if p >= type_threshold:
                types.append(cls)
        out[MULTI_HEAD] = sorted(types) or ["none"]
        out["types_confidence"] = tconf
        return out

    def _top_features(self, model: LogisticRegression, X, k: int, n: int = 5) -> List[str]:
        names = np.concatenate([self.char_vec.get_feature_names_out(), self.word_vec.get_feature_names_out()])
        coef = model.coef_[k] if model.coef_.shape[0] > 1 else model.coef_[0] * (1 if k == 1 else -1)
        contrib = X.toarray()[0] * coef
        idx = np.argsort(contrib)[::-1][:n * 3]
        return [str(names[i]).strip() for i in idx if contrib[i] > 0 and len(str(names[i]).strip()) >= 3]

    # ---- persistence ------------------------------------------------------
    def save(self, path: str) -> None:
        joblib.dump(self, path)

    @staticmethod
    def load(path: str) -> "BaselineClassifier":
        return joblib.load(path)


def _split_types(s) -> List[str]:
    if isinstance(s, float) or s is None or str(s).strip() == "":
        return ["none"]
    return [t.strip() for t in str(s).split(";") if t.strip()]


def load_classifier(model_dir: str = "models") -> BaselineClassifier:
    """Prefer C1 (ONNX, exported by scripts/train_transformer.py) when present; else C0."""
    c1 = os.path.join(model_dir, "c1_onnx")
    if os.path.isdir(c1):
        try:
            from .classify_c1 import OnnxClassifier  # type: ignore  # provided once C1 is trained
            return OnnxClassifier(c1)                 # same .predict() contract
        except Exception:
            pass
    c0 = os.path.join(model_dir, "c0.joblib")
    if os.path.exists(c0):
        return BaselineClassifier.load(c0)
    raise FileNotFoundError("No trained classifier. Run scripts/evaluate.py --train first.")
