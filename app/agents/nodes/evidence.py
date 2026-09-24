from app.agents.state import InvestigationState
from app.evidence import renumber_evidence


def fuse_evidence(state: InvestigationState) -> dict:
    """Runs once, after all 4 parallel collect_* nodes have finished (LangGraph
    only enters this node once every edge into it has fired) — assigns the
    final E1/E2/E3... IDs the rca node will cite."""
    return {"evidence_bundle": renumber_evidence(state["evidence"])}
