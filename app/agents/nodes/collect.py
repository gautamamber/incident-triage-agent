from app.agents.state import InvestigationState
from app.evidence import (
    build_git_evidence,
    build_log_evidence,
    build_metric_evidence,
    build_trace_evidence,
)

# Four independent nodes — LangGraph runs them in parallel since none of them
# read each other's output, only the shared incident (section 6.1's fan-out).
# Each appends 0 or 1 items to the shared `evidence` list via its reducer.


def collect_logs(state: InvestigationState) -> dict:
    try:
        item = build_log_evidence(state["incident"])
        return {"evidence": [item] if item else []}
    except Exception as exc:
        return {"errors": [f"collect_logs: {exc}"]}


def collect_traces(state: InvestigationState) -> dict:
    try:
        item = build_trace_evidence(state["incident"])
        return {"evidence": [item] if item else []}
    except Exception as exc:
        return {"errors": [f"collect_traces: {exc}"]}


def collect_metrics(state: InvestigationState) -> dict:
    try:
        item = build_metric_evidence(state["incident"])
        return {"evidence": [item]}
    except Exception as exc:
        return {"errors": [f"collect_metrics: {exc}"]}


def collect_git(state: InvestigationState) -> dict:
    try:
        item = build_git_evidence(state["incident"])
        return {"evidence": [item] if item else []}
    except Exception as exc:
        return {"errors": [f"collect_git: {exc}"]}
