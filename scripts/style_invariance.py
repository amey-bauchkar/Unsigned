"""style_invariance.py — the same incident written in seven styles must produce ONE identical account.

This is the property the twist asks for, stated as a test: style is not stripped, it never enters.
Seven renderings per incident: lowercase-and-dots, CAPS+emoji, formal English, Marathi-English,
SMS abbreviations, sarcastic, Devanagari Hindi. For each incident we report whether the extracted
facts are identical across all seven, whether the full account (which also carries the classifier's
distress/urgency line) is identical, and what the attacker makes of the seven raw texts.

    python scripts/style_invariance.py
"""
from __future__ import annotations

import json
import os
import sys
import time

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from unsigned.pipeline.classify import BaselineClassifier   # noqa: E402
from unsigned.pipeline.facts import Facts                    # noqa: E402
from unsigned.pipeline.narrate import narrate                # noqa: E402
from unsigned.pipeline.run import build_card                 # noqa: E402
from unsigned.privacy.attacker import StyleAttacker          # noqa: E402

INCIDENTS = {
    "hostel B · night · standing 3 h · ₹500 · fear": [
        "seniors ne hostel b me raat ko 3 ghante khade rakha aur 500 rupees maange... dar lagta hai yaar...",
        "BHAI seniors ne hostel B me raat ko 3 ghante KHADE rakha aur 500 rupees maange!!! 😭😭 dar lagta hai!!!",
        "Sir, some seniors made me stand for 3 hours at night in Hostel B and demanded 500 rupees. I am scared.",
        "seniors ni hostel b madhe ratri 3 taas ubha kela ani 500 rupaye magitle na, khup bhiti vatte",
        "srs ne hostel b me rat ko 3 hrs khada rkha aur 500 rs maange, dar lgta h",
        "wow such a warm welcome?? seniors made us stand 3 hours at night in hostel B and asked 500 rupees, love it, scared now hmm",
        "सीनियर ने hostel B में रात को ३ घंटे खड़े रखा और ५०० रुपये मांगे, डर लगता है",
    ],
    "canteen · seniors · money demand · threats · repeated": [
        "canteen me seniors roz treat maangte hai... nahi diya to dhamki dete hai... phir se hua aaj",
        "CANTEEN me seniors roz TREAT maangte hai!!! 😡 nahi diya to dhamki!!! phir se hua aaj!!!",
        "Sir, seniors demand treats in the canteen every day and threaten us when we refuse. It happened again today.",
        "canteen madhe seniors roz treat magtat na, nahi dile tar dhamki detat, punha zala aaj",
        "canteen me srs roz treat mangte h, nhi diya to dhamki, phir se hua aj",
        "love how seniors 'ask' for treats in the canteen every day?? and threaten us if we say no. again today. amazing",
        "canteen में सीनियर रोज़ treat मांगते हैं, नहीं दिया तो धमकी देते हैं, फिर से हुआ आज",
    ],
    "ground · one senior · slap · public · injury": [
        "ground pe ek senior ne sabke saamne thappad mara... chot lagi hai...",
        "GROUND pe ek senior ne sabke saamne THAPPAD mara!!! 😭 chot lagi hai!!!",
        "Sir, one senior slapped me in front of everyone on the ground. I am hurt.",
        "ground var ek senior ni sagle samor thappad marla, chot lagli ahe",
        "ground pe ek sr ne sbke samne thappad mara, chot lgi h",
        "great day?? one senior slapped me in front of everyone on the ground, as a joke obviously. hurt now hmm",
        "ground पर एक सीनियर ने सबके सामने थप्पड़ मारा, चोट लगी है",
    ],
}


def main() -> None:
    df = pd.read_csv(os.path.join(ROOT, "data", "dev_seed.csv"))
    clf = BaselineClassifier().fit(df)
    att = StyleAttacker().fit(df["text"].tolist(), df["author"].astype(str).tolist())
    rows = []
    for name, styles in INCIDENTS.items():
        cards = [build_card(t, clf) for t in styles]
        fact_keys = {json.dumps({k: v for k, v in c.facts.items()}, sort_keys=True) for c in cards}
        fact_sentences = {narrate(Facts.from_dict(c.facts), "none", "routine").rsplit(" The reporter", 1)[0] for c in cards}
        accounts = {c.narrative() for c in cards}
        attr = [att.attribute(t)[0] for t in styles]
        rows.append({"incident": name, "styles": len(styles), "distinct_fact_graphs": len(fact_keys),
                     "distinct_fact_sentences": len(fact_sentences), "distinct_accounts": len(accounts),
                     "attacker_authors_on_raw": len(set(attr)), "account": sorted(accounts)[0]})
        print(f"\n{name}")
        print(f"  {len(styles)} styles -> {len(fact_keys)} fact graph(s), {len(fact_sentences)} fact sentence(s), {len(accounts)} account(s); "
              f"attacker sees {len(set(attr))} different author(s) in the raw texts")
        print("  ->", sorted(accounts)[0])
        if len(fact_keys) > 1:
            for t, c in zip(styles, cards):
                print("     ", t[:60], "|", {k: v for k, v in c.facts.items() if k in ("acts", "duration", "amount", "frequency", "consequences", "location", "time_bucket")})
    ev_path = os.path.join(ROOT, "models", "evaluation.json")
    ev = json.load(open(ev_path, encoding="utf-8")) if os.path.exists(ev_path) else {}
    ev["style_invariance"] = {"incidents": len(rows), "styles_per_incident": 7,
                              "fact_identical": sum(r["distinct_fact_sentences"] == 1 for r in rows),
                              "account_identical": sum(r["distinct_accounts"] == 1 for r in rows),
                              "rows": rows, "run_date": time.strftime("%Y-%m-%d %H:%M")}
    json.dump(ev, open(ev_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"\nfact sentences identical: {ev['style_invariance']['fact_identical']}/{len(rows)} · full accounts identical: {ev['style_invariance']['account_identical']}/{len(rows)}")
    print("wrote models/evaluation.json[style_invariance]")


if __name__ == "__main__":
    main()
