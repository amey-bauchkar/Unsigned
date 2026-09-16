"""P1 — rising-pattern detector over released cards.

Counts cards per (location, time_bucket, type) per week and flags a group when
this week's count is a Poisson surprise against the group's own history and at
least `min_cards` distinct cards contribute. The committee acts on the group —
the hostel, the hour, the behaviour — not on a person.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

from scipy.stats import poisson

from ..pipeline.card import LOCATION_HIERARCHY

# Detection happens at the same level the heat grid shows, so a floor and its hostel count together.
GROUP_LEVEL = {"hostel_a", "hostel_b", "hostel_c", "common_areas", "academic", "transit", "online", "campus", "unknown"}


def rollup(location: str) -> str:
    node = location
    steps = 0
    while node is not None and node not in GROUP_LEVEL and steps < 12:
        steps += 1
        node = LOCATION_HIERARCHY.get(node)
    return node or "unknown"


def weekly_counts(cards: List[dict]) -> Dict[Tuple[str, str, str], Dict[int, int]]:
    """cards: dicts with location, time_bucket, types(list), week(int)."""
    counts: Dict[Tuple[str, str, str], Dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for c in cards:
        for t in c["types"]:
            if t == "none":
                continue
            counts[(rollup(c["location"]), c["time_bucket"], t)][c["week"]] += 1
    return counts


def detect(cards: List[dict], current_week: int, min_cards: int = 3, alpha: float = 0.01, history_weeks: int = 6) -> List[dict]:
    """Return alerts for groups whose current-week count is a Poisson surprise."""
    alerts = []
    for key, by_week in weekly_counts(cards).items():
        now = by_week.get(current_week, 0)
        if now < min_cards:
            continue
        hist = [by_week.get(w, 0) for w in range(current_week - history_weeks, current_week)]
        baseline = max(sum(hist) / max(len(hist), 1), 0.25)     # floor avoids zero-rate degeneracy
        p = float(poisson.sf(now - 1, baseline))                  # P(X >= now)
        if p < alpha:
            loc, tb, typ = key
            alerts.append({
                "location": loc, "time_bucket": tb, "type": typ, "week": current_week,
                "cards_this_week": now, "baseline_per_week": round(baseline, 2), "p_value": p,
                "message": f"Rising pattern: {typ.replace('_', ' ')} at {loc.replace('_', ' ')} during "
                           f"{tb.replace('_', ' ')} — {now} distinct cards this week vs ~{baseline:.1f} usual.",
                "suggested_action": "Increase warden presence at this location/time; brief the anti-ragging squad; "
                                    "post the helpline notice in the location.",
            })
    return sorted(alerts, key=lambda a: a["p_value"])
