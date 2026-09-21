"""Tests for the three new Unsigned features:
1. Privacy Health / Self-Test
2. Intervention Tracker
3. Privacy Event Log

Verifies privacy invariants, bounded retention, matched-window rates, and committee authentication.
"""
import os
import sys
import sqlite3
import tempfile
import time
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unsigned.api.app import app, DB_PATH, COMMITTEE_KEY
from unsigned.interventions.tracker import (
    init_interventions_table,
    create_intervention,
    get_interventions,
    get_intervention_by_id,
    update_intervention,
    compute_outcome,
)
from unsigned.pipeline.classify import BaselineClassifier
from unsigned.pipeline.narrate import LEXICON, foreign_tokens
from unsigned.pipeline.run import process
from unsigned.privacy.attacker import StyleAttacker
from unsigned.privacy.events import (
    record_event,
    get_events,
    sanitize_metadata,
    EVENT_TYPES,
    MAX_RETENTION,
)
from unsigned.privacy.health import (
    run_self_test,
    check_raw_persistence,
    check_student_word_release,
    check_closed_vocabulary,
    check_canary_isolation,
    check_sensitive_logging,
    check_external_network_isolation,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def test_db():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE IF NOT EXISTS cards (
        id INTEGER PRIMARY KEY, card_json TEXT NOT NULL, urgency TEXT, distress TEXT,
        release_at REAL NOT NULL, released INTEGER DEFAULT 0, day_bucket TEXT NOT NULL,
        week INTEGER NOT NULL, k_satisfied INTEGER, token_hash TEXT, status TEXT DEFAULT 'received',
        parent_id INTEGER, resolved_at REAL
    );
    CREATE TABLE IF NOT EXISTS audits (
        card_id INTEGER, audit_json TEXT NOT NULL, raw_discarded_after_ms INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS replies (card_id INTEGER, text TEXT NOT NULL, at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS privacy_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL NOT NULL, event_type TEXT NOT NULL,
        subsystem TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ok', duration_ms INTEGER,
        safe_metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """)
    init_interventions_table(con)
    yield con, path
    con.close()
    if os.path.exists(path):
        os.unlink(path)


# ----------------------------------------------------------------- 1. PRIVACY HEALTH
def test_self_test_endpoint_requires_auth(client):
    res = client.post("/api/privacy/self-test")
    assert res.status_code == 401

    res_auth = client.post("/api/privacy/self-test", headers={"X-Committee-Key": COMMITTEE_KEY})
    assert res_auth.status_code == 200
    data = res_auth.json()
    assert data["status"] in ("pass", "fail")
    assert "tests" in data
    assert len(data["tests"]) == 6
    assert data["summary"]["total"] == 6


def test_real_self_test_passes():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    c0_path = os.path.join(root, "models", "c0.joblib")
    a1_path = os.path.join(root, "models", "a1.joblib")
    clf = BaselineClassifier.load(c0_path)
    attacker = StyleAttacker.load(a1_path) if os.path.exists(a1_path) else None

    res = run_self_test(clf, attacker)
    assert res["status"] == "pass", f"Self-test failed: {res}"
    assert res["summary"]["passed"] == 6
    assert res["summary"]["failed"] == 0

    # Ensure no canary text or raw text leaked into details
    for t in res["tests"]:
        assert "CANARY_" not in t["details"]
        assert t["status"] == "pass"


def test_individual_privacy_health_checks():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    clf = BaselineClassifier.load(os.path.join(root, "models", "c0.joblib"))
    attacker = StyleAttacker.load(os.path.join(root, "models", "a1.joblib"))

    ok, msg = check_raw_persistence(clf, attacker)
    assert ok, f"check_raw_persistence failed: {msg}"

    ok, msg = check_student_word_release(clf, attacker)
    assert ok, f"check_student_word_release failed: {msg}"

    ok, msg = check_closed_vocabulary(clf, attacker)
    assert ok, f"check_closed_vocabulary failed: {msg}"

    ok, msg = check_canary_isolation(clf)
    assert ok, f"check_canary_isolation failed: {msg}"

    ok, msg = check_sensitive_logging()
    assert ok, f"check_sensitive_logging failed: {msg}"

    ok, msg = check_external_network_isolation()
    assert ok, f"check_external_network_isolation failed: {msg}"


# ----------------------------------------------------------------- 2. INTERVENTION TRACKER
def test_intervention_crud_and_schema(test_db):
    con, _ = test_db

    # Create intervention aligned to pattern (location_group, time_bucket, incident_type)
    i_id = create_intervention(
        con,
        location_group="hostel_b",
        time_bucket="night",
        incident_type="coercion_forced_acts",
        action="Increased night patrols by anti-ragging squad",
        action_type="patrol",
        assigned_unit="anti_ragging_squad",
        status="active",
        started_at=time.time() - 4 * 86400,  # 4 days ago
    )
    assert i_id > 0

    item = get_intervention_by_id(con, i_id)
    assert item is not None
    assert item["location_group"] == "hostel_b"
    assert item["time_bucket"] == "night"
    assert item["incident_type"] == "coercion_forced_acts"
    assert item["status"] == "active"

    # Verify no foreign keys exist to cards or students
    fk_list = con.execute("PRAGMA foreign_key_list(interventions)").fetchall()
    assert len(fk_list) == 0

    # Update status
    updated = update_intervention(con, i_id, status="completed")
    assert updated is True
    item2 = get_intervention_by_id(con, i_id)
    assert item2["status"] == "completed"


def test_intervention_outcome_matched_window(test_db):
    con, _ = test_db
    now = time.time()
    started_at = now - (4 * 86400)  # Started 4 days ago

    # Seed mock cards into test database:
    # Pre-window: [started_at - 4*86400, started_at) -> 8 matching cards
    # Post-window: [started_at, started_at + 4*86400] -> 3 matching cards
    import json
    card_matching = json.dumps({
        "location": "hostel_b_floor2",
        "time_bucket": "night",
        "types": ["coercion_forced_acts"],
    })
    card_unrelated = json.dumps({
        "location": "academic",
        "time_bucket": "morning",
        "types": ["verbal_abuse"],
    })

    # Insert 8 cards in pre-window
    for i in range(8):
        ts = started_at - (1 + (i % 3)) * 86400
        con.execute(
            "INSERT INTO cards(card_json,urgency,distress,release_at,released,day_bucket,week,k_satisfied,token_hash) "
            "VALUES (?,?,?,?,1,'2026-09-10',1,1,'tok')",
            (card_matching, "soon", "high", ts),
        )

    # Insert 3 cards in post-window
    for i in range(3):
        ts = started_at + (1 + (i % 2)) * 86400
        con.execute(
            "INSERT INTO cards(card_json,urgency,distress,release_at,released,day_bucket,week,k_satisfied,token_hash) "
            "VALUES (?,?,?,?,1,'2026-09-18',1,1,'tok')",
            (card_matching, "soon", "high", ts),
        )

    # Insert 5 unrelated cards
    for i in range(5):
        con.execute(
            "INSERT INTO cards(card_json,urgency,distress,release_at,released,day_bucket,week,k_satisfied,token_hash) "
            "VALUES (?,?,?,?,1,'2026-09-15',1,1,'tok')",
            (card_unrelated, "routine", "low", started_at - 86400),
        )

    intervention = {
        "location_group": "hostel_b",
        "time_bucket": "night",
        "incident_type": "coercion_forced_acts",
        "started_at": started_at,
    }

    outcome = compute_outcome(con, intervention, now=now)
    assert outcome["insufficient_data"] is False
    assert outcome["comparison_days"] == 4
    assert outcome["before_count"] == 8
    assert outcome["after_count"] == 3
    assert outcome["before_rate"] == 2.0   # 8 / 4
    assert outcome["after_rate"] == 0.75   # 3 / 4
    # (3 - 8) / 8 = -62.5%
    assert outcome["observed_change_pct"] == -62.5
    assert "BEFORE: 8 reports / 4 days" in outcome["display_summary"]
    assert "AFTER: 3 reports / 4 days" in outcome["display_summary"]


def test_intervention_insufficient_data_under_2_days(test_db):
    con, _ = test_db
    now = time.time()
    started_at = now - (1 * 86400)  # only 1 day ago

    intervention = {
        "location_group": "hostel_b",
        "time_bucket": "night",
        "incident_type": "coercion_forced_acts",
        "started_at": started_at,
    }
    outcome = compute_outcome(con, intervention, now=now)
    assert outcome["insufficient_data"] is True
    assert "minimum 2 days required" in outcome["message"]


def test_intervention_endpoints_require_auth(client):
    res = client.get("/api/interventions")
    assert res.status_code == 401

    res_auth = client.get("/api/interventions", headers={"X-Committee-Key": COMMITTEE_KEY})
    assert res_auth.status_code == 200
    assert "interventions" in res_auth.json()


# ----------------------------------------------------------------- 3. PRIVACY EVENT LOG
def test_event_sanitizer_rejects_sensitive_keys():
    dirty = {
        "acts_count": 2,
        "k_satisfied": True,
        "raw_text": "complaint text",
        "body": "student words",
        "token": "amber-bridge-cedar-delta-1234",
        "ip": "10.0.0.1",
        "email": "student@college.edu",
        "author": "A01",
    }
    clean = sanitize_metadata(dirty)
    assert "raw_text" not in clean
    assert "body" not in clean
    assert "token" not in clean
    assert "ip" not in clean
    assert "email" not in clean
    assert "author" not in clean
    assert clean["acts_count"] == 2
    assert clean["k_satisfied"] is True


def test_event_bounded_retention(test_db):
    con, _ = test_db

    # Insert 550 events
    for i in range(550):
        record_event(
            con,
            event_type="CARD_STORED",
            subsystem="storage",
            status="ok",
            safe_metadata={"count": i},
        )

    count = con.execute("SELECT COUNT(*) FROM privacy_events").fetchone()[0]
    assert count <= MAX_RETENTION
    assert count == 500


def test_pipeline_emits_raw_buffer_released():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    clf = BaselineClassifier.load(os.path.join(root, "models", "c0.joblib"))

    emitted = []

    def sink(event_type, subsystem, status, dur, meta):
        emitted.append((event_type, subsystem, status, dur, meta))

    text = "seniors made us stand for 3 hours in hostel b corridor at night"
    res = process(text, clf, None, [], k=3, event_sink=sink)

    event_names = [e[0] for e in emitted]
    assert "FACTS_EXTRACTED" in event_names
    assert "GENERALIZATION_APPLIED" in event_names
    assert "CARD_GENERATED" in event_names
    assert "CARD_VALIDATED" in event_names
    assert "RAW_BUFFER_RELEASED" in event_names

    # Check that RAW_BUFFER_RELEASED emitted duration_ms
    raw_rel = [e for e in emitted if e[0] == "RAW_BUFFER_RELEASED"][0]
    assert raw_rel[3] is not None and raw_rel[3] >= 0
    assert raw_rel[4] == {}  # Zero text in metadata


def test_privacy_events_api(client):
    # Unauthenticated
    res = client.get("/api/privacy/events")
    assert res.status_code == 401

    # Authenticated
    res_auth = client.get("/api/privacy/events", headers={"X-Committee-Key": COMMITTEE_KEY})
    assert res_auth.status_code == 200
    data = res_auth.json()
    assert "events" in data

    # Verify no raw text in any event metadata
    for ev in data["events"]:
        assert "text" not in str(ev["metadata"]).lower()
        assert "token" not in str(ev["metadata"]).lower()
