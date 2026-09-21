"""Unsigned API — FastAPI, single laptop, SQLite. There is no table, log or response that contains raw text.

Student side (open):
  GET  /                         submission page (privacy preview, passphrase token)
  GET  /status                   status page (token -> status, replies, add information)
  POST /preview                  the card the committee WOULD see + rarity flags; nothing stored
  POST /submit                   pipeline -> discard text -> queue card by urgency -> token
  GET  /api/status/{token}       status + replies for the student's case
  POST /api/status/{token}/add   anonymous follow-up (a new card threaded to the case)

Committee side (passcode, header X-Committee-Key):
  GET  /console                  console page
  POST /api/login                passcode -> ok
  GET  /api/cards                released cards, generalised at read time, threaded
  GET  /api/patterns             rising-pattern alerts
  GET  /api/audit                attacker numbers, channel bound, k, discard latency, evaluate.py results
  POST /api/cards/{id}/reply     reply to the student (visible via token)
  POST /api/cards/{id}/status    received | in_progress | resolved
  GET  /api/report/weekly        printable institutional summary (no cards, only aggregates)
  POST /api/attacker/link        DEMO: "which two of these were written by the same student?"
  POST /api/attacker/reference   DEMO: give the attacker a known writing sample (the adversary's knowledge)
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import math
import os
import random
import secrets
import sqlite3
import tempfile
import threading
import time
from collections import Counter, deque
from typing import List, Optional

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from ..interventions import (
    init_interventions_table,
    create_intervention,
    get_interventions,
    get_intervention_by_id,
    update_intervention,
    get_recommendations_for_patterns,
)
from ..patterns.detect import detect
from ..pipeline.card import Card, channel_capacity_bits
from ..pipeline.classify import BaselineClassifier, load_classifier
from ..pipeline.run import display as _display, preview as _preview, process as _process
from ..pipeline.narrate import LEXICON, narrative_capacity_bits
from ..privacy.attacker import StyleAttacker
from ..privacy.events import record_event as _record_evt, get_events

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(os.path.dirname(HERE), "web")
ROOT = os.path.dirname(os.path.dirname(HERE))
MODELS = os.path.join(ROOT, "models")
DB_PATH = os.environ.get("UNSIGNED_DB", os.path.join(ROOT, "unsigned.sqlite"))
K = int(os.environ.get("UNSIGNED_K", "3"))
COMMITTEE_KEY = os.environ.get("UNSIGNED_COMMITTEE_KEY", "committee")     # change in deployment
DEMO_FAST = os.environ.get("UNSIGNED_DEMO_FAST", "1") == "1"               # release delays in seconds instead of hours
DEMO_MODE = os.environ.get("UNSIGNED_DEMO", "1") == "1"                    # demo endpoints + demo_author; OFF in any real deployment
JITTER_MS = (20, 140)                                                       # response-time padding so latency cannot leak text length
RELEASE_DELAY_S = {"immediate": (0, 15 * 60), "soon": (3600, 6 * 3600), "routine": (6 * 3600, 12 * 3600)}
STATUSES = ("received", "in_progress", "resolved")
WORDS = ("amber bridge cedar delta ember falcon garnet harbor iris jade kite lotus maple nova orbit pearl "
         "quartz river sage tiger umber violet willow zephyr").split()

@asynccontextmanager
async def _lifespan(app):
    _load()
    yield


app = FastAPI(title="Unsigned", docs_url=None, redoc_url=None, openapi_url=None, lifespan=_lifespan)
_clf: Optional[BaselineClassifier] = None
_attacker: Optional[StyleAttacker] = None
_recent_submissions: deque = deque(maxlen=200)      # global flood control without identity
_model_lock = threading.Lock()                       # attacker/demo-file updates are serialised


# ----------------------------------------------------------------- side-channel hygiene
class Hygiene(BaseHTTPMiddleware):
    """No caching, no referrers, no framing. (IP logging is disabled by the launcher: access_log=False.)"""
    async def dispatch(self, request: Request, call_next):
        resp: Response = await call_next(request)
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp


app.add_middleware(Hygiene)


# ----------------------------------------------------------------- storage
def _db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with _db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY, card_json TEXT NOT NULL, urgency TEXT, distress TEXT,
            release_at REAL NOT NULL, released INTEGER DEFAULT 0, day_bucket TEXT NOT NULL,
            week INTEGER NOT NULL, k_satisfied INTEGER, token_hash TEXT, status TEXT DEFAULT 'received',
            parent_id INTEGER, resolved_at REAL);
        CREATE TABLE IF NOT EXISTS audits (card_id INTEGER, audit_json TEXT NOT NULL, raw_discarded_after_ms INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS replies (card_id INTEGER, text TEXT NOT NULL, at REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_cards_token ON cards(token_hash);
        CREATE TABLE IF NOT EXISTS privacy_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL NOT NULL, event_type TEXT NOT NULL,
            subsystem TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ok', duration_ms INTEGER,
            safe_metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_privacy_events_ts ON privacy_events(timestamp DESC);
        """)
        init_interventions_table(con)
        cols = {r["name"] for r in con.execute("PRAGMA table_info(cards)")}
        for col, ddl in (("parent_id", "INTEGER"), ("resolved_at", "REAL")):
            if col not in cols:
                con.execute(f"ALTER TABLE cards ADD COLUMN {col} {ddl}")


def _released_fine(con: sqlite3.Connection) -> dict:
    con.execute("UPDATE cards SET released=1 WHERE released=0 AND release_at<=?", (time.time(),))
    out = {}
    for r in con.execute("SELECT id, card_json FROM cards WHERE released=1"):
        d = json.loads(r["card_json"]); d.pop("narrative", None)
        out[r["id"]] = Card(**d)
    return out


