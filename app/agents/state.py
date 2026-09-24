import operator
from typing import Annotated, TypedDict

from app.models.evidence import Evidence
from app.models.incident import IncidentSnapshot
from app.models.rca import RCA


class Classification(TypedDict):
    category: str
    method: str  # "rule" or "llm" — which path decided it (section 6.3)


class InvestigationState(TypedDict):
    incident: IncidentSnapshot
    repo_sha: str | None
    classification: Classification | None
    evidence: Annotated[list[Evidence], operator.add]  # raw: parallel nodes each append here
    evidence_bundle: list[Evidence]  # final, E1/E2/E3-numbered — set once by fuse_evidence
    rca: RCA | None
    errors: Annotated[list[str], operator.add]  # tool failures recorded, not fatal (section 6.4)
