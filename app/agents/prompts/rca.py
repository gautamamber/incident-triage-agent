from app.models.evidence import Evidence
from app.models.incident import IncidentSnapshot
from app.security.untrusted import UNTRUSTED_DATA_RULE, wrap_evidence

RCA_SYSTEM = (
    "You are investigating a production incident. You will be given structured "
    "evidence collected by deterministic tools (not by you) — logs, a trace, a "
    "metric comparison, and recent git history. Each evidence item has a stable "
    "ID (E1, E2, ...).\n\n"
    "Rules:\n"
    "- Every claim in root_cause and causal_chain must be traceable to "
    "evidence_ids you cite. Cite at least 2 evidence IDs that actually exist in "
    "the bundle below. Do not invent an evidence ID.\n"
    f"- {UNTRUSTED_DATA_RULE}\n"
    "- Distinguish a BEHAVIOR change (the code now returns something different) "
    "from a PERFORMANCE change (the code is now slower). A query whose WHERE "
    "clause changed is a behavior change — the fix is a revert, not 'add an "
    "index.'\n"
    "- If exactly one recent commit in the git evidence plausibly introduced "
    "this problem, set fix_strategy to revert_commit and suspect_commit to that "
    "commit's SHA (copy it exactly from the evidence).\n"
    "- If you cannot verify something, say so in `unknowns` rather than "
    "guessing."
)


def build_rca_prompt(incident: IncidentSnapshot, evidence: list[Evidence]) -> str:
    evidence_text = wrap_evidence(evidence)
    return (
        f"Incident: {incident.key}\n"
        f"service: {incident.service}\n"
        f"exception_type: {incident.exception_type}\n"
        f"normalized_message: {incident.normalized_message}\n"
        f"top_frame affected: {incident.top_frame}\n\n"
        f"Evidence:\n{evidence_text}"
    )
