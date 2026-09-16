"""evaluate.py — every number that goes on a slide, printed with the run date.

Usage
  python scripts/evaluate.py --corpus data/dev_seed.csv --train     # trains C0 + A1, writes models/, prints metrics
  python scripts/evaluate.py --corpus data/corpus.csv                # metrics only (models must exist)

Corpus CSV columns: author, text, distress, urgency, types (semicolon list), sarcasm, mundane
Numbers from data/dev_seed.csv are for smoke tests ONLY — never on a slide.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score
from sklearn.model_selection import GroupKFold

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from unsigned.pipeline.card import Card, channel_capacity_bits            # noqa: E402
from unsigned.pipeline.classify import BaselineClassifier, _split_types  # noqa: E402
from unsigned.pipeline.normalize import normalize                        # noqa: E402
from unsigned.pipeline.run import build_card                             # noqa: E402
from unsigned.pipeline.narrate import LEXICON, foreign_tokens, narrative_capacity_bits  # noqa: E402
from unsigned.privacy.attacker import (StyleAttacker, leave_one_out_accuracy,   # noqa: E402
                                       pairwise_linkability_auc)
from unsigned.privacy.kanon import enforce_k                             # noqa: E402


def classifier_cv(df: pd.DataFrame, n_splits: int) -> dict:
    """Grouped CV by author so no author's style leaks across folds."""
    groups = df["author"].values
    gkf = GroupKFold(n_splits=min(n_splits, df["author"].nunique()))
    preds = {h: np.empty(len(df), dtype=object) for h in ["distress", "urgency", "sarcasm"]}
    sys_preds = {h: np.empty(len(df), dtype=object) for h in ["distress", "urgency"]}
    for tr, te in gkf.split(df, groups=groups):
        clf = BaselineClassifier().fit(df.iloc[tr])
        for i in te:
            p = clf.predict(df.iloc[i]["text"])
            for h in preds:
                preds[h][i] = p[h]
            c = build_card(df.iloc[i]["text"], clf)              # classifier + fact graph + rules = what the system does
            sys_preds["distress"][i], sys_preds["urgency"][i] = c.distress, c.urgency

    def score(pr):
        out = {}
        for h in pr:
            y = df[h].astype(str).values
            out[h] = float(f1_score(y, pr[h], average="macro")) if len(set(y)) > 1 else None
        sarc = df["sarcasm"].astype(str) == "1"
        if sarc.sum() >= 3:
            out["distress_sarcastic"] = float(f1_score(df.loc[sarc, "distress"].astype(str), pr["distress"][sarc.values], average="macro"))
        mund = df["mundane"].astype(str) == "1"
        if mund.sum() >= 1:
            out["false_alert_rate"] = float(np.mean(pr["distress"][mund.values] != "none"))
        return out
    out = score(preds)
    out["system"] = score(sys_preds)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=os.path.join(ROOT, "data", "dev_seed.csv"))
    ap.add_argument("--train", action="store_true", help="train C0 and A1 on the full corpus and save to models/")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--folds", type=int, default=5)
    args = ap.parse_args()

    df = pd.read_csv(args.corpus)
    df["text"] = df["text"].astype(str)
    texts, authors = df["text"].tolist(), df["author"].astype(str).tolist()
    is_seed = os.path.basename(args.corpus) == "dev_seed.csv"
    run_date = time.strftime("%Y-%m-%d %H:%M")
    print(f"\nUnsigned evaluate.py — {run_date} — corpus: {args.corpus}")
    if is_seed:
        print("!! DEV SEED (team-written smoke-test data). These numbers must never appear on a slide.")
    print(f"authors={df['author'].nunique()} texts={len(df)} chance={1/df['author'].nunique():.3f}")

    # ---- 1. Attacker strength on raw text ---------------------------------
    acc_raw = leave_one_out_accuracy(texts, authors)
    acc_norm = leave_one_out_accuracy([normalize(t) for t in texts], authors)
    att = StyleAttacker().fit(texts, authors)
    auc_raw = pairwise_linkability_auc(att, texts, authors)
    print(f"\n[A1 attacker]  accuracy@1 raw={acc_raw:.3f}  normalised={acc_norm:.3f}  linkability AUC raw={auc_raw:.3f}")

    # ---- 2. Privacy result: the same attacker on released cards -----------
    clf_full = BaselineClassifier().fit(df)
    released: list[Card] = []
    card_texts = []
    for t in texts:
        c = build_card(t, clf_full)
        c, _ = enforce_k(c, released, args.k)
        released.append(c)
        card_texts.append(c.narrative())
    acc_cards = leave_one_out_accuracy(card_texts, authors)
    auc_cards = pairwise_linkability_auc(att, card_texts, authors)
    n_gen = sum(1 for c in released if c.generalisation_steps)
    violations = sum(len(foreign_tokens(t)) for t in card_texts)
    n_words = sum(len(t.split()) for t in card_texts)
    non_mundane = df[df["mundane"].astype(str) != "1"]
    coverage = float(np.mean([bool(build_card(t, clf_full).facts.get("acts")) for t in non_mundane["text"]])) if len(non_mundane) else float("nan")
    print(f"[privacy]      attacker accuracy@1 on released narratives={acc_cards:.3f} (chance {1/df['author'].nunique():.3f})  "
          f"linkability AUC narratives={auc_cards:.3f}  cards generalised={n_gen}/{len(released)}  k={args.k}")
    print(f"[lexicon]      {n_words} narrative words released, {violations} outside the lexicon (lexicon size {len(LEXICON)})  "
          f"| fact coverage on ragging texts={coverage:.2f}")
    print(f"[channel]      card capacity={channel_capacity_bits():.1f} bits · narrative capacity={narrative_capacity_bits():.1f} bits (upper bounds, none of it style)")

    # ---- 3. Classifier (grouped CV) ----------------------------------------
    c0 = classifier_cv(df, args.folds)
    fmt = lambda v: "—" if v is None else f"{v:.2f}"
    print(f"[C0 classifier] macro-F1 distress={fmt(c0.get('distress'))} urgency={fmt(c0.get('urgency'))} "
          f"sarcasm={fmt(c0.get('sarcasm'))} | distress F1 on sarcastic subset={fmt(c0.get('distress_sarcastic'))} "
          f"| false-alert rate on mundane={fmt(c0.get('false_alert_rate'))}")
    sy = c0["system"]
    print(f"[system]       classifier + facts + rules: distress F1={fmt(sy.get('distress'))} urgency F1={fmt(sy.get('urgency'))} "
          f"| sarcastic-subset distress F1={fmt(sy.get('distress_sarcastic'))} | false-alert rate on mundane={fmt(sy.get('false_alert_rate'))}")

    # ---- 4. Latency -------------------------------------------------------
    t0 = time.perf_counter(); n = 0
    for t in texts[:20]:
        build_card(t, clf_full); n += 1
    lat = (time.perf_counter() - t0) / max(n, 1) * 1000
    print(f"[latency]      build_card ~ {lat:.0f} ms/submission (laptop CPU)")

    result = {
        "run_date": run_date, "corpus": os.path.basename(args.corpus), "dev_seed": is_seed,
        "n_authors": int(df["author"].nunique()), "n_texts": int(len(df)), "chance": 1 / df["author"].nunique(),
        "attacker_acc_raw": acc_raw, "attacker_acc_norm": acc_norm, "attacker_acc_cards": acc_cards,
        "link_auc_raw": auc_raw, "link_auc_cards": auc_cards, "cards_generalised": n_gen, "k": args.k,
        "channel_capacity_bits": channel_capacity_bits(), "narrative_capacity_bits": narrative_capacity_bits(),
        "lexicon_size": len(LEXICON), "lexicon_violations": violations, "narrative_words": n_words, "fact_coverage": coverage,
        "c0": c0, "latency_ms": lat,
    }
    os.makedirs(os.path.join(ROOT, "models"), exist_ok=True)
    ev_path = os.path.join(ROOT, "models", "evaluation.json")
    if os.path.exists(ev_path):                      # keep the fuzz / style-invariance results from their own scripts
        old = json.load(open(ev_path, encoding="utf-8"))
        for k in ("fuzz", "style_invariance", "feedback"):
            if k in old:
                result[k] = old[k]
    with open(ev_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    if args.train:
        clf_full.save(os.path.join(ROOT, "models", "c0.joblib"))
        att.save(os.path.join(ROOT, "models", "a1.joblib"))
        with open(os.path.join(ROOT, "models", "a1_reference.json"), "w", encoding="utf-8") as f:
            json.dump({"texts": texts, "authors": authors}, f, ensure_ascii=False)
        print("\nsaved models/c0.joblib, models/a1.joblib, models/a1_reference.json")
    print("wrote models/evaluation.json\n")


if __name__ == "__main__":
    main()
