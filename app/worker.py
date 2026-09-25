import sys
from pathlib import Path

from langgraph.checkpoint.postgres import PostgresSaver
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.agents.graph import build_graph
from app.db import SessionLocal, checkpointer_conn_string, init_db
from app.knowledge import reindex_knowledge
from app.models.confidence import ConfidenceScore
from app.models.fix import FixOutcome
from app.models.incident import Incident, IncidentSnapshot, IncidentStatus
from app.models.rca import RCA
from app.security.redaction import redact

KNOWLEDGE_INCIDENTS_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "incidents"

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


def _write_knowledge_draft(
    incident: IncidentSnapshot, rca: RCA, confidence: ConfidenceScore | None
) -> None:
    """Doc section 6.3's persist node: 'writes a draft knowledge/incidents/
    INC-xxxx.md for human editing.' This is how the knowledge base grows on
    its own — today's resolved incident becomes tomorrow's retrieve_knowledge
    hit. Redacted like every other piece of text that leaves this pipeline,
    even though the RCA's own inputs were already redacted upstream —
    defense in depth, same reasoning as the collector's two redaction passes
    back in Phase 1."""
    KNOWLEDGE_INCIDENTS_DIR.mkdir(parents=True, exist_ok=True)
    causal_chain = "\n".join(f"- {step}" for step in rca.causal_chain)
    # A short title, not the full root_cause sentence — this becomes the H1
    # heading AND (via _load_documents' "first line, minus '#'" rule) the
    # title stored in knowledge_documents. The full explanation still lives
    # in full under "## Root cause" just below.
    short_title = rca.root_cause if len(rca.root_cause) <= 80 else rca.root_cause[:77] + "..."
    content = (
        f"# {incident.key}: {short_title}\n\n"
        f"**Service:** {incident.service}\n"
        f"**Category:** {rca.category.value}\n"
        f"**Exception:** {incident.exception_type}\n"
        f"**Confidence:** {confidence.score if confidence else 'n/a'} "
        f"({confidence.band if confidence else 'n/a'})\n\n"
        f"## Root cause\n{rca.root_cause}\n\n"
        f"## Causal chain\n{causal_chain}\n\n"
        f"## Recommended action\n{rca.recommended_action}\n\n"
        f"## Suspect commit\n{rca.suspect_commit or 'none identified'}\n\n"
        "---\n*Draft, written automatically. Edit before treating as a trusted runbook.*\n"
    )
    (KNOWLEDGE_INCIDENTS_DIR / f"{incident.key}.md").write_text(redact(content))


def run_once(db: Session, incident_id: int | None = None) -> None:
    incident = db.get(Incident, incident_id) if incident_id is not None else _claim_incident(db)
    if incident is None:
        print("[worker] nothing to investigate")
        return

    incident.status = IncidentStatus.INVESTIGATING.value
    db.commit()

    snapshot = IncidentSnapshot.model_validate(incident)
    # thread_id = incident.id: every node's output is saved to Postgres under
    # this thread (doc section 6.2). If the worker dies mid-run, invoking
    # again with the same thread_id and input=None resumes from the last
    # completed node instead of re-running the whole investigation.
    config = {"configurable": {"thread_id": str(incident.id)}}
    with PostgresSaver.from_conn_string(checkpointer_conn_string()) as checkpointer:
        graph = build_graph(checkpointer=checkpointer)
        result = graph.invoke(
            {
                "incident": snapshot,
                "repo_sha": None,
                "classification": None,
                "evidence": [],
                "evidence_bundle": [],
                "code_findings": [],
                "knowledge": [],
                "rca": None,
                "confidence": None,
                "fix": None,
                "errors": [],
            },
            config=config,
        )

    rca = result.get("rca")
    confidence = result.get("confidence")
    fix = result.get("fix")
    incident.category = (result.get("classification") or {}).get("category")
    incident.rca_json = rca.model_dump_json() if rca else None
    incident.confidence_score = confidence.score if confidence else None
    incident.confidence_band = confidence.band if confidence else None

    if not rca or (confidence and confidence.band == "low"):
        incident.status = IncidentStatus.NEEDS_HUMAN.value
    elif fix is not None and fix.outcome == FixOutcome.DRAFT_PR_OPENED:
        incident.status = IncidentStatus.FIX_PROPOSED.value
    else:
        incident.status = IncidentStatus.RCA_READY.value
    db.commit()

    if rca:
        _write_knowledge_draft(snapshot, rca, confidence)
        reindex_knowledge(db)  # so this incident is vector-searchable next time

    print(f"[worker] {incident.key} -> {incident.status}")
    if fix is not None:
        print(
            f"[worker] fix: {fix.outcome.value} ({fix.strategy}) {fix.pr_url or fix.give_up_reason}"
        )
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
