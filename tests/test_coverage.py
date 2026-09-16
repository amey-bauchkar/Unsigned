"""Extraction coverage on phrasings the dev seed was NOT written around — including the ones an
adversarial reviewer listed — and the lexicon invariant on every one of them.
Run: python tests/test_coverage.py   (or pytest)"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd  # noqa: E402

from unsigned.pipeline.classify import BaselineClassifier  # noqa: E402
from unsigned.pipeline.narrate import foreign_tokens        # noqa: E402
from unsigned.pipeline.normalize import normalize           # noqa: E402
from unsigned.pipeline.run import build_card                # noqa: E402
from unsigned.pipeline.translit import transliterate        # noqa: E402

SEED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "dev_seed.csv")
CLF = BaselineClassifier().fit(pd.read_csv(SEED))

# (text, acts that MUST be found, consequences that MUST be found)
CASES = [
    ("सीनियर ने हॉस्टल में रात को ३ घंटे खड़े रखा और ५०० रुपये मांगे, वीडियो भी बनाया", {"forced_standing", "money_demand", "recording"}, set()),
    ("सिनियर्स नी मला उभं केलं आणि पैसे मागितले, खूप भीती वाटते", {"forced_standing", "money_demand"}, {"fear"}),
    ("they wouldn't let me leave the room and threw water on me, ye teesri baar hai", {"confinement", "physical_violence"}, set()),
    ("woh bahut aggressive behave karte hain, mujhe bahut takleef ho rahi hai", {"threats"}, {"mental_distress"}),
    ("seniors locked us in the common room till 2 am and made us sing", {"confinement", "forced_performance"}, set()),
    ("ek senior ne canteen me sabke saamne thappad mara, chot lagi hai, dar lagta hai", {"physical_violence", "public_humiliation"}, {"injury", "fear"}),
    ("roz raat ko 11 baje bulate hai aur intro dene bolte hai, neend nahi aati", {"summoning", "forced_introductions"}, {"sleep_loss"}),
    ("unhone mera phone le liya aur mere photos whatsapp group me daal diye", {"phone_confiscation", "sharing_online"}, set()),
    ("mere saath jo kiya woh galat tha", set(), set()),                          # no act cue -> honest empty graph
    ("the mess food?? cold again. what a surprise hmm", set(), set()),
]


def test_devanagari_reaches_the_cues():
    t = transliterate("रात को ३ घंटे खड़े रखा")
    assert "raat" in t and "3" in t and "khade" in t


def test_normaliser_maps_transliterated_forms():
    n = normalize("सीनियर ने पैसे मांगे")
    assert n.startswith("senior") and "paise" in n


def test_extraction_coverage_on_unseen_phrasings():
    misses = []
    for text, acts, cons in CASES:
        c = build_card(text, CLF)
        got_acts, got_cons = set(c.facts["acts"]), set(c.facts["consequences"])
        if not acts <= got_acts or not cons <= got_cons:
            misses.append((text[:50], acts - got_acts, cons - got_cons))
    assert not misses, misses


def test_lexicon_invariant_holds_on_all_cases():
    for text, _, _ in CASES:
        assert foreign_tokens(build_card(text, CLF).narrative()) == []


def test_release_channel_fuzz_small():
    """150 adversarial inputs with canaries: nothing the student typed reaches the account or the stored card."""
    import importlib.util, json, random
    spec = importlib.util.spec_from_file_location("fz", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "fuzz_release_channel.py"))
    fz = importlib.util.module_from_spec(spec); spec.loader.exec_module(fz)
    rng = random.Random(3)
    for i in range(150):
        text, c = fz.gen(rng, i)
        card = build_card(text, CLF)
        account = card.narrative()
        stored = json.dumps({k: v for k, v in card.to_dict().items() if k != "why"}, ensure_ascii=False)
        assert foreign_tokens(account) == [] and c.lower() not in account.lower() and c.lower() not in stored.lower(), text[:60]


def test_style_invariance_three_incidents_seven_styles():
    import importlib.util
    spec = importlib.util.spec_from_file_location("si", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "style_invariance.py"))
    si = importlib.util.module_from_spec(spec); spec.loader.exec_module(si)
    for name, styles in si.INCIDENTS.items():
        accounts = {build_card(t, CLF).narrative() for t in styles}
        assert len(accounts) == 1, (name, accounts)


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in list(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print("ok ", f.__name__)
    print(f"{len(fns)} tests passed")
