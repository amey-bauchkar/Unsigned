"""Attacker-in-the-loop release audit.

Runs inside the pipeline while the raw text is still in memory. Only numbers survive.

What is measured, and why each number exists:

  foreign_tokens  — STRUCTURAL guarantee. The released narrative is generated from the closed
                    lexicon (narrate.py); this counts tokens outside it. It is 0 by construction
                    and re-checked here, because a guarantee that is not re-checked is a hope.
  raw_top_prob    — what a warden holding the raw text could do: the attacker's confidence.
  released_top_prob — the attacker's confidence on the narrative. Forced-choice models are always
                    confident about *something*, so this is reported but not used as the meter.
  leak_tv         — information the narrative gives the attacker beyond the categorical card
                    (total variation between its posteriors). This is CONTENT information —
                    the facts the committee is meant to receive — never style, which cannot enter.
  p_true          — DEMO / EVALUATION ONLY: probability on a designated reference author, on the
                    raw text vs on the narrative. The honest per-card number when the truth is known.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Optional

from .attacker import StyleAttacker
from ..pipeline.card import Card
from ..pipeline.narrate import foreign_tokens


@dataclass
class AuditResult:
    chance: float
    raw_top_author: str
    raw_top_prob: float
    raw_p_true: Optional[float]
    released_p_true: Optional[float]
    released_top_prob: float
    leak_tv: float
    narrative_tokens: int
    foreign_tokens: int
    margin_allowed: float
    detail_kept: bool
    decision: str

    def to_dict(self) -> dict:
        return asdict(self)


def _tv(p: Dict[str, float], q: Dict[str, float]) -> float:
    keys = set(p) | set(q)
    return 0.5 * float(sum(abs(p.get(k, 0.0) - q.get(k, 0.0)) for k in keys))


def audit(text: str, card: Card, attacker: Optional[StyleAttacker], margin: float = 0.20,
          demo_author: Optional[str] = None) -> AuditResult:
    narrative = card.narrative()
    n_tokens = len(narrative.split())
    foreign = foreign_tokens(narrative)
    if foreign:                                        # cannot happen (narrate() raises), belt and braces
        card.facts = {}
        narrative = card.narrative()
        foreign = foreign_tokens(narrative)

    if attacker is None or not attacker.fitted:
        return AuditResult(0.0, "n/a", 0.0, None, None, 0.0, 0.0, n_tokens, len(foreign), margin, bool(card.facts),
                           "no attacker loaded -> lexicon check only")

    chance = attacker.chance()
    if demo_author and demo_author not in attacker.authors:
        demo_author = None
    raw_author, raw_p, raw_dist = attacker.attribute(text)
    _, rel_p, rel_dist = attacker.attribute(narrative)
    _, _, null_dist = attacker.attribute(card.template_narrative())
    leak = _tv(rel_dist, null_dist)
    decision = (f"released: lexicon narrative, {n_tokens} tokens, {len(foreign)} foreign"
                if card.facts else "released: template only")
    return AuditResult(
        chance, raw_author, float(raw_p),
        float(raw_dist.get(demo_author, 0.0)) if demo_author else None,
        float(rel_dist.get(demo_author, 0.0)) if demo_author else None,
        float(rel_p), float(leak), n_tokens, len(foreign), margin, bool(card.facts), decision,
    )
