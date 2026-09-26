from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.incident import Incident, IncidentStatus

_AUTO_RESOLVE_ELIGIBLE = [
    IncidentStatus.OPEN.value,
    IncidentStatus.REOPENED.value,
    IncidentStatus.RCA_READY.value,
    IncidentStatus.NEEDS_HUMAN.value,
]


def auto_resolve(db: Session, resolve_after_minutes: int) -> list[Incident]:
    """No new occurrences for resolve_after_minutes -> RESOLVED. Incidents
    mid-investigation (INVESTIGATING, FIX_PROPOSED) are left alone — those
    belong to the worker, not the detector."""
    cutoff = datetime.now(UTC) - timedelta(minutes=resolve_after_minutes)
    stale = (
        db.query(Incident)
        .filter(Incident.status.in_(_AUTO_RESOLVE_ELIGIBLE), Incident.last_seen < cutoff)
        .all()
    )
    for incident in stale:
        incident.status = IncidentStatus.RESOLVED.value
    db.commit()
    return stale
