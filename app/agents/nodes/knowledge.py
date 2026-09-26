from app.agents.state import InvestigationState
from app.db import SessionLocal
from app.knowledge import hybrid_search
from app.models.evidence import Evidence


def retrieve_knowledge(state: InvestigationState) -> dict:
    """Runs after code_investigation, before rca — retrieved runbooks/
    past-incidents become new evidence items, same numbering pattern as
    code_investigation's findings, so the rca prompt sees them the same way
    it sees any other evidence source."""
    incident = state["incident"]
    classification = state.get("classification") or {}
    query = " ".join(
        [
            classification.get("category", ""),
            incident.exception_type or "",
            incident.normalized_message,
        ]
    )

    db = SessionLocal()
    try:
        hits = hybrid_search(db, query)
    finally:
        db.close()

    bundle = state["evidence_bundle"]
    new_evidence = [
        Evidence(
            id=f"E{len(bundle) + i + 1}",
            source="knowledge",
            summary=f"{hit.title} (match score {hit.score})",
            facts={"excerpt": hit.excerpt, "score": hit.score},
            ref=hit.source,
        )
        for i, hit in enumerate(hits)
    ]

    return {"knowledge": hits, "evidence_bundle": bundle + new_evidence}
