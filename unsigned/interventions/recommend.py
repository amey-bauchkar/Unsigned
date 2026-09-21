"""Deterministic, rule-based Recommended Intervention Engine.

The recommendation engine never receives raw complaint text and operates only on
privacy-safe aggregate pattern data (location_group, time_bucket, incident_type, counts, p_value).

Enforces strict null behavior: if no predefined actionable rule matches,
recommend_for_pattern() returns None.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .tracker import ACTION_TYPES, ASSIGNED_UNITS


class RecommendationRule:
    """A deterministic, policy-controlled intervention rule."""

    def __init__(
        self,
        rule_id: str,
        matcher: Callable[[Dict[str, Any]], bool],
        action: str,
        action_type: str,
        assigned_unit: str,
        reason_template: str,
    ):
        self.rule_id = rule_id
        self.matcher = matcher
        self.action = action
        assert action_type in ACTION_TYPES, f"Invalid action_type: {action_type}"
        self.action_type = action_type
        assert assigned_unit in ASSIGNED_UNITS, f"Invalid assigned_unit: {assigned_unit}"
        self.assigned_unit = assigned_unit
        self.reason_template = reason_template

    def evaluate(self, pattern: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.matcher(pattern):
            return None
        loc = pattern.get("location", "unknown")
        tb = pattern.get("time_bucket", "unknown")
        typ = pattern.get("type", "unknown")
        cnt = pattern.get("cards_this_week", 0)
        base = pattern.get("baseline_per_week", 0.0)
        p_val = pattern.get("p_value", 1.0)

        reason = self.reason_template.format(
            location=loc.replace("_", " "),
            time_bucket=tb.replace("_", " "),
            type=typ.replace("_", " "),
            count=cnt,
            baseline=base,
        )

        return {
            "id": self.rule_id,
            "recommendation": self.action,
            "action_type": self.action_type,
            "assigned_unit": self.assigned_unit,
            "reason": reason,
            "source_pattern": {
                "location": loc,
                "time_bucket": tb,
                "type": typ,
                "cards_this_week": cnt,
                "baseline_per_week": base,
                "p_value": p_val,
            },
            "status": "recommended",
        }


# Helpers for matching patterns
def _is_hostel(loc: str) -> bool:
    return loc in ("hostel_a", "hostel_b", "hostel_c", "hostels") or loc.startswith("hostel_")


def _is_night_or_eve(tb: str) -> bool:
    return tb in ("night", "evening", "night_or_evening")


# Predefined, actionable institutional policy rules
RECOMMENDATION_RULES: List[RecommendationRule] = [
    # 1. Hostel + Night + Coercion
    RecommendationRule(
        rule_id="hostel_night_coercion",
        matcher=lambda p: (
            _is_hostel(p.get("location", ""))
            and p.get("time_bucket", "") in ("night", "night_or_evening")
            and p.get("type") == "coercion_forced_acts"
            and p.get("cards_this_week", 0) >= 3
            and p.get("p_value", 1.0) < 0.01
        ),
        action="Doubled anti-ragging squad night patrols and corridor monitoring",
        action_type="patrol",
        assigned_unit="anti_ragging_squad",
        reason_template="Recurring coercion incidents detected during night hours in hostel accommodations ({count} cards this week vs ~{baseline}/wk).",
    ),
    # 2. Hostel + Night/Evening + Verbal Abuse
    RecommendationRule(
        rule_id="hostel_night_verbal_intimidation",
        matcher=lambda p: (
            _is_hostel(p.get("location", ""))
            and _is_night_or_eve(p.get("time_bucket", ""))
            and p.get("type") == "verbal_abuse"
            and p.get("cards_this_week", 0) >= 3
            and p.get("p_value", 1.0) < 0.01
        ),
        action="Scheduled senior warden floor inspections and proctor check-ins",
        action_type="inspection",
        assigned_unit="warden_board",
        reason_template="Elevated verbal intimidation patterns detected during night/evening hours in residential hostel blocks.",
    ),
    # 3. Hostel + Financial Extortion
    RecommendationRule(
        rule_id="hostel_financial_extortion",
        matcher=lambda p: (
            _is_hostel(p.get("location", ""))
            and p.get("type") == "extortion_financial"
            and p.get("cards_this_week", 0) >= 3
            and p.get("p_value", 1.0) < 0.01
        ),
        action="Dispatched proctorial inquiry team and posted anonymous anti-extortion notices",
        action_type="helpline_notice",
        assigned_unit="proctorial_board",
        reason_template="Systematic extortion or unauthorized financial collections reported in student hostel blocks.",
    ),
    # 4. Academic Building/Corridors + Physical Aggression
    RecommendationRule(
        rule_id="academic_corridor_physical",
        matcher=lambda p: (
            p.get("location", "") in ("academic", "classroom", "lab", "corridor")
            and p.get("type") == "physical"
            and p.get("cards_this_week", 0) >= 2
            and p.get("p_value", 1.0) < 0.01
        ),
        action="Stationed faculty vigilance squad and security monitoring in academic corridors",
        action_type="patrol",
        assigned_unit="anti_ragging_squad",
        reason_template="Physical aggression incidents identified in academic buildings and corridors.",
    ),
    # 5. Dining/Mess + Financial Extortion
    RecommendationRule(
        rule_id="dining_common_area_extortion",
        matcher=lambda p: (
            p.get("location", "") in ("common_areas", "mess", "canteen")
            and p.get("type") == "extortion_financial"
            and p.get("cards_this_week", 0) >= 3
            and p.get("p_value", 1.0) < 0.01
        ),
        action="Enforced dining hall proctorial surveillance and anti-extortion checkpoint monitoring",
        action_type="surveillance",
        assigned_unit="security_staff",
        reason_template="Systematic financial extortion demands reported in dining and common gathering facilities.",
    ),
    # 6. Transit Routes/Gates + Evening/Night Harassment
    RecommendationRule(
        rule_id="campus_transit_evening_harassment",
        matcher=lambda p: (
            p.get("location", "") in ("transit", "gate", "bus")
            and _is_night_or_eve(p.get("time_bucket", ""))
            and p.get("type") in ("verbal_abuse", "coercion_forced_acts", "sexual_harassment")
            and p.get("cards_this_week", 0) >= 3
            and p.get("p_value", 1.0) < 0.01
        ),
        action="Installed security checkpoint post and scheduled evening perimeter vehicle patrols",
        action_type="patrol",
        assigned_unit="security_staff",
        reason_template="Repeated harassment patterns identified along campus transit routes and perimeter gates during evening/night hours.",
    ),
    # 7. Digital Platforms + Online Harassment / Cyber
    RecommendationRule(
        rule_id="digital_online_harassment",
        matcher=lambda p: (
            (p.get("location", "") == "online" or p.get("type") == "cyber")
            and p.get("cards_this_week", 0) >= 3
            and p.get("p_value", 1.0) < 0.01
        ),
        action="Student counseling cell outreach and digital harassment advisory broadcast",
        action_type="counseling_setup",
        assigned_unit="student_affairs",
        reason_template="Repeated online harassment or cyber intimidation patterns detected across digital platforms.",
    ),
]


def recommend_for_pattern(pattern: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Evaluate a single aggregate pattern against predefined rules.

    Strict null behavior:
    If no rule matches, or actionable thresholds are not met, returns None.
    """
    for rule in RECOMMENDATION_RULES:
        rec = rule.evaluate(pattern)
        if rec is not None:
            return rec
    return None


def get_recommendations_for_patterns(
    alerts: List[Dict[str, Any]],
    active_interventions: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Aggregate recommendations across active pattern alerts.

    Filters out None results and skips patterns that already have an active intervention.
    Always returns a list (empty if no recommendations match).
    """
    active_keys = set()
    if active_interventions:
        for inv in active_interventions:
            if inv.get("status") == "active":
                loc = inv.get("location_group", "").strip().lower()
                tb = inv.get("time_bucket", "").strip().lower()
                typ = inv.get("incident_type", "").strip().lower()
                active_keys.add((loc, tb, typ))

    recommendations: List[Dict[str, Any]] = []
    seen_keys = set()

    for alert in alerts:
        loc = alert.get("location", "").strip().lower()
        tb = alert.get("time_bucket", "").strip().lower()
        typ = alert.get("type", "").strip().lower()
        pat_key = (loc, tb, typ)

        # If already addressed by an active intervention or already recommended, skip
        if pat_key in active_keys or pat_key in seen_keys:
            continue

        rec = recommend_for_pattern(alert)
        if rec is not None:
            seen_keys.add(pat_key)
            recommendations.append(rec)

    return recommendations