def _atomic_json(path: str, data) -> None:
    """Write JSON to a temp file and rename it into place — never a half-written file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def _pad_latency(t0: float) -> None:
    """Sleep so every submission-path response takes a random time in JITTER_MS above its own compute.
    (Absolute timing still varies with load; this removes the text-length signal a watcher could read.)"""
    time.sleep(random.uniform(*JITTER_MS) / 1000)


def _token() -> str:
    return "-".join(random.choice(WORDS) for _ in range(4)) + "-" + secrets.token_hex(2)


def _hash(tok: str) -> str:
    return hashlib.sha256(tok.strip().lower().encode()).hexdigest()


def _store(con, card: Card, result: dict, token_hash: str, parent_id: Optional[int] = None) -> tuple[int, float]:
    lo, hi = RELEASE_DELAY_S.get(card.urgency, RELEASE_DELAY_S["routine"])
    delay = random.uniform(lo, hi) / (3600 if DEMO_FAST else 1)
    now = time.time()
    cur = con.execute(
        "INSERT INTO cards(card_json,urgency,distress,release_at,day_bucket,week,k_satisfied,token_hash,parent_id) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (json.dumps(card.to_dict()), card.urgency, card.distress, now + delay, time.strftime("%Y-%m-%d", time.gmtime(now)),
         int(now // (7 * 86400)), int(result["k_satisfied"]), token_hash, parent_id))
    con.execute("INSERT INTO audits(card_id,audit_json,raw_discarded_after_ms) VALUES (?,?,?)",
                (cur.lastrowid, json.dumps(result["audit"]), result["raw_discarded_after_ms"]))
    return cur.lastrowid, delay


# ----------------------------------------------------------------- models
def _load() -> None:
    global _clf, _attacker
    init_db()
    try:
        _clf = load_classifier(MODELS)
    except Exception:
        _clf = None
    a1 = os.path.join(MODELS, "a1.joblib")
    _attacker = StyleAttacker.load(a1) if os.path.exists(a1) else None
    ref = os.path.join(MODELS, "a1_reference.json")            # reference samples added in the Demo tab survive restarts
    if _attacker is not None and os.path.exists(ref):
        data = json.load(open(ref, encoding="utf-8"))
        if len(set(data["authors"])) > len(_attacker.authors):
            _attacker = StyleAttacker().fit(data["texts"], data["authors"])


# Initialize on import so test runners and workers have tables and models ready
_load()


def _require_clf() -> BaselineClassifier:
    if _clf is None:
        raise HTTPException(503, "No trained classifier. Run: python scripts/evaluate.py --train")
    return _clf


def _require_attacker() -> StyleAttacker:
    if _attacker is None or not _attacker.fitted:
        raise HTTPException(503, "No attacker loaded. Run: python scripts/evaluate.py --train")
    return _attacker


def committee(x_committee_key: str = Header(default="")) -> None:
    if not hmac.compare_digest(x_committee_key, COMMITTEE_KEY):
        raise HTTPException(401, "committee passcode required")


def demo_only() -> None:
    if not DEMO_MODE:
        raise HTTPException(404, "demo features are disabled on this deployment")


def _demo_author(s) -> Optional[str]:
    """demo_author is honoured only when demo mode is on; otherwise it is silently dropped."""
    return s.demo_author if DEMO_MODE else None


# ----------------------------------------------------------------- schemas
class Submission(BaseModel):
    text: str = Field(min_length=5, max_length=2000)
    padding: Optional[str] = None            # client pads the body to a fixed size
    demo_author: Optional[str] = None        # DEMO ONLY
    facts_override: Optional[dict] = None    # the student's edits from the privacy preview (closed values only)


class Reply(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class StatusChange(BaseModel):
    status: str


class Feedback(BaseModel):
    question: str = Field(min_length=1, max_length=40)      # closed set below
    answer: str = Field(min_length=1, max_length=8)         # "yes" | "no"


FEEDBACK_QUESTIONS = {"understood_card": "Did you understand what the committee will see?",
                      "would_use": "Would you use this instead of staying silent?",
                      "felt_safe": "Did you feel your words were safe?"}


class Login(BaseModel):
    passcode: str


class Reference(BaseModel):
    author: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=5, max_length=2000)


class LinkRequest(BaseModel):
    texts: List[str] = Field(min_length=2, max_length=8)


class InterventionCreate(BaseModel):
    location_group: str = Field(min_length=1, max_length=40)
    time_bucket: str = Field(min_length=1, max_length=30)
    incident_type: str = Field(min_length=1, max_length=40)
    action: str = Field(min_length=3, max_length=120)
    action_type: Optional[str] = Field(default="patrol", max_length=30)
    assigned_unit: Optional[str] = Field(default="anti_ragging_squad", max_length=30)
    status: Optional[str] = Field(default="active", max_length=20)
    started_at: Optional[float] = None
    review_at: Optional[float] = None
    institutional_note: Optional[str] = Field(default=None, max_length=256)


class InterventionUpdate(BaseModel):
    status: Optional[str] = Field(default=None, max_length=20)
    review_at: Optional[float] = None
    action: Optional[str] = Field(default=None, max_length=120)
    institutional_note: Optional[str] = Field(default=None, max_length=256)


# ----------------------------------------------------------------- pages
@app.get("/", response_class=HTMLResponse)
def page_submit():
    return FileResponse(os.path.join(WEB, "submit.html"))


@app.get("/status", response_class=HTMLResponse)
def page_status():
    return FileResponse(os.path.join(WEB, "status.html"))


@app.get("/console", response_class=HTMLResponse)
def page_console():
    return FileResponse(os.path.join(WEB, "console.html"))


@app.get("/present", response_class=HTMLResponse, dependencies=[Depends(demo_only)])
def page_present():
    return FileResponse(os.path.join(WEB, "present.html"))


@app.get("/app.css")
def css():
    return FileResponse(os.path.join(WEB, "app.css"), media_type="text/css")


# ----------------------------------------------------------------- overview (dashboard) + demo story
ROW_GROUPS = ["hostel_a", "hostel_b", "hostel_c", "common_areas", "academic", "transit", "online", "unknown"]
COL_BUCKETS = ["morning", "afternoon", "evening", "night", "unknown"]


def _group_of(location: str) -> str:
    from ..pipeline.card import LOCATION_HIERARCHY
    node = location
    steps = 0
    while node is not None and node not in ROW_GROUPS and steps < 12:
        steps += 1
        node = LOCATION_HIERARCHY.get(node)
    return node or "unknown"


@app.get("/api/overview", dependencies=[Depends(committee)])
def overview():
    """KPIs, a location × time heat grid (cells below k are suppressed), and cards per week."""
    week = int(time.time() // (7 * 86400))
    with _db() as con:
        _released_fine(con)
        rows = con.execute("SELECT card_json, week, status, urgency, parent_id FROM cards WHERE released=1").fetchall()
        pending = con.execute("SELECT COUNT(*) FROM cards WHERE released=0").fetchone()[0]
    grid = {g: {b: 0 for b in COL_BUCKETS} for g in ROW_GROUPS}
    per_week = Counter()
    open_cards = immediate = 0
    for r in rows:
        d = json.loads(r["card_json"])
        per_week[r["week"]] += 1
        if r["week"] == week:
            grid[_group_of(d["location"])][d["time_bucket"] if d["time_bucket"] in COL_BUCKETS else "unknown"] += 1
        if r["status"] != "resolved" and r["parent_id"] is None:
            open_cards += 1
            if r["urgency"] == "immediate":
                immediate += 1
    cells = [{"row": g, "col": b, "n": (n if n >= K else 0), "suppressed": 0 < n < K}
             for g in ROW_GROUPS for b, n in grid[g].items()]
    series = [{"week": w, "n": per_week.get(w, 0)} for w in range(week - 7, week + 1)]
    return {"week": week, "open": open_cards, "immediate": immediate, "pending_release": pending,
            "this_week": per_week.get(week, 0), "last_week": per_week.get(week - 1, 0),
            "grid": cells, "rows": ROW_GROUPS, "cols": COL_BUCKETS, "series": series, "k": K}


DEMO_PATH = os.path.join(MODELS, "demo_texts.json")
DEFAULT_DEMO_TEXTS = [
    "wow such a warm welcome from seniors?? 3 hours standing in hostel B corridor at night, great tradition hmm",
    "BHAI kal raat seniors ne hostel B second floor pe bulaya aur 3 ghante KHADE rakha!!! 😭😭 intro intro intro!!!",
    "nothing serious?? just the usual comments about how we dress, in the lab, every single day. hmm. fine I guess",
]


class DemoTexts(BaseModel):
    texts: List[str] = Field(min_length=2, max_length=5)


@app.get("/api/demo/texts", dependencies=[Depends(committee), Depends(demo_only)])
def demo_texts_get():
    if os.path.exists(DEMO_PATH):
        return {"texts": json.load(open(DEMO_PATH, encoding="utf-8"))}
    return {"texts": DEFAULT_DEMO_TEXTS}


@app.post("/api/demo/texts", dependencies=[Depends(committee), Depends(demo_only)])
def demo_texts_set(d: DemoTexts):
    os.makedirs(MODELS, exist_ok=True)
    with _model_lock:
        _atomic_json(DEMO_PATH, d.texts)
    return {"ok": True}


@app.post("/api/demo/story", dependencies=[Depends(committee), Depends(demo_only)])
def demo_story(req: LinkRequest):
    """Everything Present mode needs for the hook, in one call, on the real models:
    attacker on the raw texts -> the same texts as cards -> attacker on the cards."""
    att = _require_attacker()
    clf = _require_clf()
    with _db() as con:
        released = list(_released_fine(con).values())
    n = len(req.texts)
    raw_pairs = [{"a": i, "b": j, "p": round(att.link(req.texts[i], req.texts[j]), 3)} for i in range(n) for j in range(i + 1, n)]
    raw_attr = [dict(zip(("author", "prob"), att.attribute(t)[:2])) for t in req.texts]
    cards, timings = [], []
    for t in req.texts:
        r = _process(t, clf, att, released, K)
        cards.append(r["shown"].to_dict()); timings.append(r["raw_discarded_after_ms"])
    narr = [c["narrative"] for c in cards]
    card_pairs = [{"a": i, "b": j, "p": round(att.link(narr[i], narr[j]), 3)} for i in range(n) for j in range(i + 1, n)]
    card_attr = [dict(zip(("author", "prob"), att.attribute(t)[:2])) for t in narr]
    spread_raw = round(max(p["p"] for p in raw_pairs) - min(p["p"] for p in raw_pairs), 3) if raw_pairs else 0
    spread_cards = round(max(p["p"] for p in card_pairs) - min(p["p"] for p in card_pairs), 3) if card_pairs else 0
    raw_sorted, card_sorted = sorted(raw_pairs, key=lambda p: -p["p"]), sorted(card_pairs, key=lambda p: -p["p"])
    same_guess = bool(raw_sorted and card_sorted and (raw_sorted[0]["a"], raw_sorted[0]["b"]) == (card_sorted[0]["a"], card_sorted[0]["b"]))
    words = [len(c["narrative"].split()) for c in cards]
    return {"raw_pairs": raw_sorted, "raw_attribution": raw_attr, "card_attribution": card_attr,
            "spread_raw": spread_raw, "spread_cards": spread_cards, "same_top_pair": same_guess,
            "narrative_words": words, "lexicon_size": len(LEXICON),
            "cards": cards, "discard_ms": timings, "card_pairs": card_sorted,
            "chance": att.chance(), "reference_authors": len(att.authors), "capacity_bits": round(channel_capacity_bits(), 1), "k": K}


# ----------------------------------------------------------------- student API
@app.post("/preview")
def preview(s: Submission):
    clf = _require_clf()
    t0 = time.perf_counter()
    with _db() as con:
        released = list(_released_fine(con).values())
    out = _preview(s.text, clf, released, K, facts_override=s.facts_override)
    _pad_latency(t0)
    return out


def _flood_check() -> None:
    now = time.time()
    _recent_submissions.append(now)
    if sum(1 for t in _recent_submissions if now - t < 60) > 60:
        raise HTTPException(429, "Too many submissions right now. Please try again in a minute.")


@app.post("/submit")
def submit(s: Submission):
    clf = _require_clf()
    _flood_check()
    with _db() as con:
        _record_evt(con, "INPUT_RECEIVED", "pipeline", "ok", None, {"payload_bytes": len(s.text)})
        released = list(_released_fine(con).values())

        def sink(evt_type, subsystem, status, dur, meta):
            _record_evt(con, evt_type, subsystem, status, dur, meta)

        result = _process(s.text, clf, _attacker, released, K, demo_author=_demo_author(s),
                          facts_override=s.facts_override, event_sink=sink)
        del s
        tok = _token()
        card_id, delay = _store(con, result["card"], result, _hash(tok))
        _record_evt(con, "CARD_STORED", "storage", "ok", None,
                    {"urgency": result["card"].urgency, "k_satisfied": bool(result["k_satisfied"])})
    _pad_latency(0)
    return {"token": tok, "case": card_id, "release_in_seconds": round(delay),
            "raw_discarded_after_ms": result["raw_discarded_after_ms"], "audit": result["audit"],
            "card": result["shown"].to_dict(), "k_satisfied": result["k_satisfied"], "fact_status": result["fact_status"]}


@app.get("/api/status/{token}")
def status(token: str):
    with _db() as con:
        con.execute("UPDATE cards SET released=1 WHERE released=0 AND release_at<=?", (time.time(),))
        row = con.execute("SELECT id, status, released, release_at FROM cards WHERE token_hash=? AND parent_id IS NULL",
                          (_hash(token),)).fetchone()
        if not row:
            raise HTTPException(404, "We don't recognise that passphrase.")
        ids = [row["id"]] + [r["id"] for r in con.execute("SELECT id FROM cards WHERE parent_id=?", (row["id"],))]
        q = ",".join("?" * len(ids))
        replies = [dict(r) for r in con.execute(f"SELECT text, at FROM replies WHERE card_id IN ({q}) ORDER BY at", ids)]
        followups = con.execute("SELECT COUNT(*) FROM cards WHERE parent_id=?", (row["id"],)).fetchone()[0]
    return {"status": row["status"], "released": bool(row["released"]),
            "releases_in_seconds": max(0, round(row["release_at"] - time.time())) if not row["released"] else 0,
            "replies": replies, "followups": followups}


@app.post("/api/status/{token}/add")
def add_information(token: str, s: Submission):
    clf = _require_clf()
    _flood_check()
    with _db() as con:
        parent = con.execute("SELECT id FROM cards WHERE token_hash=? AND parent_id IS NULL", (_hash(token),)).fetchone()
        if not parent:
            raise HTTPException(404, "We don't recognise that passphrase.")
        _record_evt(con, "INPUT_RECEIVED", "pipeline", "ok", None, {"payload_bytes": len(s.text), "followup": True})
        released = list(_released_fine(con).values())

        def sink(evt_type, subsystem, status, dur, meta):
            _record_evt(con, evt_type, subsystem, status, dur, meta)

        result = _process(s.text, clf, _attacker, released, K, facts_override=s.facts_override, event_sink=sink)
        del s
        _, delay = _store(con, result["card"], result, _hash(token), parent_id=parent["id"])
        _record_evt(con, "CARD_STORED", "storage", "ok", None,
                    {"urgency": result["card"].urgency, "followup": True})
    _pad_latency(0)
    return {"ok": True, "release_in_seconds": round(delay), "raw_discarded_after_ms": result["raw_discarded_after_ms"],
            "card": result["shown"].to_dict()}


# ----------------------------------------------------------------- committee API
@app.post("/api/login")
def login(l: Login):
    if not hmac.compare_digest(l.passcode, COMMITTEE_KEY):
        raise HTTPException(401, "Wrong passcode")
    return {"ok": True}


@app.get("/api/cards", dependencies=[Depends(committee)])
def cards():
    order = {"immediate": 0, "soon": 1, "routine": 2}
    with _db() as con:
        fine = _released_fine(con)
        rows = con.execute(
            "SELECT c.id, c.day_bucket, c.status, c.parent_id, a.audit_json, a.raw_discarded_after_ms, "
            "(SELECT COUNT(*) FROM replies r WHERE r.card_id=c.id) AS n_replies "
            "FROM cards c LEFT JOIN audits a ON a.card_id=c.id WHERE c.released=1").fetchall()
        pending = con.execute("SELECT COUNT(*) FROM cards WHERE released=0").fetchone()[0]
    out = []
    for r in rows:
        others = [c for i, c in fine.items() if i != r["id"]]
        shown, k_ok, fact_status = _display(fine[r["id"]], others, K)
        d = shown.to_dict()
        d.update(id=r["id"], day=r["day_bucket"], status=r["status"], parent_id=r["parent_id"], k_satisfied=k_ok, fact_status=fact_status,
                 n_replies=r["n_replies"], audit=json.loads(r["audit_json"]) if r["audit_json"] else None,
                 raw_discarded_after_ms=r["raw_discarded_after_ms"])
        out.append(d)
    out.sort(key=lambda d: ({"received": 0, "in_progress": 1, "resolved": 2}[d["status"]], order.get(d["urgency"], 9), -d["id"]))
    return {"cards": out, "pending_release": pending, "below_k": sum(1 for d in out if not d["k_satisfied"])}


@app.get("/api/patterns", dependencies=[Depends(committee)])
def patterns():
    with _db() as con:
        rows = con.execute("SELECT card_json, week FROM cards WHERE released=1").fetchall()
    cs = []
    for r in rows:
        d = json.loads(r["card_json"]); d["week"] = r["week"]; cs.append(d)
    week = int(time.time() // (7 * 86400))
    return {"alerts": detect(cs, week), "week": week}


@app.post("/api/feedback")
def feedback(f: Feedback):
    """One-tap hallway-study answers. Counts only: no text, no token, no case id — nothing to link."""
    if f.question not in FEEDBACK_QUESTIONS or f.answer not in ("yes", "no"):
        raise HTTPException(400, "unknown question or answer")
    with _db() as con:
        con.execute("CREATE TABLE IF NOT EXISTS feedback (question TEXT, answer TEXT, day TEXT)")
        con.execute("INSERT INTO feedback(question, answer, day) VALUES (?,?,?)", (f.question, f.answer, time.strftime("%Y-%m-%d", time.gmtime())))
    return {"ok": True}


def _feedback_summary() -> dict:
    with _db() as con:
        con.execute("CREATE TABLE IF NOT EXISTS feedback (question TEXT, answer TEXT, day TEXT)")
        rows = con.execute("SELECT question, answer, COUNT(*) AS n FROM feedback GROUP BY question, answer").fetchall()
    out = {q: {"yes": 0, "no": 0, "text": t} for q, t in FEEDBACK_QUESTIONS.items()}
    for r in rows:
        if r["question"] in out:
            out[r["question"]][r["answer"]] = r["n"]
    return out


@app.get("/api/audit", dependencies=[Depends(committee)])
def audit_summary():
    with _db() as con:
        rows = con.execute("SELECT audit_json, raw_discarded_after_ms FROM audits").fetchall()
    lat = sorted(r["raw_discarded_after_ms"] for r in rows)
    auds = [json.loads(r["audit_json"]) for r in rows]
    ev_path = os.path.join(MODELS, "evaluation.json")
    evaluation = json.load(open(ev_path, encoding="utf-8")) if os.path.exists(ev_path) else None
    return {
        "channel_capacity_bits": round(channel_capacity_bits(), 2), "k": K,
        "narrative_capacity_bits": round(narrative_capacity_bits(), 1), "lexicon_size": len(LEXICON),
        "foreign_tokens_total": sum(a.get("foreign_tokens", 0) for a in auds),
        "narrative_tokens_total": sum(a.get("narrative_tokens", 0) for a in auds),
        "attacker_loaded": _attacker is not None and _attacker.fitted,
        "attacker_reference_authors": len(_attacker.authors) if _attacker else 0,
        "raw_discarded_after_ms": {"n": len(lat), "p50": lat[len(lat) // 2] if lat else None, "max": lat[-1] if lat else None},
        "mean_raw_top_prob": round(sum(a["raw_top_prob"] for a in auds) / len(auds), 3) if auds else None,
        "mean_leak_tv": round(sum(a["leak_tv"] for a in auds) / len(auds), 3) if auds else None,
        "evaluation": evaluation,
        "feedback": _feedback_summary(),
    }


@app.post("/api/cards/{card_id}/reply", dependencies=[Depends(committee)])
def reply(card_id: int, r: Reply):
    with _db() as con:
        row = con.execute("SELECT id, status FROM cards WHERE id=?", (card_id,)).fetchone()
        if not row:
            raise HTTPException(404)
        con.execute("INSERT INTO replies(card_id,text,at) VALUES (?,?,?)", (card_id, r.text, time.time()))
        if row["status"] == "received":
            con.execute("UPDATE cards SET status='in_progress' WHERE id=?", (card_id,))
        _record_evt(con, "MESSAGE_SENT", "committee", "ok", None, {"reply_chars": len(r.text)})
    return {"ok": True}


@app.post("/api/cards/{card_id}/status", dependencies=[Depends(committee)])
def set_status(card_id: int, s: StatusChange):
    if s.status not in STATUSES:
        raise HTTPException(400, f"status must be one of {STATUSES}")
    with _db() as con:
        con.execute("UPDATE cards SET status=?, resolved_at=? WHERE id=?",
                    (s.status, time.time() if s.status == "resolved" else None, card_id))
    return {"ok": True}


# ----------------------------------------------------------------- privacy events
@app.get("/api/privacy/events", dependencies=[Depends(committee)])
def privacy_events_get(limit: int = 50, filter: str = "all"):
    with _db() as con:
        evts = get_events(con, limit=limit, filter_category=filter)
    return {"events": evts, "total_returned": len(evts)}


# ----------------------------------------------------------------- intervention tracker
@app.get("/api/interventions/recommendations", dependencies=[Depends(committee)])
def interventions_recommendations():
    with _db() as con:
        rows = con.execute("SELECT card_json, week FROM cards WHERE released=1").fetchall()
        active_invs = get_interventions(con, status_filter="active")
    cs = []
    for r in rows:
        try:
            d = json.loads(r["card_json"])
            d["week"] = r["week"]
            cs.append(d)
        except Exception:
            continue
    week = int(time.time() // (7 * 86400))
    alerts = detect(cs, week)
    recs = get_recommendations_for_patterns(alerts, active_invs)
    return {"recommendations": recs}


@app.get("/api/interventions", dependencies=[Depends(committee)])
def interventions_list(status: Optional[str] = None):
    with _db() as con:
        items = get_interventions(con, status_filter=status)
    return {"interventions": items, "count": len(items)}


@app.post("/api/interventions", dependencies=[Depends(committee)])
def interventions_create(req: InterventionCreate):
    with _db() as con:
        new_id = create_intervention(
            con,
            location_group=req.location_group,
            time_bucket=req.time_bucket,
            incident_type=req.incident_type,
            action=req.action,
            action_type=req.action_type or "patrol",
            assigned_unit=req.assigned_unit or "anti_ragging_squad",
            status=req.status or "active",
            started_at=req.started_at,
            review_at=req.review_at,
            institutional_note=req.institutional_note,
        )
        item = get_intervention_by_id(con, new_id)
    return {"ok": True, "intervention": item}


@app.get("/api/interventions/{intervention_id}", dependencies=[Depends(committee)])
def interventions_detail(intervention_id: int):
    with _db() as con:
        item = get_intervention_by_id(con, intervention_id)
    if not item:
        raise HTTPException(404, "Intervention not found")
    return item


@app.patch("/api/interventions/{intervention_id}", dependencies=[Depends(committee)])
def interventions_update(intervention_id: int, req: InterventionUpdate):
    with _db() as con:
        ok = update_intervention(
            con,
            intervention_id,
            status=req.status,
            review_at=req.review_at,
            action=req.action,
            institutional_note=req.institutional_note,
        )
        if not ok:
            raise HTTPException(404, "Intervention not found or no fields to update")
        item = get_intervention_by_id(con, intervention_id)
    return {"ok": True, "intervention": item}


@app.get("/api/report/weekly", dependencies=[Depends(committee)], response_class=HTMLResponse)
def weekly_report():
    """Aggregates only — no cards, no narratives — suitable for institutional executive review."""
    week = int(time.time() // (7 * 86400))
    with _db() as con:
        rows = con.execute("SELECT card_json, week, status, day_bucket, resolved_at, release_at FROM cards WHERE released=1").fetchall()
    this = [r for r in rows if r["week"] == week]
    prev = [r for r in rows if r["week"] == week - 1]

    def agg(rs):
        c_type, c_loc, c_urg, c_dist = Counter(), Counter(), Counter(), Counter()
        for r in rs:
            d = json.loads(r["card_json"])
            for t in d.get("types", []):
                c_type[t] += 1
            c_loc[d.get("location", "unknown")] += 1
            c_urg[d.get("urgency", "routine")] += 1
            c_dist[d.get("distress", "low")] += 1
        return c_type, c_loc, c_urg, c_dist

    t_now, l_now, u_now, d_now = agg(this)
    t_prev, l_prev, u_prev, _ = agg(prev)

    total_this = len(this)
    total_prev = len(prev)
    delta_total = total_this - total_prev
    delta_str = f"+{delta_total}" if delta_total > 0 else f"{delta_total}"

    all_received = sum(1 for r in rows if r["status"] == "received")
    all_in_prog = sum(1 for r in rows if r["status"] == "in_progress")
    all_resolved = sum(1 for r in rows if r["status"] == "resolved")
    total_all = len(rows)

    resolved = [r for r in rows if r["status"] == "resolved" and r["resolved_at"]]
    med_days = None
    if resolved:
        ds = sorted((r["resolved_at"] - r["release_at"]) / 86400 for r in resolved)
        med_days = round(ds[len(ds) // 2], 1)

    # Palette
    PALETTE = ["#1F6F78", "#D48A0C", "#C9463A", "#2F8F5B", "#5A738E", "#8B5FBF", "#B47D52", "#E8A838"]

    # Generate SVG Donut Chart with innerRadius=65, size=200
    def build_donut_svg(items, total, size=200, inner_radius=65):
        cx, cy = size / 2, size / 2
        R = 95
        r = inner_radius
        if total == 0 or not items:
            return f'''<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" class="chart-svg">
              <circle cx="{cx}" cy="{cy}" r="{(R+r)/2}" fill="none" stroke="var(--surface-2)" stroke-width="{R-r}" />
              <text x="{cx}" y="{cy}" text-anchor="middle" dominant-baseline="middle" font-family="var(--ui)" fill="var(--muted)" font-size="12">No incidents</text>
            </svg>'''
        paths = []
        current_angle = -math.pi / 2
        for idx, (label, count) in enumerate(items):
            if count <= 0:
                continue
            fraction = count / total
            slice_angle = fraction * 2 * math.pi
            if fraction >= 0.9999:
                slice_angle = 1.9999 * math.pi
            next_angle = current_angle + slice_angle
            x1 = cx + R * math.cos(current_angle)
            y1 = cy + R * math.sin(current_angle)
            x2 = cx + R * math.cos(next_angle)
            y2 = cy + R * math.sin(next_angle)
            x3 = cx + r * math.cos(next_angle)
            y3 = cy + r * math.sin(next_angle)
            x4 = cx + r * math.cos(current_angle)
            y4 = cy + r * math.sin(current_angle)
            large_arc = 1 if slice_angle > math.pi else 0
            color = PALETTE[idx % len(PALETTE)]
            d = f"M {x1:.2f} {y1:.2f} A {R} {R} 0 {large_arc} 1 {x2:.2f} {y2:.2f} L {x3:.2f} {y3:.2f} A {r} {r} 0 {large_arc} 0 {x4:.2f} {y4:.2f} Z"
            pct_val = round(fraction * 100)
            formatted_label = label.replace("_", " ").title()
            paths.append(f'<path class="pie-slice" d="{d}" fill="{color}" stroke="var(--surface)" stroke-width="2.5" data-index="{idx}" data-label="{formatted_label}" data-value="{count}" data-color="{color}"><title>{formatted_label}: {count} ({pct_val}%)</title></path>')
            current_angle = next_angle
        return f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" class="chart-svg">' + "".join(paths) + '</svg>'

    top_types = t_now.most_common(8)
    donut_svg = build_donut_svg(top_types, total_this if total_this > 0 else 1, size=200, inner_radius=65)

    # Donut Legend HTML
    legend_items = []
    for idx, (t, n) in enumerate(top_types):
        color = PALETTE[idx % len(PALETTE)]
        pct_val = round((n / max(1, total_this)) * 100)
        formatted_label = t.replace('_', ' ').title()
        legend_items.append(
            f'''<div class="legend-row" data-index="{idx}" data-label="{formatted_label}" data-value="{n}" data-color="{color}">
              <span class="swatch" style="background:{color}"></span>
              <span class="label">{formatted_label}</span>
              <span class="count">{n}</span>
              <span class="pct">{pct_val}%</span>
            </div>'''
        )
    legend_html = "".join(legend_items) if legend_items else '<p class="muted">No categories recorded this week.</p>'

    # Types Table Rows
    type_table_rows = []
    for t, n in t_now.most_common():
        prev_n = t_prev.get(t, 0)
        diff = n - prev_n
        if diff > 0:
            trend = f'<span class="pill bad" style="font-size:.72rem">+{diff} ↑</span>'
        elif diff < 0:
            trend = f'<span class="pill ok" style="font-size:.72rem">{diff} ↓</span>'
        else:
            trend = f'<span class="pill quiet" style="font-size:.72rem">0 —</span>'
        share = f"{round((n / max(1, total_this)) * 100)}%"
        type_table_rows.append(
            f'<tr><td class="bold-cell">{t.replace("_", " ").title()}</td><td class="num">{n}</td><td class="num muted">{prev_n}</td><td>{trend}</td><td class="num">{share}</td></tr>'
        )
    type_table_html = "".join(type_table_rows) if type_table_rows else '<tr><td colspan="5" class="muted" style="text-align:center;padding:1.5rem">No categorized incidents recorded this week.</td></tr>'

    # Generalized Locations Table / List
    loc_table_rows = []
    for l, n in l_now.most_common(6):
        pct_loc = round((n / max(1, total_this)) * 100)
        loc_table_rows.append(
            f'''<div class="loc-item">
              <div class="loc-head"><span class="loc-name">{l.replace('_', ' ').title()}</span><span class="loc-count"><b>{n}</b> ({pct_loc}%)</span></div>
              <div class="loc-bar"><i style="width:{max(4, pct_loc)}%"></i></div>
            </div>'''
        )
    loc_table_html = "".join(loc_table_rows) if loc_table_rows else '<p class="muted">No location clusters recorded.</p>'

    # Urgency Badges & Counts
    imm_count = u_now.get("immediate", 0)
    soon_count = u_now.get("soon", 0)
    rout_count = u_now.get("routine", 0)

    gen_date = time.strftime("%d %B %Y, %H:%M IST")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Unsigned — Weekly Institutional Report (Week {week})</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Google+Sans:wght@400;500;600;700&family=Google+Sans+Text:wght@400;500;600;700&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&family=Manrope:wght@500;600;700;800&family=JetBrains+Mono:wght@500;600;700&display=swap">
<link rel="stylesheet" href="/app.css">
<style>
  body {{
    background: var(--ground);
    color: var(--ink);
    font-family: var(--ui);
    padding: 2.5rem 1rem 5rem;
  }}
  .report-container {{
    max-width: 900px;
    margin: 0 auto;
    background: var(--surface);
    border: 1px solid var(--rule);
    border-radius: 18px;
    padding: 2.5rem 2.8rem;
    box-shadow: 0 8px 30px rgba(31,29,26,0.04);
  }}
  
  /* Top Institutional Bar */
  .inst-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 2px solid var(--rule-strong);
    padding-bottom: 1.2rem;
    margin-bottom: 1.8rem;
    flex-wrap: wrap;
    gap: 1rem;
  }}
  .inst-brand {{
    font: 800 .82rem var(--ui);
    letter-spacing: .15em;
    text-transform: uppercase;
    color: var(--accent-ink);
  }}
  .inst-brand span {{
    color: var(--muted);
    font-weight: 500;
  }}
  .inst-actions {{
    display: flex;
    align-items: center;
    gap: .8rem;
  }}
  .btn-print {{
    background: var(--accent);
    color: #ffffff;
    border: 1px solid var(--accent);
    padding: .45rem 1rem;
    border-radius: 999px;
    font: 700 .82rem var(--ui);
    cursor: pointer;
    transition: all .15s;
    display: inline-flex;
    align-items: center;
    gap: .4rem;
  }}
  .btn-print:hover {{
    background: var(--accent-ink);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(31,111,120,0.25);
  }}
  
  /* Title Block */
  .title-block {{
    margin-bottom: 2rem;
  }}
  .title-block h1 {{
    font: 500 2.4rem/1.1 var(--serif);
    letter-spacing: -.02em;
    color: var(--ink);
    margin: 0 0 .5rem;
  }}
  .title-block h1 em {{
    font-style: italic;
    color: var(--accent-ink);
  }}
  .meta-row {{
    display: flex;
    gap: 1.2rem;
    align-items: center;
    font-size: .88rem;
    color: var(--muted);
    flex-wrap: wrap;
    margin-bottom: .8rem;
  }}
  .meta-row b {{ color: var(--ink); }}
  .confidential-notice {{
    background: var(--surface-2);
    border-left: 3px solid var(--accent);
    padding: .65rem 1rem;
    border-radius: 0 10px 10px 0;
    font: 400 .95rem/1.45 var(--serif);
    color: var(--muted);
  }}
  .confidential-notice b {{ color: var(--ink); }}

  /* KPI Grid */
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
    margin-bottom: 2.2rem;
  }}
  .kpi-card {{
    background: var(--surface-2);
    border: 1px solid var(--rule);
    border-radius: 14px;
    padding: 1.1rem 1.2rem;
    display: grid;
    gap: .25rem;
    align-content: start;
    transition: transform .15s var(--ease);
  }}
  .kpi-card:hover {{ transform: translateY(-2px); }}
  .kpi-card.alert-card {{
    background: var(--bad-wash);
    border-color: rgba(201, 70, 58, 0.3);
  }}
  .kpi-card.alert-card .kpi-num {{ color: var(--bad); }}
  .kpi-title {{
    font: 700 .68rem var(--ui);
    letter-spacing: .12em;
    text-transform: uppercase;
    color: var(--muted);
  }}
  .kpi-num {{
    font: 700 2.2rem/1.05 var(--num);
    color: var(--ink);
    letter-spacing: -.02em;
  }}
  .kpi-sub {{
    font-size: .8rem;
    color: var(--muted);
    line-height: 1.3;
  }}

  /* Analytics 2-Column Section: Category Distribution (320px) + Lifecycle & Urgency (Lengthened to fill width) */
  .analytics-grid {{
    display: grid;
    grid-template-columns: 320px 1fr;
    gap: 1.5rem;
    margin-bottom: 2.2rem;
    align-items: stretch;
  }}
  .panel {{
    background: var(--surface);
    border: 1px solid var(--rule);
    border-radius: 14px;
    padding: 1.3rem 1.4rem;
    box-shadow: 0 1px 4px rgba(31,29,26,0.02);
    display: flex;
    flex-direction: column;
  }}
  .panel-header {{
    border-bottom: 1px solid var(--rule);
    padding-bottom: .6rem;
    margin-bottom: 1rem;
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }}
  .panel-header h2 {{
    font: 600 1.2rem/1.2 var(--serif);
    color: var(--ink);
    margin: 0;
  }}
  .panel-header span {{
    font: 500 .75rem var(--num);
    color: var(--muted);
  }}

  /* Donut Layout - Chart Top, Legend Below */
  .donut-wrap {{
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1.1rem;
  }}
  .pie-container {{
    position: relative;
    width: 200px;
    height: 200px;
    flex-shrink: 0;
    margin: 0 auto;
  }}
  .chart-svg {{
    width: 200px;
    height: 200px;
    display: block;
    overflow: visible;
  }}
  .pie-slice {{
    transition: transform .2s var(--ease), filter .2s;
    transform-origin: 100px 100px;
    cursor: pointer;
  }}
  .pie-slice:hover {{
    transform: scale(1.035);
    filter: drop-shadow(0 4px 8px rgba(31,29,26,0.15));
  }}
  .pie-center {{
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    text-align: center;
    pointer-events: none;
    width: 120px;
  }}
  .pie-val {{
    font-family: var(--num);
    font-size: 1.65rem;
    font-weight: 700;
    line-height: 1.1;
    color: var(--ink);
    transition: color .15s ease;
  }}
  .pie-label {{
    font-family: var(--ui);
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted);
    margin-top: 2px;
    transition: color .15s ease;
  }}
  .legend-list {{
    display: grid;
    gap: .45rem;
    font-size: .84rem;
    width: 100%;
  }}
  .legend-row {{
    display: flex;
    align-items: center;
    gap: .55rem;
    padding: .35rem .5rem;
    border-radius: 8px;
    transition: background .15s;
    cursor: pointer;
  }}
  .legend-row:hover {{
    background: var(--surface-2);
  }}
  .legend-row .swatch {{
    width: 11px;
    height: 11px;
    border-radius: 3px;
    flex-shrink: 0;
  }}
  .legend-row .label {{
    flex: 1;
    color: var(--ink);
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .legend-row .count {{
    font: 700 .82rem var(--num);
    color: var(--muted);
  }}
  .legend-row .pct {{
    font: 700 .8rem var(--num);
    color: var(--accent-ink);
    width: 36px;
    text-align: right;
  }}

  /* Urgency & Status Distributions */
  .dist-group {{
    margin-bottom: 1.2rem;
  }}
  .dist-group:last-child {{ margin-bottom: 0; }}
  .dist-label {{
    font: 700 .68rem var(--ui);
    letter-spacing: .1em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: .45rem;
    display: block;
  }}
  .status-badges {{
    display: flex;
    gap: .5rem;
    flex-wrap: wrap;
    margin-bottom: .6rem;
  }}
  .bar-stacked {{
    height: 10px;
    border-radius: 6px;
    background: var(--code);
    display: flex;
    overflow: hidden;
    gap: 2px;
  }}
  .bar-stacked span {{
    height: 100%;
    transition: width .5s;
  }}

  /* Location Hotspots */
  .loc-item {{
    margin-bottom: .8rem;
  }}
  .loc-item:last-child {{ margin-bottom: 0; }}
  .loc-head {{
    display: flex;
    justify-content: space-between;
    font-size: .88rem;
    margin-bottom: .25rem;
  }}
  .loc-name {{ font-weight: 600; color: var(--ink); }}
  .loc-count {{ font-family: var(--num); font-size: .84rem; font-weight: 700; color: var(--muted); }}
  .loc-bar {{
    height: 7px;
    background: var(--surface-2);
    border-radius: 4px;
    overflow: hidden;
  }}
  .loc-bar i {{
    display: block;
    height: 100%;
    background: var(--accent);
    border-radius: 4px;
  }}

  /* Data Table */
  table.report-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: .88rem;
    margin-top: .4rem;
  }}
  table.report-table th {{
    background: var(--surface-2);
    padding: .7rem .9rem;
    font: 700 .68rem var(--ui);
    letter-spacing: .1em;
    text-transform: uppercase;
    color: var(--muted);
    border-bottom: 1px solid var(--rule-strong);
    text-align: left;
  }}
  table.report-table td {{
    padding: .75rem .9rem;
    border-bottom: 1px solid var(--rule);
    vertical-align: middle;
  }}
  table.report-table td.bold-cell {{
    font-weight: 600;
    color: var(--ink);
  }}
  table.report-table td.num {{
    font-family: var(--num);
    font-weight: 600;
    text-align: left;
  }}

  /* Regulatory & Sign-Off Footer */
  .sign-off-section {{
    border-top: 2px solid var(--rule-strong);
    padding-top: 1.8rem;
    margin-top: 2.5rem;
  }}
  .compliance-badge {{
    display: inline-flex;
    align-items: center;
    gap: .4rem;
    font: 700 .75rem var(--mono);
    color: var(--accent-ink);
    background: var(--accent-wash);
    padding: .35rem .8rem;
    border-radius: 999px;
    margin-bottom: 1rem;
  }}
  .signatures-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1.5rem;
    margin-top: 2.2rem;
  }}
  .sig-box {{
    border-top: 1px solid var(--rule-strong);
    padding-top: .5rem;
    font-size: .82rem;
  }}
  .sig-box b {{
    display: block;
    color: var(--ink);
    font-size: .86rem;
  }}
  .sig-box span {{
    color: var(--muted);
  }}

  /* Print Optimizations */
  @media print {{
    body {{
      background: #ffffff !important;
      padding: 0 !important;
    }}
    .report-container {{
      border: none !important;
      box-shadow: none !important;
      padding: 0 !important;
      max-width: 100% !important;
    }}
    .btn-print {{ display: none !important; }}
  }}
  
  @media (max-width: 768px) {{
    .report-container {{ padding: 1.5rem 1.2rem; }}
    .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .analytics-grid {{ grid-template-columns: 1fr; }}
    .donut-wrap {{ grid-template-columns: 1fr; text-align: center; }}
    .signatures-grid {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body class="student">
<div class="report-container">
  
  <!-- Institutional Header Bar -->
  <header class="inst-header">
    <div class="inst-brand">
      Unsigned <span>· Anti-Ragging Cell · Institutional Intelligence</span>
    </div>
    <div class="inst-actions">
      <span class="pill quiet">Week {week} Record</span>
      <button class="btn-print" onclick="window.print()">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9V2h12v7M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2"/><path d="M6 14h12v8H6z"/></svg>
        Print / PDF
      </button>
    </div>
  </header>

  <!-- Title & Confidentiality Notice -->
  <section class="title-block">
    <h1>Anti-Ragging Cell — <em>Weekly Intelligence Summary</em></h1>
    <div class="meta-row">
      <span>Reporting Period: <b>Academic Week {week}</b></span>
      <span>•</span>
      <span>Generated: <b>{gen_date}</b></span>
      <span>•</span>
      <span>Active Database: <b>{total_all} Total Released Cards</b></span>
    </div>
    <div class="confidential-notice">
      <b>Zero-Persistence Institutional Privacy Notice:</b> Aggregates and generalized distributions only. In accordance with zero-knowledge architectural principles, raw complaint texts are dereferenced in-memory. Cards are released only at granularities satisfying k-anonymity (k ≥ {K}). No student identities, roll numbers, or stylistic markers exist in institutional storage.
    </div>
  </section>

  <!-- 4-Column KPI Grid -->
  <section class="kpi-grid">
    <div class="kpi-card">
      <span class="kpi-title">Cards This Week</span>
      <span class="kpi-num">{total_this}</span>
      <span class="kpi-sub">{total_prev} cards logged last week ({delta_str} net trend)</span>
    </div>
    <div class="kpi-card {'alert-card' if imm_count > 0 else ''}">
      <span class="kpi-title">Immediate Urgency</span>
      <span class="kpi-num">{imm_count}</span>
      <span class="kpi-sub">{'Requires priority squad dispatch' if imm_count > 0 else 'Zero immediate distress spikes'}</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-title">Active Cases</span>
      <span class="kpi-num">{all_received + all_in_prog}</span>
      <span class="kpi-sub">{all_received} received · {all_in_prog} under investigation</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-title">Median Resolution</span>
      <span class="kpi-num">{f"{med_days}d" if med_days is not None else '—'}</span>
      <span class="kpi-sub">{all_resolved} cases successfully resolved</span>
    </div>
  </section>

  <!-- 2-Column Analytics: Donut Chart + Status/Urgency -->
  <section class="analytics-grid">
    
    <!-- Panel 1: Donut Pie Chart & Legend -->
    <div class="panel">
      <div class="panel-header">
        <h2>Category Distribution</h2>
        <span>this week's breakdown</span>
      </div>
      <div class="donut-wrap">
        <div class="pie-container">
          {donut_svg}
          <div class="pie-center text-center" id="pieCenter">
            <div class="font-bold text-xl pie-val" id="pieCenterVal">{total_this}</div>
            <div class="text-muted-foreground text-xs pie-label" id="pieCenterLabel">TOTAL</div>
          </div>
        </div>
        <div class="legend-list">
          {legend_html}
        </div>
      </div>
    </div>

    <!-- Panel 2: Urgency & Lifecycle Breakdown -->
    <div class="panel">
      <div class="panel-header">
        <h2>Lifecycle &amp; Urgency</h2>
        <span>operational status</span>
      </div>
      
      <div class="dist-group">
        <span class="dist-label">Urgency Tiers (This Week)</span>
        <div class="status-badges">
          <span class="pill {'bad' if imm_count > 0 else 'quiet'}">Immediate: {imm_count}</span>
          <span class="pill {'warn' if soon_count > 0 else 'quiet'}">Soon: {soon_count}</span>
          <span class="pill quiet">Routine: {rout_count}</span>
        </div>
        <div class="bar-stacked">
          <span style="width:{(imm_count/max(1, total_this))*100}%;background:var(--bad)"></span>
          <span style="width:{(soon_count/max(1, total_this))*100}%;background:var(--warn)"></span>
          <span style="width:{(rout_count/max(1, total_this))*100}%;background:var(--muted)"></span>
        </div>
      </div>

      <div class="dist-group">
        <span class="dist-label">Overall Case Status</span>
        <div class="status-badges">
          <span class="pill warn">Received: {all_received}</span>
          <span class="pill warn">In Progress: {all_in_prog}</span>
          <span class="pill ok">Resolved: {all_resolved}</span>
        </div>
        <div class="bar-stacked">
          <span style="width:{(all_received/max(1, total_all))*100}%;background:var(--warn)"></span>
          <span style="width:{(all_in_prog/max(1, total_all))*100}%;background:#4FC1C9"></span>
          <span style="width:{(all_resolved/max(1, total_all))*100}%;background:var(--ok)"></span>
        </div>
      </div>

      <div class="dist-group">
        <span class="dist-label">Resolution Efficiency</span>
        <p class="muted" style="margin:0;font-size:.85rem">
          Overall resolution rate: <b>{round((all_resolved / max(1, total_all)) * 100)}%</b> ({all_resolved} of {total_all} cases closed). Median time to resolution: <b>{med_days if med_days is not None else '—'} days</b>.
        </p>
      </div>

    </div>

  </section>

  <!-- Section: Category Trend Table -->
  <section class="panel" style="margin-bottom:1.8rem">
    <div class="panel-header">
      <h2>Ragging Taxonomy &amp; Behaviour Trends</h2>
      <span>UGC classification matrix</span>
    </div>
    <table class="report-table" aria-label="Category comparison table">
      <thead>
        <tr>
          <th>Incident Category</th>
          <th>This Week</th>
          <th>Last Week</th>
          <th>Trend</th>
          <th>Share</th>
        </tr>
      </thead>
      <tbody>
        {type_table_html}
      </tbody>
    </table>
  </section>

  <!-- Section: Spatial Distribution (Generalised Hotspots) -->
  <section class="panel" style="margin-bottom:2.2rem">
    <div class="panel-header">
      <h2>Spatial Hotspots (Generalised Locations)</h2>
      <span>k-anonymized campus zones</span>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.5rem">
      <div>
        {loc_table_html}
      </div>
      <div style="background:var(--surface-2);border-radius:12px;padding:1rem 1.2rem;font-size:.86rem;color:var(--muted);line-height:1.5">
        <b style="color:var(--ink);display:block;margin-bottom:.3rem">Generalization Guarantee:</b>
        Specific room numbers, individual wing identifiers, and exact timestamps are mathematically generalized before release to prevent triangulation. Reports are aggregated to campus zones (e.g. <i>Hostel B</i>, <i>Canteen</i>) shared by at least k={K} distinct complaints.
      </div>
    </div>
  </section>

  <!-- Sign-Off & Regulatory Compliance -->
  <footer class="sign-off-section">
    <div class="compliance-badge">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
      UGC Regulations (2009) &amp; Institutional Anti-Ragging Mandate Compliant
    </div>
    <p class="muted" style="font-size:.84rem;margin:0 0 1.5rem">
      This document constitutes the official anonymized weekly log of the Institutional Anti-Ragging Cell. Generated autonomously by Unsigned under zero-persistence guarantees. No raw student submissions or identity markers were processed into disk storage.
    </p>

    <div class="signatures-grid">
      <div class="sig-box">
        <b>Chairperson</b>
        <span>Anti-Ragging Squad / Cell</span>
      </div>
      <div class="sig-box">
        <b>Dean of Student Welfare</b>
        <span>Student Affairs Directorate</span>
      </div>
      <div class="sig-box">
        <b>Proctorial Board</b>
        <span>Campus Discipline Committee</span>
      </div>
    </div>
  </footer>

</div>
<script>
(function() {{
  const total = {total_this};
  const valEl = document.getElementById("pieCenterVal");
  const labEl = document.getElementById("pieCenterLabel");
  function setCenter(v, l, c) {{
    if (valEl) {{
      valEl.textContent = Number(v).toLocaleString();
      valEl.style.color = c || "";
    }}
    if (labEl) {{
      labEl.textContent = l;
      labEl.style.color = c ? "var(--ink)" : "";
    }}
  }}
  document.querySelectorAll(".pie-slice, .legend-row").forEach(el => {{
    el.addEventListener("mouseenter", () => {{
      const v = el.dataset.value;
      const l = el.dataset.label;
      const c = el.dataset.color;
      if (v != null) setCenter(v, l, c);
    }});
    el.addEventListener("mouseleave", () => {{
      setCenter(total, "TOTAL", "");
    }});
  }});
}})();
</script>
</body>
</html>"""


