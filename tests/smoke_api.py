"""End-to-end smoke test against a running server:  python tests/smoke_api.py http://localhost:8000 [passcode]"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
KEY = sys.argv[2] if len(sys.argv) > 2 else "committee"


def call(path, body=None, key=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["X-Committee-Key"] = key
    req = urllib.request.Request(BASE + path, method="POST" if body is not None else "GET", headers=headers,
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req) as r:
            ct = r.headers.get("content-type", "")
            return json.load(r) if ct.startswith("application/json") else r.read().decode()
    except urllib.error.HTTPError as e:
        return {"error": e.code, "detail": e.read().decode()[:120]}


judge_sample = "wow such a warm welcome?? 3 hours standing in the hostel B corridor at night, great tradition hmm"
new_text = "so the seniors made us stand in hostel b again at night?? and asked for 500 rupees this time. lovely people hmm"

print("1  committee auth :", "401 without passcode OK" if call("/api/cards").get("error") == 401 else "FAIL")
print("2  login          :", call("/api/login", {"passcode": KEY}))
print("3  attacker ref   :", call("/api/attacker/reference", {"author": "JUDGE", "text": judge_sample}, KEY))
link = call("/api/attacker/link", {"texts": [judge_sample, "BHAI kal raat seniors ne KHADE rakha!!! intro intro!!!", new_text]}, KEY)
print("4  which two?     :", link["pairs"][0])
p = call("/preview", {"text": new_text})
print("5  preview        :", p["card"]["narrative"][:90], "| flags:", len(p["flags"]))
s = call("/submit", {"text": new_text, "demo_author": "JUDGE"})
a = s["audit"]
print(f"6  submit         : case #{s['case']} token={s['token']} release_in={s['release_in_seconds']}s discarded_after={s['raw_discarded_after_ms']}ms")
print(f"7  audit          : P(JUDGE|raw)={a['raw_p_true']:.2f} -> P(JUDGE|card)={a['released_p_true']:.2f} | chance {a['chance']:.2f} | leak {a['leak_tv']:.2f}")
time.sleep(max(1, s["release_in_seconds"] + 1))
st = call(f"/api/status/{s['token']}")
print("8  student status :", st["status"], "| released:", st["released"])
add = call(f"/api/status/{s['token']}/add", {"text": "they also took my phone charger and said come back at 11 pm to hostel b"})
print("9  add info       :", add.get("ok"), "| card:", add["card"]["types"])
c = call("/api/cards", key=KEY)
mine = [d for d in c["cards"] if d["id"] == s["case"]][0]
print(f"10 committee cards: {len(c['cards'])} released, {c['pending_release']} pending, {c['below_k']} below k; case #{s['case']} shown at {mine['location']}/{mine['time_bucket']} k_ok={mine['k_satisfied']}")
print("11 reply          :", call(f"/api/cards/{s['case']}/reply", {"text": "Thank you. Warden rounds in that hostel are doubled from tonight. Add anything else here."}, KEY))
print("12 status change  :", call(f"/api/cards/{s['case']}/status", {"status": "in_progress"}, KEY))
st = call(f"/api/status/{s['token']}")
print("13 student sees   :", st["status"], "|", len(st["replies"]), "reply |", st["followups"], "addition")
pt = call("/api/patterns", key=KEY)
print("14 patterns       :", [(x["location"], x["time_bucket"], x["type"], x["cards_this_week"]) for x in pt["alerts"]] or "none")
au = call("/api/audit", key=KEY)
print("15 audit summary  :", {k: au[k] for k in ["channel_capacity_bits", "k", "attacker_reference_authors", "mean_raw_top_prob", "mean_leak_tv"]}, "| p50 discard", au["raw_discarded_after_ms"]["p50"], "ms")
rep = call("/api/report/weekly", key=KEY)
print("16 weekly report  :", "html OK" if "<h1>" in rep else rep)
print("17 pages          :", ["OK" if "<!doctype html>" in call(x).lower() else "FAIL" for x in ["/", "/status", "/console"]])
