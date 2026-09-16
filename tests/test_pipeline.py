"""Unit tests for the sanitiser pipeline.  Run:  python -m pytest -q   (or)   python tests/test_pipeline.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd  # noqa: E402

from unsigned.pipeline.card import Card, channel_capacity_bits            # noqa: E402
from unsigned.pipeline.classify import BaselineClassifier                # noqa: E402
from unsigned.pipeline.extract import extract                            # noqa: E402
from unsigned.pipeline.normalize import normalize                        # noqa: E402
from unsigned.pipeline.run import build_card, process                    # noqa: E402
from unsigned.privacy.attacker import StyleAttacker, leave_one_out_accuracy  # noqa: E402
from unsigned.privacy.kanon import enforce_k                             # noqa: E402
from unsigned.patterns.detect import detect                              # noqa: E402

SEED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "dev_seed.csv")
DF = pd.read_csv(SEED)


def test_normalize_canonicalises_variants_and_strips_emoji():
    n = normalize("Wow such a WARM welcome from srs 😂😂 nhi bola kisi ko!!! 3 ghante")
    assert "😂" not in n and "seniors" in n and "nahi" in n and "<num>" in n and "!!!" not in n


def test_extract_finds_location_time_actor_behaviours():
    ex = extract(normalize("Seniors ne hostel B second floor pe raat ko 3 ghante khade rakha aur paise maange"))
    assert ex["location"] == "hostel_b_floor2" and ex["time_bucket"] == "night" and ex["actor_role"] == "seniors"
    assert {"forced_standing", "money_demand"} <= set(ex["behaviours"])


def test_card_narrative_is_template_only():
    c = Card("high", "soon", ["coercion_forced_acts"], "hostel_b", "night", "seniors", ["forced_standing"])
    assert c.narrative().startswith("Reported:") and channel_capacity_bits() > 0


def test_attacker_beats_chance_on_raw_but_not_on_cards():
    texts, authors = DF["text"].tolist(), DF["author"].tolist()
    acc_raw = leave_one_out_accuracy(texts, authors)
    clf = BaselineClassifier().fit(DF)
    cards = [build_card(t, clf).narrative() for t in texts]
    acc_cards = leave_one_out_accuracy(cards, authors)
    chance = 1 / len(set(authors))
    assert acc_raw > 3 * chance, acc_raw
    assert acc_cards <= chance + 0.05, acc_cards


def test_kanon_generalises_until_k():
    clf = BaselineClassifier().fit(DF)
    released = []
    shown, ok = enforce_k(build_card("seniors ne hostel b me raat ko khade rakha", clf), released, k=3)
    assert not ok and shown.location == "campus"          # nothing to hide among yet -> coarsest level
    for t in ["hostel b night seniors forced us to stand", "raat ko hostel b me seniors ne khada rakha"]:
        released.append(build_card(t, clf))
    shown, ok = enforce_k(build_card("hostel b me raat ko seniors ne khade rakha", clf), released, k=3)
    assert ok and shown.location == "hostel_b" and shown.time_bucket == "night"


def test_audit_lexicon_invariant_and_text_not_returned():
    clf = BaselineClassifier().fit(DF)
    att = StyleAttacker().fit(DF["text"].tolist(), DF["author"].tolist())
    r = process("wow such a great welcome?? standing 3 hours in hostel b at night hmm", clf, att, [], k=3, demo_author="A06")
    a = r["audit"]
    assert a["foreign_tokens"] == 0 and a["narrative_tokens"] > 8       # a real narrative, entirely from the lexicon
    assert a["raw_p_true"] > 0.3                                         # the raw text would have exposed the author
    assert "text" not in r and r["raw_discarded_after_ms"] >= 0


def test_facts_extraction_bands_numbers_and_reads_hinglish():
    from unsigned.pipeline.facts import extract_facts
    raw = "Seniors ne hostel B pe raat ko 3 ghante khade rakha aur 500 rupees maange, video banaya, phir se hua, dar lagta hai"
    f, spans = extract_facts(normalize(raw), raw, "hostel_b", "night")
    assert {"forced_standing", "money_demand", "recording"} <= set(f.acts)
    assert f.duration == "2h_5h" and f.amount == "100_500" and f.frequency == "repeated"
    assert "fear" in f.consequences and "video" in f.digital and f.actor_role == "seniors"
    assert spans["amount"] == ["500 rupees"]                              # spans go to the student only


def test_narrative_never_contains_student_words():
    from unsigned.pipeline.narrate import foreign_tokens, LEXICON
    clf = BaselineClassifier().fit(DF)
    weird = "BHAI kal raat seniors ne KHADE rakha!!! 😭😭 intro intro intro!!! yaar bahut dar lag raha h"
    c = build_card(weird, clf)
    n = c.narrative()
    assert foreign_tokens(n) == [] and "bhai" not in n.lower() and "yaar" not in n.lower() and "😭" not in n
    for t in DF["text"]:                                                  # whole corpus: zero violations
        assert foreign_tokens(build_card(t, clf).narrative()) == []
    assert len(LEXICON) < 400                                             # the channel is small by design


def test_per_fact_generalisation_coarsens_identifiers_but_keeps_acts():
    from unsigned.privacy.rarity import generalise_facts
    clf = BaselineClassifier().fit(DF)
    lone = build_card("ek senior ne lab me raat ko 2 ghante khade rakha aur 1500 rupees liye, sabke saamne", clf)
    shown, status = generalise_facts(lone, released=[], k=3)
    by = {s["field"]: s for s in status if s["field"] in ("amount", "duration", "actor_count")}
    assert by["amount"]["status"] == "generalised" and shown.facts["amount"] == "some"
    assert by["duration"]["status"] == "generalised" and shown.facts["duration"] == "unknown"
    assert set(shown.facts["acts"]) == set(lone.facts["acts"])           # what happened is never suppressed


def test_override_is_validated_against_closed_sets():
    from unsigned.pipeline.facts import Facts, apply_override
    f = Facts(acts=["forced_standing"], amount="100_500")
    g = apply_override(f, {"acts": ["threats", "<script>"], "amount": "over_9000", "public": 1})
    assert g.acts == ["threats"] and g.amount == "100_500" and g.public is True


def test_pattern_detector_fires_on_surge_only():
    quiet = [{"location": "hostel_b", "time_bucket": "night", "types": ["coercion_forced_acts"], "week": w} for w in range(1, 6)]
    surge = [{"location": "hostel_b", "time_bucket": "night", "types": ["coercion_forced_acts"], "week": 6} for _ in range(5)]
    assert detect(quiet, current_week=5) == []
    alerts = detect(quiet + surge, current_week=6)
    assert alerts and alerts[0]["location"] == "hostel_b"


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in list(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print("ok ", f.__name__)
    print(f"{len(fns)} tests passed")
