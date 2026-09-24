"""S06 traffic: GET /payments/{id} with IDs that never exist. Expected: steady
404s logged at WARNING, no incident ever opens (section 5.3 — WARN never opens one)."""

import argparse
import time
import uuid

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:8800")
parser.add_argument("--duration-seconds", type=int, default=60)
parser.add_argument("--rps", type=float, default=5)
args = parser.parse_args()

interval = 1 / args.rps
deadline = time.monotonic() + args.duration_seconds
sent = 0

with httpx.Client(base_url=args.base_url, timeout=5) as client:
    while time.monotonic() < deadline:
        start = time.monotonic()
        resp = client.get(f"/payments/{uuid.uuid4()}")
        sent += 1
        assert resp.status_code == 404, f"expected 404, got {resp.status_code}: {resp.text}"
        elapsed = time.monotonic() - start
        time.sleep(max(0, interval - elapsed))

print(f"sent {sent} requests, all 404")
