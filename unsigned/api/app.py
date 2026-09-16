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

from ..patterns.detect import detect
from ..pipeline.card import Card, channel_capacity_bits
from ..pipeline.classify import BaselineClassifier, load_classifier
from ..pipeline.run import display as _display, preview as _preview, process as _process
from ..pipeline.narrate import LEXICON, narrative_capacity_bits
from ..privacy.attacker import StyleAttacker

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
        """)
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
        released = list(_released_fine(con).values())
        result = _process(s.text, clf, _attacker, released, K, demo_author=_demo_author(s), facts_override=s.facts_override)
        del s
        tok = _token()
        card_id, delay = _store(con, result["card"], result, _hash(tok))
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
        released = list(_released_fine(con).values())
        result = _process(s.text, clf, _attacker, released, K, facts_override=s.facts_override)
        del s
        _, delay = _store(con, result["card"], result, _hash(token), parent_id=parent["id"])
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
    return {"ok": True}


@app.post("/api/cards/{card_id}/status", dependencies=[Depends(committee)])
def set_status(card_id: int, s: StatusChange):
    if s.status not in STATUSES:
        raise HTTPException(400, f"status must be one of {STATUSES}")
    with _db() as con:
        con.execute("UPDATE cards SET status=?, resolved_at=? WHERE id=?",
                    (s.status, time.time() if s.status == "resolved" else None, card_id))
    return {"ok": True}


@app.get("/api/report/weekly", dependencies=[Depends(committee)], response_class=HTMLResponse)
def weekly_report():
    """Aggregates only — no cards, no narratives — suitable for the institution's records."""
    week = int(time.time() // (7 * 86400))
    with _db() as con:
        rows = con.execute("SELECT card_json, week, status, day_bucket, resolved_at, release_at FROM cards WHERE released=1").fetchall()
    this = [r for r in rows if r["week"] == week]
    prev = [r for r in rows if r["week"] == week - 1]

    def agg(rs):
        c_type, c_loc, c_urg = Counter(), Counter(), Counter()
        for r in rs:
            d = json.loads(r["card_json"])
            for t in d["types"]:
                c_type[t] += 1
            c_loc[d["location"]] += 1
            c_urg[d["urgency"]] += 1
        return c_type, c_loc, c_urg

    t_now, l_now, u_now = agg(this)
    t_prev, _, _ = agg(prev)
    resolved = [r for r in rows if r["status"] == "resolved" and r["resolved_at"]]
    med_days = None
    if resolved:
        ds = sorted((r["resolved_at"] - r["release_at"]) / 86400 for r in resolved)
        med_days = round(ds[len(ds) // 2], 1)
    rows_html = "".join(f"<tr><td>{t.replace('_', ' ')}</td><td>{n}</td><td>{t_prev.get(t, 0)}</td></tr>" for t, n in t_now.most_common())
    loc_html = "".join(f"<li>{l.replace('_', ' ')}: {n}</li>" for l, n in l_now.most_common(6))
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Unsigned — weekly report</title>
<link rel="stylesheet" href="/app.css"></head><body class="report"><main class="narrow">
<p class="lab">Unsigned · institutional summary · week {week} · generated {time.strftime('%d %b %Y %H:%M')}</p>
<h1>Anti-ragging cell — weekly summary</h1>
<p class="muted">Aggregates only. No individual card, narrative or student information appears in this report.</p>
<div class="grid3">
  <div class="tile"><span class="lab">Cards this week</span><span class="big">{len(this)}</span><span class="muted">{len(prev)} last week</span></div>
  <div class="tile"><span class="lab">Immediate-urgency cards</span><span class="big">{u_now.get('immediate', 0)}</span></div>
  <div class="tile"><span class="lab">Median days to resolve</span><span class="big">{med_days if med_days is not None else '—'}</span></div>
</div>
<h2>By type</h2><table><tr><th>Type</th><th>This week</th><th>Last week</th></tr>{rows_html or '<tr><td colspan=3>none</td></tr>'}</table>
<h2>Where (generalised)</h2><ul>{loc_html or '<li>none</li>'}</ul>
<h2>Status</h2><p>Received {sum(1 for r in rows if r['status']=='received')} · In progress {sum(1 for r in rows if r['status']=='in_progress')} · Resolved {sum(1 for r in rows if r['status']=='resolved')}</p>
<p class="muted">Privacy: raw complaint text is never stored; cards are released only at a granularity shared by at least {K} cards.</p>
</main></body></html>"""


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
