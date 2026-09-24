import sys

from app.db import SessionLocal, init_db
from app.evidence import build_evidence_bundle
from app.models.incident import Incident


def cmd_evidence(incident_key: str) -> None:
    if not incident_key.startswith("INC-"):
        raise SystemExit(f"expected INC-xxxx, got {incident_key!r}")
    incident_id = int(incident_key.removeprefix("INC-"))

    init_db()
    db = SessionLocal()
    try:
        incident = db.get(Incident, incident_id)
        if incident is None:
            raise SystemExit(f"no incident {incident_key}")

        print(f"=== {incident.key} ({incident.severity}, {incident.status}) ===")
        print(f"service:             {incident.service}")
        print(f"exception_type:      {incident.exception_type}")
        print(f"normalized_message:  {incident.normalized_message}")
        print(f"top_frame:           {incident.top_frame}")
        print(f"error_count:         {incident.error_count}")
        print()

        bundle = build_evidence_bundle(incident)
        for item in bundle:
            print(f"[{item.id}] ({item.source}) {item.summary}")
            if item.ref:
                print(f"    ref: {item.ref}")
            for key, value in item.facts.items():
                print(f"    {key}: {value}")
            print()
    finally:
        db.close()


def main() -> None:
    if len(sys.argv) < 3 or sys.argv[1] != "evidence":
        raise SystemExit("usage: uv run python -m app.debug evidence INC-xxxx")
    cmd_evidence(sys.argv[2])


if __name__ == "__main__":
    main()
