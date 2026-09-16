"""C1 — fine-tune a code-mixed encoder with four heads (distress, urgency, sarcasm, types).

Optional. Requires:  pip install transformers datasets onnx onnxruntime
Run on a free Colab GPU (~20-40 min) or CPU overnight. Grouped CV by author, exactly as C0,
so the ablation is fair. C1 is switched on ONLY if it beats C0's macro-F1 on distress.

    python scripts/train_transformer.py --corpus data/corpus.csv --model l3cube-pune/hing-roberta
    python scripts/train_transformer.py --corpus data/corpus.csv --model google/muril-base-cased

Outputs models/c1/ (HF format) and models/c1_metrics.json. ONNX export is a TODO once C1 wins.
Candidate encoders (VERIFY availability/licence): l3cube-pune/hing-roberta, l3cube-pune/hing-bert,
google/muril-base-cased, ai4bharat/IndicBERTv2-MLM-only, l3cube-pune/marathi-roberta (Marathi-English).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from unsigned.pipeline.card import DISTRESS, URGENCY, TYPES  # noqa: E402
from unsigned.pipeline.classify import _split_types           # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--model", default="l3cube-pune/hing-roberta")
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--out", default=os.path.join(ROOT, "models", "c1"))
    args = ap.parse_args()

    try:
        import torch
        from sklearn.metrics import f1_score
        from sklearn.model_selection import GroupKFold
        from transformers import AutoModel, AutoTokenizer
    except ImportError as e:
        sys.exit(f"missing dependency: {e}. pip install transformers")

    df = pd.read_csv(args.corpus)
    texts = df["text"].astype(str).tolist()
    y_d = df["distress"].astype(str).map({str(i): i for i in range(3)}).fillna(0).astype(int).values
    y_u = df["urgency"].map({u: i for i, u in enumerate(URGENCY)}).fillna(0).astype(int).values
    y_s = df["sarcasm"].astype(int).values
    y_t = np.array([[1 if t in _split_types(s) else 0 for t in TYPES] for s in df["types"]], dtype=np.float32)
    groups = df["author"].values

    tok = AutoTokenizer.from_pretrained(args.model)
    dev = "cuda" if torch.cuda.is_available() else "cpu"

    class Heads(torch.nn.Module):
        def __init__(self, enc):
            super().__init__()
            self.enc = enc
            h = enc.config.hidden_size
            self.d = torch.nn.Linear(h, 3); self.u = torch.nn.Linear(h, 3)
            self.s = torch.nn.Linear(h, 2); self.t = torch.nn.Linear(h, len(TYPES))

        def forward(self, **kw):
            x = self.enc(**kw).last_hidden_state[:, 0]
            return self.d(x), self.u(x), self.s(x), self.t(x)

    def run_fold(tr, te):
        model = Heads(AutoModel.from_pretrained(args.model)).to(dev)
        opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
        ce, bce = torch.nn.CrossEntropyLoss(), torch.nn.BCEWithLogitsLoss()
        for _ in range(args.epochs):
            model.train()
            for i in range(0, len(tr), 16):
                idx = tr[i:i + 16]
                b = tok([texts[j] for j in idx], padding=True, truncation=True, max_length=128, return_tensors="pt").to(dev)
                d, u, s, t = model(**b)
                loss = (ce(d, torch.tensor(y_d[idx]).to(dev)) + ce(u, torch.tensor(y_u[idx]).to(dev))
                        + ce(s, torch.tensor(y_s[idx]).to(dev)) + bce(t, torch.tensor(y_t[idx]).to(dev)))
                opt.zero_grad(); loss.backward(); opt.step()
        model.eval(); preds = []
        with torch.no_grad():
            for i in range(0, len(te), 32):
                idx = te[i:i + 32]
                b = tok([texts[j] for j in idx], padding=True, truncation=True, max_length=128, return_tensors="pt").to(dev)
                d, u, s, t = model(**b)
                preds += list(zip(d.argmax(1).cpu().numpy(), u.argmax(1).cpu().numpy(), s.argmax(1).cpu().numpy()))
        return model, preds

    gkf = GroupKFold(n_splits=min(args.folds, len(set(groups))))
    pd_, pu_, ps_ = np.zeros(len(df), int), np.zeros(len(df), int), np.zeros(len(df), int)
    for tr, te in gkf.split(texts, groups=groups):
        _, preds = run_fold(list(tr), list(te))
        for j, (d, u, s) in zip(te, preds):
            pd_[j], pu_[j], ps_[j] = d, u, s
    metrics = {
        "model": args.model,
        "distress": float(f1_score(y_d, pd_, average="macro")),
        "urgency": float(f1_score(y_u, pu_, average="macro")),
        "sarcasm": float(f1_score(y_s, ps_, average="macro")),
    }
    sarc = y_s == 1
    if sarc.sum() >= 3:
        metrics["distress_sarcastic"] = float(f1_score(y_d[sarc], pd_[sarc], average="macro"))
    print(json.dumps(metrics, indent=2))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(metrics, open(os.path.join(ROOT, "models", "c1_metrics.json"), "w"), indent=2)

    # final model on all data (for deployment once it beats C0)
    model, _ = run_fold(list(range(len(df))), [])
    model.enc.save_pretrained(args.out); tok.save_pretrained(args.out)
    torch.save({k: v for k, v in model.state_dict().items() if not k.startswith("enc.")}, os.path.join(args.out, "heads.pt"))
    print(f"saved {args.out}. Compare models/c1_metrics.json with C0 in models/evaluation.json before enabling.")


if __name__ == "__main__":
    main()
