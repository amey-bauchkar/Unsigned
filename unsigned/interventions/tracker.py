"""Intervention Tracker — close the institutional intelligence loop:
DETECT -> INTERVENE -> MEASURE.

Tracks institutional actions targeting generalized patterns (location_group, time_bucket, incident_type).
Never links to individual students, cases, tokens, or complaints.
Computes before/after observed report rates using matched observation windows.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional

from ..patterns.detect import rollup, GROUP_LEVEL

ACTION_TYPES = {
    "patrol",
    "surveillance",
    "inspection",
    "policy_briefing",
    "counseling_setup",
    "helpline_notice",
    "disciplinary_hearing",
    "other",
}

ASSIGNED_UNITS = {
    "warden_board",
    "proctorial_board",
    "anti_ragging_squad",
    "security_staff",
    "student_affairs",
}

STATUSES = {"planned", "active", "completed", "reviewed"}


def init_interventions_table(con: sqlite3.Connection) -> None:
    """Create interventions schema if it doesn't already exist."""
    con.executescript("""
    CREATE TABLE IF NOT EXISTS interventions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location_group TEXT NOT NULL,
        time_bucket TEXT NOT NULL,
        incident_type TEXT NOT NULL,
        action TEXT NOT NULL,
        action_type TEXT NOT NULL DEFAULT 'patrol',
        assigned_unit TEXT NOT NULL DEFAULT 'anti_ragging_squad',
        status TEXT NOT NULL DEFAULT 'active',
        started_at REAL NOT NULL,
        review_at REAL,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL,
        institutional_note TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_interventions_status ON interventions(status);
    """)


def compute_outcome(
    con: sqlite3.Connection,
    intervention: Dict[str, Any],
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Calculate aggregate before/after incident metrics using matched observation windows.

    comparison_days = min(7, int(elapsed_days_since_start))
    If elapsed_days < 2, marks insufficient_data = True.
    """
    now = now if now is not None else time.time()
    started_at = float(intervention["started_at"])
    elapsed_days = max(0.0, (now - started_at) / 86400.0)

    if elapsed_days < 2.0:
        return {
            "insufficient_data": True,
            "message": "Insufficient post-intervention data (minimum 2 days required)",
            "comparison_days": round(elapsed_days, 1),
            "before_count": None,
            "after_count": None,
            "before_rate": None,
            "after_rate": None,
            "observed_change_pct": None,
            "display_summary": "Insufficient post-intervention data",
        }

    comparison_days = min(7, int(elapsed_days))
    pre_start = started_at - (comparison_days * 86400)
    pre_end = started_at
    post_start = started_at
    post_end = started_at + (comparison_days * 86400)

    target_loc = intervention["location_group"].strip().lower()
    target_tb = intervention["time_bucket"].strip().lower()
    target_type = intervention["incident_type"].strip().lower()

    rows = con.execute(
        "SELECT card_json, release_at FROM cards WHERE released=1 AND release_at >= ?",
        (pre_start,),
    ).fetchall()

    before_count = 0
    after_count = 0

    for r in rows:
        rel_at = float(r["release_at"])
        if rel_at < pre_start or rel_at > post_end:
            continue

        try:
            d = json.loads(r["card_json"])
        except Exception:
            continue

        card_loc = rollup(d.get("location", "unknown"))
        card_tb = (d.get("time_bucket") or "unknown").lower()
        card_types = [t.lower() for t in d.get("types", [])]

        loc_match = (target_loc in ("all", "campus")) or (card_loc == target_loc)
        tb_match = (target_tb in ("any", "unknown", "all")) or (card_tb == target_tb)
        type_match = (target_type in ("all", "any")) or (target_type in card_types)

        if loc_match and tb_match and type_match:
            if pre_start <= rel_at < pre_end:
                before_count += 1
            elif post_start <= rel_at <= post_end:
                after_count += 1

    before_rate = round(before_count / comparison_days, 2)
    after_rate = round(after_count / comparison_days, 2)

    if before_count > 0:
        observed_change_pct = round(((after_count - before_count) / before_count) * 100.0, 1)
    elif after_count > 0:
        observed_change_pct = 100.0
    else:
        observed_change_pct = 0.0

    sign = "+" if observed_change_pct > 0 else ""
    return {
        "insufficient_data": False,
        "message": f"Observed report change over {comparison_days}-day matched window",
        "comparison_days": comparison_days,
        "before_count": before_count,
        "after_count": after_count,
        "before_rate": before_rate,
        "after_rate": after_rate,
        "observed_change_pct": observed_change_pct,
        "display_summary": (
            f"BEFORE: {before_count} reports / {comparison_days} days · "
            f"AFTER: {after_count} reports / {comparison_days} days · "
            f"OBSERVED CHANGE: {sign}{observed_change_pct}%"
        ),
    }


def create_intervention(
    con: sqlite3.Connection,
    location_group: str,
    time_bucket: str,
    incident_type: str,
    action: str,
    action_type: str = "patrol",
    assigned_unit: str = "anti_ragging_squad",
    status: str = "active",
    started_at: Optional[float] = None,
    review_at: Optional[float] = None,
    institutional_note: Optional[str] = None,
) -> int:
    """Record a new institutional intervention targeting a generalized pattern."""
    now = time.time()
    st = started_at if started_at is not None else now
    rev = review_at if review_at is not None else (st + 7 * 86400)

    act_type = action_type.strip().lower() if action_type in ACTION_TYPES else "other"
    unit = assigned_unit.strip().lower() if assigned_unit in ASSIGNED_UNITS else "anti_ragging_squad"
    st_val = status.strip().lower() if status in STATUSES else "active"

    # Sanitize note: purely administrative, capped length
    safe_note = institutional_note[:256].strip() if institutional_note else None

    cur = con.execute(
        """
        INSERT INTO interventions (
            location_group, time_bucket, incident_type, action, action_type,
            assigned_unit, status, started_at, review_at, created_at, updated_at, institutional_note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            location_group.strip().lower(),
            time_bucket.strip().lower(),
            incident_type.strip().lower(),
            action.strip()[:120],
            act_type,
            unit,
            st_val,
            st,
            rev,
            now,
            now,
            safe_note,
        ),
    )
    return cur.lastrowid


