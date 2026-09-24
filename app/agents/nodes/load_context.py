from app.agents.state import InvestigationState
from app.services.repo_registry import get_service
from app.tools.git_repo import current_sha


def load_context(state: InvestigationState) -> dict:
    """Resolves the service's repo and pins HEAD (section 6.3) — everything
    downstream in this run investigates against this exact commit, even if the
    repo moves on while the run is in progress."""
    incident = state["incident"]
    try:
        service_cfg = get_service(incident.service)
        sha = current_sha(service_cfg.repo_path)
        return {"repo_sha": sha}
    except Exception as exc:
        return {"repo_sha": None, "errors": [f"load_context: {exc}"]}
