"""import_corpus.py — turn the Google Form export (one row per writer, five text columns) into the
long-format corpus the pipeline expects, with author codes and empty label columns ready for annotation.

    python scripts/import_corpus.py form_export.csv data/corpus_unlabelled.csv
    # annotate distress/urgency/types/sarcasm/mundane (see data/annotation_guide.md), save as data/corpus.csv
    python scripts/evaluate.py --corpus data/corpus.csv --train

Text columns are detected automatically (any column whose header starts with "Text" or contains
"complaint"); the author code column is the one containing "code" (falls back to row order: A01, A02, ...).
Nothing here reads or stores anything beyond the CSV you give it.
"""
from __future__ import annotations

import csv
import sys

COLUMNS = ["author", "text", "distress", "urgency", "types", "sarcasm", "mundane", "location_span", "time_span", "actor_span"]


def main(src: str, dst: str) -> None:
    with open(src, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit("no rows in the export")
    headers = list(rows[0].keys())
    text_cols = [h for h in headers if h.strip().lower().startswith("text") or "complaint" in h.lower()]
    code_col = next((h for h in headers if "code" in h.lower()), None)
    if not text_cols:
        sys.exit(f"could not find text columns in {headers}")
    out, n_authors = [], 0
    for i, r in enumerate(rows, 1):
        code = (r.get(code_col) or "").strip() if code_col else ""
        code = code or f"A{i:02d}"
        wrote = 0
        for h in text_cols:
            t = (r.get(h) or "").strip()
            if len(t) >= 5:
                out.append({"author": code, "text": t, "distress": "", "urgency": "", "types": "", "sarcasm": "", "mundane": "",
                            "location_span": "", "time_span": "", "actor_span": ""})
                wrote += 1
        n_authors += bool(wrote)
    with open(dst, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader(); w.writerows(out)
    per = {}
    for o in out:
        per[o["author"]] = per.get(o["author"], 0) + 1
    thin = [a for a, n in per.items() if n < 3]
    print(f"{len(out)} texts from {n_authors} writers -> {dst}")
    if thin:
        print(f"note: {len(thin)} writer(s) have fewer than 3 texts (the attacker needs >= 3 per author to be fair): {', '.join(thin)}")
    print("next: label the empty columns (data/annotation_guide.md), save as data/corpus.csv, then evaluate.py --corpus data/corpus.csv --train")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
