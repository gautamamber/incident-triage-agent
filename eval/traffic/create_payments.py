"""S03 traffic: POST /payments repeatedly. On clean code these all succeed.
With the S03 bug applied (a raw connection opened per request, never closed),
the connection pool exhausts after pool_size + max_overflow requests, and
later requests fail with sqlalchemy.exc.TimeoutError."""

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
status_counts: dict[int, int] = {}

with httpx.Client(base_url=args.base_url, timeout=10) as client:
    while time.monotonic() < deadline:
        start = time.monotonic()
        resp = client.post(
            "/payments", json={"customer_id": str(uuid.uuid4()), "amount": 10.0}
        )
        sent += 1
        status_counts[resp.status_code] = status_counts.get(resp.status_code, 0) + 1
        elapsed = time.monotonic() - start
        time.sleep(max(0, interval - elapsed))

print(f"sent {sent} requests, status breakdown: {status_counts}")
