import sys
import time
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.detector import aggregator, lifecycle
from app.models.incident import DetectorCursor
from app.policies import load_policies
from app.tools.loki import query_errors

OVERLAP_NS = 10_000_000_000  # 10s, tolerates ingestion delay (section 5.1)


def _get_cursor(db: Session) -> int:
    cursor = db.get(DetectorCursor, "loki")
    if cursor is None:
        start_ns = int((time.time() - 300) * 1e9)  # first run: last 5 min, not all history
        cursor = DetectorCursor(id="loki", last_timestamp_ns=start_ns)
        db.add(cursor)
        db.commit()
        return start_ns
    return cursor.last_timestamp_ns


def _set_cursor(db: Session, timestamp_ns: int) -> None:
    cursor = db.get(DetectorCursor, "loki")
    cursor.last_timestamp_ns = timestamp_ns
    db.commit()


def poll_once(db: Session, service: str):
    policies = load_policies()
    last_ts = _get_cursor(db)
    start_ns = last_ts - OVERLAP_NS
    end_ns = int(time.time() * 1e9)

    records = query_errors(settings.loki_url, service, start_ns, end_ns)

    # De-dup the overlap window: skip anything at/before the cursor, and
    # anything with an identical (timestamp, body) pair already seen this call
    # (a simplified stand-in for the doc's (timestamp, stream, hash(line))).
    seen = set()
    new_records = []
    for r in records:
        key = (r.timestamp_ns, r.body)
        if r.timestamp_ns <= last_ts or key in seen:
            continue
        seen.add(key)
        new_records.append(r)

    opened = aggregator.process_records(db, new_records, policies)
    lifecycle.auto_resolve(db, policies["detection"]["resolve_after_minutes"])

    if records:
        _set_cursor(db, max(r.timestamp_ns for r in records))

    return opened


def run_forever(service: str) -> None:
    from app.db import SessionLocal, init_db

    init_db()
    poll_seconds = load_policies()["detection"]["poll_seconds"]
    print(f"[detector] polling {service} every {poll_seconds}s")

    while True:
        db = SessionLocal()
        try:
            opened = poll_once(db, service)
            for incident in opened:
                ts = datetime.now(UTC).isoformat()
                print(
                    f"[{ts}] opened {incident.key} ({incident.severity}): "
                    f"{incident.normalized_message}"
                )
        finally:
            db.close()
        time.sleep(poll_seconds)


if __name__ == "__main__":
    run_forever(sys.argv[1] if len(sys.argv) > 1 else "payment-service")