def get_interventions(
    con: sqlite3.Connection,
    status_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve interventions enriched with computed matched-window outcome metrics."""
    if status_filter and status_filter in STATUSES:
        rows = con.execute(
            "SELECT * FROM interventions WHERE status=? ORDER BY started_at DESC",
            (status_filter,),
        ).fetchall()
    else:
        rows = con.execute("SELECT * FROM interventions ORDER BY started_at DESC").fetchall()

    out = []
    for r in rows:
        d = dict(r)
        d["outcome"] = compute_outcome(con, d)
        d["started_at_str"] = time.strftime("%d/%m/%Y", time.localtime(d["started_at"]))
        d["review_at_str"] = time.strftime("%d/%m/%Y", time.localtime(d["review_at"])) if d["review_at"] else "—"
        out.append(d)
    return out


def get_intervention_by_id(con: sqlite3.Connection, intervention_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve a single intervention with outcome metrics."""
    row = con.execute("SELECT * FROM interventions WHERE id=?", (intervention_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["outcome"] = compute_outcome(con, d)
    d["started_at_str"] = time.strftime("%d/%m/%Y", time.localtime(d["started_at"]))
    d["review_at_str"] = time.strftime("%d/%m/%Y", time.localtime(d["review_at"])) if d["review_at"] else "—"
    return d


def update_intervention(
    con: sqlite3.Connection,
    intervention_id: int,
    status: Optional[str] = None,
    review_at: Optional[float] = None,
    action: Optional[str] = None,
    institutional_note: Optional[str] = None,
) -> bool:
    """Update status, review date, action or administrative note of an existing intervention."""
    fields = []
    params = []

    if status and status in STATUSES:
        fields.append("status=?")
        params.append(status)
    if review_at is not None:
        fields.append("review_at=?")
        params.append(review_at)
    if action:
        fields.append("action=?")
        params.append(action[:120].strip())
    if institutional_note is not None:
        fields.append("institutional_note=?")
        params.append(institutional_note[:256].strip())

    if not fields:
        return False

    fields.append("updated_at=?")
    params.append(time.time())
    params.append(intervention_id)

    cur = con.execute(f"UPDATE interventions SET {', '.join(fields)} WHERE id=?", params)
    return cur.rowcount > 0