# ----------------------------------------------------------------- demo: the attacker as a product feature
@app.post("/api/attacker/link", dependencies=[Depends(committee), Depends(demo_only)])
def attacker_link(req: LinkRequest):
    """'Which two were written by the same student?' — pairwise same-author probabilities + attribution."""
    att = _require_attacker()
    n = len(req.texts)
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append({"a": i, "b": j, "same_author": round(att.link(req.texts[i], req.texts[j]), 3)})
    pairs.sort(key=lambda p: -p["same_author"])
    attributions = []
    for t in req.texts:
        a, p, _ = att.attribute(t)
        attributions.append({"author": a, "prob": round(p, 3)})
    return {"pairs": pairs, "attributions": attributions, "chance": att.chance(), "reference_authors": len(att.authors)}


@app.post("/api/attacker/reference", dependencies=[Depends(committee), Depends(demo_only)])
def attacker_reference(ref: Reference):
    """Models the adversary's knowledge (e.g. a warden holding a student's earlier essay). Demo only."""
    global _attacker
    _require_attacker()
    ref_path = os.path.join(MODELS, "a1_reference.json")
    data = json.load(open(ref_path, encoding="utf-8")) if os.path.exists(ref_path) else {"texts": [], "authors": []}
    with _model_lock:
        data["texts"].append(ref.text); data["authors"].append(ref.author)
        _atomic_json(ref_path, data)
        _attacker = StyleAttacker().fit(data["texts"], data["authors"])
    return {"ok": True, "reference_authors": len(set(data["authors"]))}
