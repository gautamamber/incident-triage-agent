import sys

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.agents.graph import build_graph
from app.db import SessionLocal, init_db
from app.models.incident import Incident, IncidentSnapshot, IncidentStatus

_CLAIMABLE = [IncidentStatus.OPEN.value, IncidentStatus.REOPENED.value]


def _claim_incident(db: Session) -> Incident | None:
    """Postgres advisory lock keyed by incident_id (architecture doc section
    5.4.1). Session-scoped — a crashed worker releases it automatically, no
    cleanup needed. `pg_try_advisory_lock` never blocks: if another worker
    already holds it, this just returns None and the caller tries the next
    incident."""
    incident = (
        db.query(Incident)
        .filter(Incident.status.in_(_CLAIMABLE))
        .order_by(Incident.first_seen)
        .first()
    )
    if incident is None:
        return None
    got_lock = db.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": incident.id}).scalar()
    return incident if got_lock else None


def run_once(db: Session, incident_id: int | None = None) -> None:
    incident = db.get(Incident, incident_id) if incident_id is not None else _claim_incident(db)
    if incident is None:
        print("[worker] nothing to investigate")
        return

    incident.status = IncidentStatus.INVESTIGATING.value
    db.commit()

    snapshot = IncidentSnapshot.model_validate(incident)
    graph = build_graph()
    result = graph.invoke(
        {
            "incident": snapshot,
            "repo_sha": None,
            "classification": None,
            "evidence": [],
            "evidence_bundle": [],
            "rca": None,
            "errors": [],
        }
    )

    rca = result.get("rca")
    incident.category = (result.get("classification") or {}).get("category")
    incident.rca_json = rca.model_dump_json() if rca else None
    incident.status = IncidentStatus.RCA_READY.value if rca else IncidentStatus.NEEDS_HUMAN.value
    db.commit()

    print(f"[worker] {incident.key} -> {incident.status}")
    if result.get("errors"):
        print(f"[worker] errors: {result['errors']}")


if __name__ == "__main__":
    init_db()
    session = SessionLocal()
    try:
        if len(sys.argv) > 1:
            run_once(session, incident_id=int(sys.argv[1].removeprefix("INC-")))
        else:
            run_once(session)
    finally:
        session.close()
