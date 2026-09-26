import operator
from typing import Annotated, TypedDict

from app.models.code_finding import CodeFinding
from app.models.confidence import ConfidenceScore
from app.models.evidence import Evidence
from app.models.fix import FixResult
from app.models.incident import IncidentSnapshot
from app.models.knowledge import KnowledgeHit
from app.models.rca import RCA


class Classification(TypedDict):
    category: str
    method: str  # "rule" or "llm" — which path decided it (section 6.3)


class InvestigationState(TypedDict):
    incident: IncidentSnapshot
    repo_sha: str | None
    run_started_at: str | None  # ISO timestamp from load_context (doc 11.7 wall-time budget)
    token_usage: Annotated[int, operator.add]  # running total across every LLM call this run
    classification: Classification | None
    evidence: Annotated[list[Evidence], operator.add]  # raw: parallel nodes each append here
    evidence_bundle: list[Evidence]  # final, E1/E2/E3-numbered — set once by fuse_evidence
    code_findings: list[CodeFinding]
    knowledge: list[KnowledgeHit]
    rca: RCA | None
    confidence: ConfidenceScore | None
    fix: FixResult | None
    errors: Annotated[list[str], operator.add]  # tool failures recorded, not fatal (section 6.4)
