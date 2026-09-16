"""Run Unsigned:  python -m unsigned [--host 0.0.0.0] [--port 8000] [--db unsigned.sqlite] [--key <committee passcode>]

Access logging is OFF on purpose (no IP addresses are ever written). Bind to the college LAN address
so students can reach the page from their phones; there is no cloud component.
"""
from __future__ import annotations

import argparse
import os
import socket


def main() -> None:
    ap = argparse.ArgumentParser(prog="unsigned")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--db", default=os.environ.get("UNSIGNED_DB", "unsigned.sqlite"))
    ap.add_argument("--key", default=os.environ.get("UNSIGNED_COMMITTEE_KEY", "committee"), help="committee passcode")
    ap.add_argument("--k", type=int, default=int(os.environ.get("UNSIGNED_K", "3")))
    ap.add_argument("--real-delays", action="store_true", help="use real release delays (hours) instead of demo seconds")
    ap.add_argument("--no-demo", action="store_true", help="disable Present mode, demo endpoints and demo_author (real deployments)")
    args = ap.parse_args()

    os.environ["UNSIGNED_DB"] = os.path.abspath(args.db)
    os.environ["UNSIGNED_COMMITTEE_KEY"] = args.key
    os.environ["UNSIGNED_K"] = str(args.k)
    os.environ["UNSIGNED_DEMO_FAST"] = "0" if args.real_delays else "1"
    os.environ["UNSIGNED_DEMO"] = "0" if args.no_demo else "1"

    import uvicorn
    try:
        lan = socket.gethostbyname(socket.gethostname())
    except OSError:
        lan = "127.0.0.1"
    print(f"\nUnsigned  ·  students: http://{lan}:{args.port}/   ·  committee: http://{lan}:{args.port}/console"
          f"   ·  passcode: {args.key}\n(access log disabled — no IP addresses are recorded)\n")
    uvicorn.run("unsigned.api.app:app", host=args.host, port=args.port, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
