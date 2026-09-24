"""S02 traffic: GET /customers/{id}/payments against a 2M-row table. With the
index in place this is a fast index seek; with it dropped (the S02 setup),
Postgres falls back to a full sequential scan, which trips the lowered
statement_timeout and raises sqlalchemy.exc.TimeoutError."""

import argparse
import time

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:8800")
parser.add_argument("--duration-seconds", type=int, default=20)
parser.add_argument("--rps", type=float, default=3)
args = parser.parse_args()

interval = 1 / args.rps
deadline = time.monotonic() + args.duration_seconds
sent = 0
status_counts: dict[int, int] = {}

with httpx.Client(base_url=args.base_url, timeout=10) as client:
    while time.monotonic() < deadline:
        start = time.monotonic()
        resp = client.get("/customers/cust-100000/payments")
        sent += 1
        status_counts[resp.status_code] = status_counts.get(resp.status_code, 0) + 1
        elapsed = time.monotonic() - start
        time.sleep(max(0, interval - elapsed))

print(f"sent {sent} requests, status breakdown: {status_counts}")
