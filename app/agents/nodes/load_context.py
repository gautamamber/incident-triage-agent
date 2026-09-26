from datetime import UTC, datetime

from app.agents.state import InvestigationState
from app.services.repo_registry import get_service
from app.tools.git_repo import current_sha


def load_context(state: InvestigationState) -> dict:
    """Resolves the service's repo and pins HEAD (section 6.3) — everything
    downstream in this run investigates against this exact commit, even if the
    repo moves on while the run is in progress. Also stamps run_started_at —
    the wall-time budget (doc 11.7) measures from here, not from incident
    detection, so the clock doesn't include time the incident spent queued."""
    incident = state["incident"]
    started_at = datetime.now(UTC).isoformat()
    try:
        service_cfg = get_service(incident.service)
        sha = current_sha(service_cfg.repo_path)
        return {"repo_sha": sha, "run_started_at": started_at}
    except Exception as exc:
        return {"repo_sha": None, "run_started_at": started_at, "errors": [f"load_context: {exc}"]}
