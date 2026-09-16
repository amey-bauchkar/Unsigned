"""train_c1_local.py — Fine-tune MurIL/HingRoBERTa locally on CPU.

Usage:
    python scripts/train_c1_local.py --corpus data/corpus.csv
    python scripts/train_c1_local.py --corpus data/corpus.csv --model l3cube-pune/hing-roberta --epochs 4
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from unsigned.pipeline.card import DISTRESS, URGENCY, TYPES  # noqa: E402


def split_types(s) -> list[str]:
    if isinstance(s, float) or s is None or str(s).strip() == "":
        return ["none"]
    return [t.strip() for t in str(s).split(";") if t.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(description="Train C1 transformer classifier locally")
    ap.add_argument("--corpus", default=os.path.join(ROOT, "data", "corpus.csv"))
    ap.add_argument("--model", default="google/muril-base-cased",
                     help="HuggingFace encoder (default: google/muril-base-cased)")
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--batch-size", type=int, default=8, help="Batch size (8 for CPU)")
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--max-len", type=int, default=128)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--out", default=os.path.join(ROOT, "models", "c1_onnx"))
    args = ap.parse_args()

    try:
        import torch
        import torch.nn as nn
        from torch.optim import AdamW
        from torch.optim.lr_scheduler import OneCycleLR
        from sklearn.metrics import f1_score
        from sklearn.model_selection import GroupKFold
        from transformers import AutoModel, AutoTokenizer
    except ImportError as e:
        sys.exit(f"Missing dependency: {e}. Run: pip install transformers torch")

    # ---- Load data --------------------------------------------------------
    df = pd.read_csv(args.corpus)
    df["text"] = df["text"].astype(str)
    texts = df["text"].tolist()
    n = len(texts)

    # Encode labels
    dist_map = {d: i for i, d in enumerate(DISTRESS)}
    urg_map = {u: i for i, u in enumerate(URGENCY)}
    y_d = df["distress"].astype(str).map(dist_map).fillna(0).astype(int).values
    y_u = df["urgency"].astype(str).map(urg_map).fillna(0).astype(int).values
    y_s = df["sarcasm"].astype(int).values
    y_t = np.array([[1.0 if t in split_types(s) else 0.0 for t in TYPES]
                     for s in df["types"]], dtype=np.float32)
    groups = df["author"].values

    print(f"\n{'='*60}")
    print(f"  Unsigned C1 Training — {time.strftime('%Y-%m-%d %H:%M')}")
    print(f"  Corpus: {args.corpus} ({n} samples, {df['author'].nunique()} authors)")
    print(f"  Encoder: {args.model}")
    print(f"  Epochs: {args.epochs}, Batch: {args.batch_size}, LR: {args.lr}")
    print(f"{'='*60}\n")

    # ---- Load tokenizer + encoder ----------------------------------------
    print("Loading tokenizer and encoder (first run downloads ~400MB)...")
    tok = AutoTokenizer.from_pretrained(args.model)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {dev}\n")

    # ---- Model definition ------------------------------------------------
    class MultiHeadClassifier(nn.Module):
        def __init__(self, encoder):
            super().__init__()
            self.encoder = encoder
            h = encoder.config.hidden_size
            self.dropout = nn.Dropout(0.1)
            self.distress_head = nn.Linear(h, 3)
            self.urgency_head = nn.Linear(h, 3)
            self.sarcasm_head = nn.Linear(h, 2)
            self.types_head = nn.Linear(h, len(TYPES))

        def forward(self, input_ids, attention_mask):
            out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
            cls = self.dropout(out.last_hidden_state[:, 0])
            return (self.distress_head(cls), self.urgency_head(cls),
                    self.sarcasm_head(cls), self.types_head(cls))

    # ---- Training function -----------------------------------------------
    def train_fold(tr_idx, te_idx, fold_num):
        encoder = AutoModel.from_pretrained(args.model)
        model = MultiHeadClassifier(encoder).to(dev)
        ce = nn.CrossEntropyLoss()
        bce = nn.BCEWithLogitsLoss()

        n_batches = (len(tr_idx) + args.batch_size - 1) // args.batch_size
        total_steps = n_batches * args.epochs
        opt = AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
        sched = OneCycleLR(opt, max_lr=args.lr, total_steps=total_steps,
                           pct_start=0.1, anneal_strategy='linear')

        for epoch in range(args.epochs):
            model.train()
            np.random.shuffle(tr_idx)
            epoch_loss = 0.0
            n_batches_done = 0
            t0 = time.perf_counter()

            for i in range(0, len(tr_idx), args.batch_size):
                idx = tr_idx[i:i + args.batch_size]
                batch_texts = [texts[j] for j in idx]
                enc = tok(batch_texts, padding=True, truncation=True,
                         max_length=args.max_len, return_tensors="pt").to(dev)

                d, u, s, t = model(enc["input_ids"], enc["attention_mask"])
                loss = (ce(d, torch.tensor(y_d[idx]).to(dev)) +
                        ce(u, torch.tensor(y_u[idx]).to(dev)) +
                        ce(s, torch.tensor(y_s[idx]).to(dev)) +
                        bce(t, torch.tensor(y_t[idx]).to(dev)))

                opt.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
                sched.step()

                epoch_loss += loss.item()
                n_batches_done += 1

                if n_batches_done % 20 == 0:
                    elapsed = time.perf_counter() - t0
                    print(f"    Fold {fold_num} Epoch {epoch+1}/{args.epochs} "
                          f"Batch {n_batches_done}/{n_batches} "
                          f"Loss={epoch_loss/n_batches_done:.4f} "
                          f"Time={elapsed:.0f}s")

            elapsed = time.perf_counter() - t0
            print(f"  Fold {fold_num} Epoch {epoch+1}/{args.epochs} done - "
                  f"avg loss={epoch_loss/max(n_batches_done,1):.4f} ({elapsed:.0f}s)")

        # ---- Evaluate on test fold -------------------------------------------
        model.eval()
        pd_, pu_, ps_ = [], [], []
        with torch.no_grad():
            for i in range(0, len(te_idx), args.batch_size * 2):
                idx = te_idx[i:i + args.batch_size * 2]
                batch_texts = [texts[j] for j in idx]
                enc = tok(batch_texts, padding=True, truncation=True,
                         max_length=args.max_len, return_tensors="pt").to(dev)
                d, u, s, t = model(enc["input_ids"], enc["attention_mask"])
                pd_.extend(d.argmax(1).cpu().numpy().tolist())
                pu_.extend(u.argmax(1).cpu().numpy().tolist())
                ps_.extend(s.argmax(1).cpu().numpy().tolist())

        return model, np.array(pd_), np.array(pu_), np.array(ps_)

    # ---- Grouped K-Fold CV -----------------------------------------------
    n_folds = min(args.folds, df["author"].nunique())
    gkf = GroupKFold(n_splits=n_folds)
    all_pd = np.zeros(n, dtype=int)
    all_pu = np.zeros(n, dtype=int)
    all_ps = np.zeros(n, dtype=int)

    print(f"Starting {n_folds}-fold grouped cross-validation...\n")
    t_start = time.perf_counter()

    for fold, (tr, te) in enumerate(gkf.split(texts, groups=groups), 1):
        tr_list, te_list = list(tr), list(te)
        print(f"\n--- Fold {fold}/{n_folds} (train={len(tr_list)}, test={len(te_list)}) ---")
        _, pd_, pu_, ps_ = train_fold(tr_list, te_list, fold)
        for j, idx in enumerate(te_list):
            all_pd[idx] = pd_[j]
            all_pu[idx] = pu_[j]
            all_ps[idx] = ps_[j]

        # Per-fold metrics
        te_yd = y_d[te_list]
        te_yu = y_u[te_list]
        te_ys = y_s[te_list]
        f1_d = f1_score(te_yd, pd_, average="macro")
        f1_u = f1_score(te_yu, pu_, average="macro")
        f1_s = f1_score(te_ys, ps_, average="macro") if len(set(te_ys)) > 1 else 0.0
        print(f"  Fold {fold} -> distress F1={f1_d:.3f}  urgency F1={f1_u:.3f}  sarcasm F1={f1_s:.3f}")

    # ---- Overall metrics -------------------------------------------------
    cv_time = time.perf_counter() - t_start
    metrics = {
        "model": args.model,
        "corpus": os.path.basename(args.corpus),
        "n_samples": n,
        "n_authors": int(df["author"].nunique()),
        "epochs": args.epochs,
        "cv_folds": n_folds,
        "distress_f1": float(f1_score(y_d, all_pd, average="macro")),
        "urgency_f1": float(f1_score(y_u, all_pu, average="macro")),
        "sarcasm_f1": float(f1_score(y_s, all_ps, average="macro")) if len(set(y_s)) > 1 else 0.0,
    }

    # Sarcastic subset
    sarc_mask = y_s == 1
    if sarc_mask.sum() >= 3:
        metrics["distress_sarcastic_f1"] = float(
            f1_score(y_d[sarc_mask], all_pd[sarc_mask], average="macro"))

    # Mundane false-alert rate
    mund = df["mundane"].astype(int).values == 1
    if mund.sum() >= 1:
        metrics["mundane_false_alert"] = float(np.mean(all_pd[mund] != 0))

    print(f"\n{'='*60}")
    print(f"  CROSS-VALIDATION RESULTS ({cv_time:.0f}s total)")
    print(f"{'='*60}")
    for k, v in metrics.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}")
        else:
            print(f"  {k}: {v}")
    print()

    # ---- Train final model on ALL data -----------------------------------
    print("Training final model on ALL data...")
    t_final = time.perf_counter()
    all_idx = list(range(n))
    final_model, _, _, _ = train_fold(all_idx, [], 0)
    print(f"Final model trained in {time.perf_counter() - t_final:.0f}s\n")

    # ---- Export to ONNX --------------------------------------------------
    print("Exporting to ONNX...")
    os.makedirs(args.out, exist_ok=True)

    final_model.eval()
    final_model.to("cpu")
    dummy = tok("test sentence", return_tensors="pt", padding=True,
                truncation=True, max_length=args.max_len)

    class OnnxWrapper(nn.Module):
        """Wrapper that returns named outputs for ONNX."""
        def __init__(self, model):
            super().__init__()
            self.model = model

        def forward(self, input_ids, attention_mask):
            d, u, s, t = self.model(input_ids, attention_mask)
            return d, u, s, t

    wrapper = OnnxWrapper(final_model)
    wrapper.eval()

    try:
        torch.onnx.export(
            wrapper,
            (dummy["input_ids"], dummy["attention_mask"]),
            os.path.join(args.out, "model.onnx"),
            input_names=["input_ids", "attention_mask"],
            output_names=["distress_logits", "urgency_logits",
                          "sarcasm_logits", "types_logits"],
            dynamic_axes={
                "input_ids": {0: "batch", 1: "seq"},
                "attention_mask": {0: "batch", 1: "seq"},
                "distress_logits": {0: "batch"},
                "urgency_logits": {0: "batch"},
                "sarcasm_logits": {0: "batch"},
                "types_logits": {0: "batch"},
            },
            opset_version=14,
            do_constant_folding=True,
        )
        print(f"  ONNX model saved to {args.out}/model.onnx")
    except Exception as e:
        print(f"  ONNX export failed: {e}")
        print("  Saving PyTorch model instead...")
        torch.save(final_model.state_dict(), os.path.join(args.out, "model.pt"))
        # Save encoder config for fallback loading
        final_model.encoder.config.save_pretrained(args.out)
        print(f"  PyTorch model saved to {args.out}/model.pt")

    # Save tokenizer
    tok.save_pretrained(args.out)
    print(f"  Tokenizer saved to {args.out}/")

    # Save head dimensions for inference
    head_config = {
        "distress_labels": DISTRESS,
        "urgency_labels": URGENCY,
        "types_labels": TYPES,
        "hidden_size": final_model.encoder.config.hidden_size,
        "model_name": args.model,
    }
    with open(os.path.join(args.out, "head_config.json"), "w") as f:
        json.dump(head_config, f, indent=2)

    # Save metrics
    metrics_path = os.path.join(ROOT, "models", "c1_metrics.json")
    os.makedirs(os.path.dirname(metrics_path), exist_ok=True)
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    print(f"  Metrics saved to {metrics_path}")

    print(f"\n{'='*60}")
    print(f"  DONE! Model ready at: {args.out}")
    print(f"  Place classify_c1.py in unsigned/pipeline/ to enable C1.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
