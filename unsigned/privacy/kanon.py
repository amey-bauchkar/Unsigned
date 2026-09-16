"""K1 — k-anonymity generaliser for cards.

A released (location, time_bucket) combination with a shared type must appear in at
least k cards; otherwise location, then time, are generalised up their hierarchies until
it does. Cards that cannot reach k at the coarsest level are quarantined — the
committee sees only a count until more cards arrive or a time limit forces
release at the coarsest level.
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable, List, Optional, Tuple

from ..pipeline.card import Card, LOCATION_HIERARCHY, TIME_HIERARCHY


def _parent(h: dict, leaf: str) -> Optional[str]:
    return h.get(leaf)


def generalise_once(card: Card) -> bool:
    """Generalise one step (location first, then time). Returns False if at the root."""
    p = _parent(LOCATION_HIERARCHY, card.location)
    if p is not None:
        card.generalisation_steps.append(f"location: {card.location} -> {p}")
        card.location = p
        return True
    p = _parent(TIME_HIERARCHY, card.time_bucket)
    if p is not None:
        card.generalisation_steps.append(f"time: {card.time_bucket} -> {p}")
        card.time_bucket = p
        return True
    return False


def key_counts(released: Iterable[Card]) -> Counter:
    return Counter(c.key() for c in released)


def enforce_k(card: Card, released: List[Card], k: int = 3) -> Tuple[Card, bool]:
    """Generalise *card* until its key appears >= k-1 times among released cards
    (so that with this card the group has size >= k). Returns (card, satisfied).

    Counting is done against released cards *re-generalised to the same level*,
    so a specific card can join a coarser group.
    """
    while True:
        n = sum(1 for r in released if _matches_at_level(r, card))
        if n + 1 >= k:
            return card, True
        if not generalise_once(card):
            return card, False


def _matches_at_level(released_card: Card, card: Card) -> bool:
    """Does the released card fall under card's (possibly generalised) location/time/types?"""
    return (
        _is_under(LOCATION_HIERARCHY, released_card.location, card.location)
        and _is_under(TIME_HIERARCHY, released_card.time_bucket, card.time_bucket)
        and bool(set(released_card.types) & set(card.types))      # any shared type: types are content, not identity
    )


def _is_under(h: dict, leaf: str, ancestor: str) -> bool:
    node: Optional[str] = leaf
    steps = 0
    while node is not None and steps < 12:
        steps += 1
        if node == ancestor:
            return True
        node = h.get(node)
    return False


def rarity_flags(card: Card, released: List[Card], k: int = 3) -> List[str]:
    """Human-readable warnings for the pre-submission privacy preview."""
    flags = []
    n = sum(1 for r in released if _matches_at_level(r, card))
    if n + 1 < k:
        flags.append(
            f"This combination ({card.location.replace('_', ' ')}, {card.time_bucket.replace('_', ' ')}, "
            f"{', '.join(card.types)}) matches fewer than {k} reports — it will be generalised before release."
        )
    return flags
