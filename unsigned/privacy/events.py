"""Privacy event logging — inspectable lifecycle stream without student text.

Records operational lifecycle events (INPUT_RECEIVED, FACTS_EXTRACTED,
GENERALIZATION_APPLIED, CARD_GENERATED, CARD_VALIDATED, RAW_BUFFER_RELEASED,
CARD_STORED, etc.) using a strictly controlled vocabulary and sanitized metadata.

Never stores: raw text, complaint body, student words, IP, email, phone, token.
Retention is bounded to at most 500 events.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional

EVENT_TYPES = {
    "INPUT_RECEIVED",
    "FACTS_EXTRACTED",
    "GENERALIZATION_APPLIED",
    "CARD_GENERATED",
    "CARD_VALIDATED",
    "RAW_BUFFER_RELEASED",
    "CARD_STORED",
    "MESSAGE_SENT",
    "PRIVACY_TEST_STARTED",
    "PRIVACY_TEST_COMPLETED",
    "PRIVACY_TEST_FAILED",
    "PROCESSING_FAILED",
}

SUBSYSTEMS = {"pipeline", "storage", "privacy", "audit", "privacy_health", "committee"}

FORBIDDEN_KEYS = {
    "text", "raw", "raw_text", "body", "token", "token_hash",
    "ip", "email", "phone", "payload", "narrative", "author", "student",
    "passphrase", "name", "roll_number", "content",
}

MAX_RETENTION = 500

CATEGORY_MAP = {
    "privacy": {
        "GENERALIZATION_APPLIED", "CARD_VALIDATED", "RAW_BUFFER_RELEASED",
        "PRIVACY_TEST_STARTED", "PRIVACY_TEST_COMPLETED", "PRIVACY_TEST_FAILED",
    },
    "processing": {
        "INPUT_RECEIVED", "FACTS_EXTRACTED", "CARD_GENERATED", "CARD_STORED", "PROCESSING_FAILED",
    },
    "system": {
        "MESSAGE_SENT", "PRIVACY_TEST_STARTED", "PRIVACY_TEST_COMPLETED", "PRIVACY_TEST_FAILED",
    },
}


def sanitize_metadata(meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Ensure metadata contains only safe, non-identifying operational fields."""
    if not meta:
        return {}
    clean = {}
    for k, v in meta.items():
        k_lower = str(k).lower().strip()
        if k_lower in FORBIDDEN_KEYS or any(sub in k_lower for sub in ("text", "raw", "token", "phone", "email")):
            continue
        # Only allow primitive, bounded values
        if isinstance(v, (int, float, bool)):
            clean[k] = v
        elif isinstance(v, str):
            clean[k] = v[:64]  # bounded length, non-identifying tag
        elif isinstance(v, list):
            clean[k] = [x for x in v[:10] if isinstance(x, (int, float, bool, str))]
    return clean


def record_event(
    con: sqlite3.Connection,
    event_type: str,
    subsystem: str,
    status: str = "ok",
    duration_ms: Optional[int] = None,
    safe_metadata: Optional[Dict[str, Any]] = None,
    timestamp: Optional[float] = None,
) -> None:
    """Record a lifecycle event with bounded retention."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Invalid event_type: {event_type}. Must be one of {EVENT_TYPES}")

    ts = timestamp if timestamp is not None else time.time()
    clean_meta = sanitize_metadata(safe_metadata)
    meta_json = json.dumps(clean_meta, ensure_ascii=False)

    con.execute(
        "INSERT INTO privacy_events (timestamp, event_type, subsystem, status, duration_ms, safe_metadata_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (ts, event_type, subsystem, status, duration_ms, meta_json),
    )

    # Enforce bounded retention: keep maximum 500 events
    con.execute(
        "DELETE FROM privacy_events WHERE id NOT IN ("
        "SELECT id FROM privacy_events ORDER BY id DESC LIMIT ?)",
        (MAX_RETENTION,),
    )


def get_events(
    con: sqlite3.Connection,
    limit: int = 50,
    filter_category: str = "all",
) -> List[Dict[str, Any]]:
    """Retrieve recent events, optionally filtered by category."""
    limit = max(1, min(limit, 200))
    cat = (filter_category or "all").lower().strip()

    if cat in CATEGORY_MAP:
        allowed = CATEGORY_MAP[cat]
        q = ",".join("?" for _ in allowed)
        rows = con.execute(
            f"SELECT id, timestamp, event_type, subsystem, status, duration_ms, safe_metadata_json "
            f"FROM privacy_events WHERE event_type IN ({q}) ORDER BY id DESC LIMIT ?",
            (*allowed, limit),
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT id, timestamp, event_type, subsystem, status, duration_ms, safe_metadata_json "
            "FROM privacy_events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    out = []
    for r in rows:
        meta = json.loads(r["safe_metadata_json"]) if r["safe_metadata_json"] else {}
        ts = float(r["timestamp"])
        time_str = time.strftime("%H:%M:%S", time.localtime(ts))
        date_str = time.strftime("%d/%m/%Y", time.localtime(ts))
        out.append({
            "id": r["id"],
            "timestamp": ts,
            "time_str": time_str,
            "date_str": date_str,
            "event_type": r["event_type"],
            "subsystem": r["subsystem"],
            "status": r["status"],
            "duration_ms": r["duration_ms"],
            "metadata": meta,
        })
    return out
