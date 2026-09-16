"""seed_demo.py — populate the database with a SIX-WEEK replayed history for the demo.

Runs the real pipeline over corpus texts (dev seed by default), back-dating each card
to a simulated week so the Patterns tab has history and k-anonymity groups exist.
The texts are discarded exactly as in production; only cards are stored.

Usage:  python scripts/seed_demo.py [--corpus data/dev_seed.csv] [--db unsigned.sqlite]
Label the replay as SIMULATED TIMELINE on any slide.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("UNSIGNED_DB", os.path.join(ROOT, "unsigned.sqlite"))

from unsigned.api import app as api                       # noqa: E402
from unsigned.pipeline.classify import BaselineClassifier  # noqa: E402
from unsigned.pipeline.run import process                 # noqa: E402
from unsigned.privacy.attacker import StyleAttacker       # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=os.path.join(ROOT, "data", "dev_seed.csv"))
    ap.add_argument("--db", default=os.environ["UNSIGNED_DB"])
    ap.add_argument("--weeks", type=int, default=6)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    api.DB_PATH = args.db
    api.init_db()
    rng = random.Random(args.seed)

    clf = BaselineClassifier.load(os.path.join(ROOT, "models", "c0.joblib"))
    att = StyleAttacker.load(os.path.join(ROOT, "models", "a1.joblib"))
    df = pd.read_csv(args.corpus)
    now = time.time()
    this_week = int(now // (7 * 86400))

    # Story: quiet background for weeks 1-4, then a rising Hostel-B/night pattern in the last two weeks.
    texts = df["text"].tolist()
    rows = []
    for t in texts:
        w = rng.choice(range(this_week - args.weeks + 1, this_week - 1))       # background weeks
        rows.append((t, w))
    surge = [t for t in texts if "hostel b" in t.lower() or "hostel B" in t]
    for t in surge * 2:                                                          # mostly this week, a little last week
        rows.append((t, this_week if rng.random() < 0.8 else this_week - 1))

    statuses = ["resolved"] * 5 + ["in_progress"] * 2 + ["received"] * 3
    with api._db() as con:
        released = list(api._released_fine(con).values())
        for text, week in rows:
            r = process(text, clf, att, released, api.K)
            card = r["card"]
            released.append(card)
            ts = (week * 7 + rng.randint(0, 6)) * 86400 + rng.randint(0, 86399)
            st = rng.choice(statuses) if week < this_week else "received"
            cur = con.execute(
                "INSERT INTO cards(card_json,urgency,distress,release_at,released,day_bucket,week,k_satisfied,token_hash,status,resolved_at) "
                "VALUES (?,?,?,?,1,?,?,?,?,?,?)",
                (json.dumps(card.to_dict()), card.urgency, card.distress, ts,
                 time.strftime("%Y-%m-%d", time.gmtime(ts)), week, int(r["k_satisfied"]), api._hash(os.urandom(8).hex()),
                 st, ts + rng.randint(1, 6) * 86400 if st == "resolved" else None),
            )
            con.execute("INSERT INTO audits(card_id,audit_json,raw_discarded_after_ms) VALUES (?,?,?)",
                        (cur.lastrowid, json.dumps(r["audit"]), r["raw_discarded_after_ms"]))
    print(f"seeded {len(rows)} cards over {args.weeks} weeks into {args.db} (SIMULATED TIMELINE)")


if __name__ == "__main__":
    main()
