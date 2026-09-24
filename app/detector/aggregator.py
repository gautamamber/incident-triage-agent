from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.detector.fingerprint import fingerprint, normalize_message
from app.detector.severity import score_severity
from app.models.incident import Incident, IncidentStatus, OccurrenceBucket
from app.tools.loki import LogRecord


def _truncate_to_minute(timestamp_ns: int) -> datetime:
    dt = datetime.fromtimestamp(timestamp_ns / 1e9, tz=UTC)
    return dt.replace(second=0, microsecond=0)


def _upsert_bucket(db: Session, fp: str, service: str, bucket_start: datetime) -> None:
    stmt = insert(OccurrenceBucket).values(
        fingerprint=fp, service=service, bucket_start=bucket_start, count=1
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_fingerprint_bucket",
        set_={"count": OccurrenceBucket.count + 1},
    )
    db.execute(stmt)


def _count_in_window(db: Session, fp: str, window_minutes: int) -> int:
    since = datetime.now(UTC) - timedelta(minutes=window_minutes)
    total = db.scalar(
        select(func.sum(OccurrenceBucket.count)).where(
            OccurrenceBucket.fingerprint == fp,
            OccurrenceBucket.bucket_start >= since,
        )
    )
    return total or 0


def process_records(db: Session, records: list[LogRecord], policies: dict) -> list[Incident]:
    """Fingerprint each record, bucket it, then decide per-fingerprint whether
    to open, update, or reopen an incident (section 5.3-5.4). Returns incidents
    newly opened or reopened by this call (for notification / logging)."""
    detection = policies["detection"]
    always_page = set(detection["always_page_exceptions"])
    window_minutes = detection["window_minutes"]
    min_occurrences = detection["min_occurrences"]
    cooldown_minutes = detection["cooldown_minutes"]

    touched: dict[str, LogRecord] = {}
    for record in records:
        fp = fingerprint(
            service=record.service_name,
            exception_type=record.exception_type,
            message=record.body,
            top_frame=record.top_frame,
        )
        bucket_start = _truncate_to_minute(record.timestamp_ns)
        _upsert_bucket(db, fp, record.service_name, bucket_start)
        touched[fp] = record  # last record for this fingerprint in this batch
    db.commit()

    opened: list[Incident] = []
    now = datetime.now(UTC)

    for fp, record in touched.items():
        count = _count_in_window(db, fp, window_minutes)

        active = (
            db.query(Incident)
            .filter(Incident.fingerprint == fp, Incident.status != IncidentStatus.RESOLVED.value)
            .first()
        )
        if active:
            active.last_seen = now
            active.error_count = count
            if record.trace_id and record.trace_id not in active.sample_trace_ids:
                active.sample_trace_ids = [*active.sample_trace_ids, record.trace_id][:5]
            db.commit()
            continue

        should_open = count >= min_occurrences or record.exception_type in always_page
        if not should_open:
            continue

        recently_resolved = (
            db.query(Incident)
            .filter(
                Incident.fingerprint == fp,
                Incident.status == IncidentStatus.RESOLVED.value,
                Incident.last_seen >= now - timedelta(minutes=cooldown_minutes),
            )
            .order_by(Incident.last_seen.desc())
            .first()
        )
        if recently_resolved:
            recently_resolved.status = IncidentStatus.REOPENED.value
            recently_resolved.last_seen = now
            recently_resolved.error_count = count
            db.commit()
            opened.append(recently_resolved)
            continue

        incident = Incident(
            fingerprint=fp,
            service=record.service_name,
            severity=score_severity(error_count_5m=count),
            status=IncidentStatus.OPEN.value,
            exception_type=record.exception_type,
            normalized_message=normalize_message(record.body),
            sample_message=record.body,
            top_frame=record.top_frame,
            first_seen=now,
            last_seen=now,
            error_count=count,
            sample_trace_ids=[record.trace_id] if record.trace_id else [],
            affected_routes=[],
        )
        db.add(incident)
        db.commit()
        opened.append(incident)

    return opened
