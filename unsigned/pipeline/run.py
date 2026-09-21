"""The sanitiser pipeline: raw text in (memory only) -> released card out.

    normalize -> classify -> extract -> facts (+ student's edits) -> card -> k-anonymity (card + per-fact)
    -> narrative from the closed lexicon -> attacker audit -> DISCARD TEXT

`process()` returns only the card, the audit numbers and timings. The caller must not keep
`text` after this returns; the API layer enforces that.
"""
from __future__ import annotations

import copy
import time
from typing import Callable, List, Optional, Tuple

from ..privacy.attacker import StyleAttacker
from ..privacy.audit import audit, AuditResult
from ..privacy.kanon import enforce_k, rarity_flags
from ..privacy.rarity import generalise_facts
from .card import Card, MAX_TYPES_PER_CARD
from .classify import BaselineClassifier
from .extract import extract
from .facts import apply_override, extract_facts, options
from .narrate import foreign_tokens
from .normalize import normalize
from .rules import apply_rules
from .translit import transliterate


def build_card(text: str, clf: BaselineClassifier, facts_override: Optional[dict] = None) -> Card:
    """Classify + extract + fact graph -> a card at full detail."""
    card, _ = build_card_with_spans(text, clf, facts_override)
    return card


def build_card_with_spans(text: str, clf: BaselineClassifier, facts_override: Optional[dict] = None) -> Tuple[Card, dict]:
    norm = normalize(text)
    pred = clf.predict(text)
    ex = extract(norm)
    facts, spans = extract_facts(norm, transliterate(text), ex["location"], ex["time_bucket"])   # numbers/units in either script
    if facts.actor_role == "unknown" and ex["actor_role"] != "unknown":
        facts.actor_role = ex["actor_role"]
    facts = apply_override(facts, facts_override)
    pred, fired = apply_rules(norm, pred, facts)
    types = sorted(set(pred["types"]) | set(facts.types()) | set(ex["types_from_behaviours"]))
    types = [t for t in types if t != "none"] or ["none"]
    types = types[:MAX_TYPES_PER_CARD]
    why = dict(pred.get("why", {}))
    if fired:
        why["rules"] = fired
    why["extracted_spans"] = [s for s in [ex["spans"]["location"], ex["spans"]["time"], ex["spans"]["actor"]] if s] \
        + [s for vals in spans.values() for s in vals][:8]
    card = Card(
        distress=pred["distress"], urgency=pred["urgency"], types=types,
        location=facts.location, time_bucket=facts.time_bucket, actor_role=facts.actor_role,
        behaviours=list(facts.acts), why=why, facts=facts.to_dict(),
    )
    return card, spans


def display(card: Card, released: List[Card], k: int = 3) -> Tuple[Card, bool, List[dict]]:
    """What the committee sees: per-fact k-anonymity, then card-level k on (place, time, type)."""
    shown, fact_status = generalise_facts(card, released, k)
    shown, k_ok = enforce_k(shown, released, k)
    if shown.facts:
        shown.facts["location"], shown.facts["time_bucket"] = shown.location, shown.time_bucket
    return shown, k_ok, fact_status


def preview(text: str, clf: BaselineClassifier, released: List[Card], k: int = 3, facts_override: Optional[dict] = None) -> dict:
    """What the committee WOULD see. Nothing is stored. Spans are the student's own words, returned
    to the student only, so the preview can show which words produced which fact."""
    card, spans = build_card_with_spans(text, clf, facts_override)
    flags = rarity_flags(copy.deepcopy(card), released, k)
    shown, _, fact_status = display(card, released, k)
    narrative = shown.narrative()
    return {
        "card": shown.to_dict(), "flags": flags, "facts": card.facts, "fact_status": fact_status,
        "spans": spans, "options": options(),
        "lexicon": {"tokens": len(narrative.split()), "foreign": len(foreign_tokens(narrative))},
    }


def process(text: str, clf: BaselineClassifier, attacker: Optional[StyleAttacker], released: List[Card], k: int = 3,
            demo_author: Optional[str] = None, facts_override: Optional[dict] = None,
            event_sink: Optional[Callable[[str, str, str, Optional[int], Optional[dict]], None]] = None) -> dict:
    t0 = time.perf_counter()
    card = build_card(text, clf, facts_override)                    # stored at full detail (facts are closed values)
    if event_sink:
        event_sink("FACTS_EXTRACTED", "pipeline", "ok", None, {"acts_count": len(card.facts.get("acts", []))})

    shown, k_ok, fact_status = display(card, released, k)
    if event_sink:
        event_sink("GENERALIZATION_APPLIED", "privacy", "ok", None,
                   {"k_satisfied": bool(k_ok), "widened_steps": len(shown.generalisation_steps)})

    narr = shown.narrative()
    ft = foreign_tokens(narr)
    if event_sink:
        event_sink("CARD_GENERATED", "pipeline", "ok", None, {"narrative_tokens": len(narr.split())})
        event_sink("CARD_VALIDATED", "pipeline", "ok", None, {"foreign_tokens": len(ft)})

    result: AuditResult = audit(text, shown, attacker, demo_author=demo_author)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    # --- the raw text is dropped here; only numbers and the card leave this function ---
    del text
    if event_sink:
        event_sink("RAW_BUFFER_RELEASED", "pipeline", "ok", elapsed_ms, {})
    return {"card": card, "shown": shown, "k_satisfied": k_ok, "fact_status": fact_status,
            "audit": result.to_dict(), "raw_discarded_after_ms": elapsed_ms}
