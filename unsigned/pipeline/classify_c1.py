"""C1 — ONNX inference wrapper for the fine-tuned encoder.

Drop-in replacement for BaselineClassifier. Same .predict() contract.
Auto-detected by load_classifier() in classify.py when models/c1_onnx/ exists.

Requires: pip install onnxruntime transformers
"""
from __future__ import annotations

import json
import os
from typing import Dict, List

import numpy as np

from .card import DISTRESS, URGENCY, TYPES


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - np.max(x, axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


class OnnxClassifier:
    """C1 — fine-tuned MurIL/HingRoBERTa with 4 heads, exported to ONNX.

    Same .predict(text) interface as BaselineClassifier so the rest of the
    pipeline (rules, facts, audit) works unchanged.
    """

    def __init__(self, model_dir: str = "models/c1_onnx"):
        import onnxruntime as ort
        from transformers import AutoTokenizer

        onnx_path = os.path.join(model_dir, "model.onnx")
        if not os.path.exists(onnx_path):
            raise FileNotFoundError(f"No ONNX model at {onnx_path}")

        self.session = ort.InferenceSession(
            onnx_path,
            providers=["CPUExecutionProvider"],
        )
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        self.max_len = 128

        # Load head config if available
        config_path = os.path.join(model_dir, "head_config.json")
        if os.path.exists(config_path):
            with open(config_path) as f:
                self.config = json.load(f)
        else:
            self.config = {
                "distress_labels": DISTRESS,
                "urgency_labels": URGENCY,
                "types_labels": TYPES,
            }

        self.fitted = True  # compatibility with BaselineClassifier

    def predict(self, text: str, type_threshold: float = 0.5) -> dict:
        """Return dict matching BaselineClassifier.predict() contract."""
        enc = self.tokenizer(
            text, padding=True, truncation=True,
            max_length=self.max_len, return_tensors="np",
        )

        outputs = self.session.run(
            ["distress_logits", "urgency_logits", "sarcasm_logits", "types_logits"],
            {
                "input_ids": enc["input_ids"].astype(np.int64),
                "attention_mask": enc["attention_mask"].astype(np.int64),
            },
        )

        d_logits, u_logits, s_logits, t_logits = outputs

        # Distress
        d_proba = _softmax(d_logits[0])
        d_idx = int(np.argmax(d_proba))
        distress = DISTRESS[d_idx]

        # Urgency
        u_proba = _softmax(u_logits[0])
        u_idx = int(np.argmax(u_proba))
        urgency = URGENCY[u_idx]

        # Sarcasm
        s_proba = _softmax(s_logits[0])
        s_idx = int(np.argmax(s_proba))
        sarcasm = str(s_idx)

        # Types (multi-label)
        t_proba = _sigmoid(t_logits[0])
        types_conf: Dict[str, float] = {}
        types_list: List[str] = []
        for i, tname in enumerate(TYPES):
            p = float(t_proba[i])
            types_conf[tname] = p
            if p >= type_threshold:
                types_list.append(tname)
        if not types_list or types_list == ["none"]:
            types_list = ["none"]

        return {
            "distress": distress,
            "urgency": urgency,
            "sarcasm": sarcasm,
            "types": sorted(types_list),
            "distress_confidence": float(d_proba[d_idx]),
            "urgency_confidence": float(u_proba[u_idx]),
            "sarcasm_confidence": float(s_proba[s_idx]),
            "types_confidence": types_conf,
            "why": {},  # ONNX doesn't provide feature attribution
        }
