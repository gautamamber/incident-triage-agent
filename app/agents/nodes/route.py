from app.agents.state import InvestigationState
from app.config import settings
from app.models.rca import FixStrategy
from app.services.repo_registry import get_service


def fix_eligibility(state: InvestigationState) -> tuple[bool, str]:
    """Checks every precondition from doc section 9.1, in code — not because
    the fix subgraph exists yet (Phase 10), but so the reasoning is visible
    now and AGENT_MODE is enforced here, at the routing step, exactly where
    the Phase 0 gap-fix said it must be: not trusted from anything the LLM
    said, read directly from the typed settings object."""
    rca = state["rca"]
    confidence = state["confidence"]
    if rca is None or confidence is None:
        return False, "no RCA/confidence available"
    if settings.agent_mode != "fix":
        return False, f"AGENT_MODE={settings.agent_mode!r} (needs 'fix')"
    if confidence.band != "high":
        return False, f"confidence band is {confidence.band!r} (needs 'high')"
    if rca.fix_strategy not in (FixStrategy.REVERT_COMMIT, FixStrategy.CODE_CHANGE):
        return False, (
            f"fix_strategy is {rca.fix_strategy.value!r} (needs revert_commit/code_change)"
        )
    try:
        service_cfg = get_service(state["incident"].service)
    except (KeyError, ValueError):
        return False, "service not found in registry"
    if not service_cfg.fix_allowed:
        return False, f"service {state['incident'].service!r} is not on the fix allowlist"
    return True, "eligible — would enter the fix subgraph (Phase 10, not built yet)"


def route_decision(state: InvestigationState) -> str:
    """The one real conditional edge in this graph (doc section 6.1's ROUTE
    node): low confidence goes through an explicit needs-human step first;
    high confidence that also passes fix_eligibility() goes to the fix
    subgraph; everything else goes straight to notify."""
    confidence = state["confidence"]
    if confidence is None or confidence.band == "low":
        return "needs_human"
    eligible, _ = fix_eligibility(state)
    if eligible:
        return "fix"
    return "notify"


def mark_needs_human(state: InvestigationState) -> dict:
    confidence = state["confidence"]
    unknowns = state["rca"].unknowns if state["rca"] else []
    note = (
        f"NEEDS_HUMAN: confidence={confidence.score if confidence else 0} "
        f"({confidence.band if confidence else 'none'}) — unknowns: {unknowns}"
    )
    return {"errors": [note]}
