from app.agents.state import InvestigationState
from app.models.confidence import ConfidenceScore
from app.models.evidence import Evidence
from app.policies import load_policies

_DB_HINTS = ("postgres", "database", "sql")


def _find(bundle: list[Evidence], source: str) -> Evidence | None:
    return next((e for e in bundle if e.source == source), None)


def _dominant_hotspot(bundle: list[Evidence]) -> dict | None:
    trace = _find(bundle, "trace")
    if trace is None:
        return None
    components = trace.facts.get("components") or []
    if not components or components[0].get("pct", 0) < 60:
        return None
    return components[0]


def _trace_hotspot(bundle: list[Evidence], category: str, weight: float) -> tuple[float, str]:
    hotspot = _dominant_hotspot(bundle)
    if hotspot is None:
        return 0.0, "no dominant trace hotspot (need >=60% of latency in one component)"
    hotspot_is_db = any(h in hotspot["name"].lower() for h in _DB_HINTS)
    if hotspot_is_db == (category == "DATABASE"):
        return weight, f"hotspot {hotspot['name']} ({hotspot['pct']}%) matches category {category}"
    return 0.0, f"hotspot {hotspot['name']} present but doesn't match category {category}"


def _code_location(state: InvestigationState, weight: float) -> tuple[float, str]:
    rca = state["rca"]
    top_frame_file = (state["incident"].top_frame or "").split(":")[0]
    component_file = rca.affected_component.split(":")[0]
    if component_file and component_file == top_frame_file:
        return weight, f"affected_component matches crash top_frame ({component_file})"
    return 0.0, "affected_component doesn't match crash top_frame"


def _change_correlation(bundle: list[Evidence], rca, weight: float) -> tuple[float, str]:
    git = _find(bundle, "git")
    if git is None or not rca.suspect_commit:
        return 0.0, "no git evidence or RCA named no suspect commit"
    if git.ref == rca.suspect_commit:
        return weight, f"suspect_commit {rca.suspect_commit[:8]} matches the git evidence found"
    return 0.0, "RCA's suspect_commit doesn't match the commit git evidence found"


def _metric_corroboration(bundle: list[Evidence], weight: float) -> tuple[float, str]:
    metric = _find(bundle, "metric")
    if metric is None:
        return 0.0, "no metric evidence"
    ratio = metric.facts.get("change_ratio")
    baseline = metric.facts.get("baseline_value") or 0
    incident_v = metric.facts.get("incident_value") or 0
    changed = (ratio is not None and (ratio > 1.5 or ratio < 0.67)) or (baseline == 0 < incident_v)
    if changed:
        return weight, "metric shows a meaningful change from baseline"
    return 0.0, "metric shows no significant change from baseline"


def _log_corroboration(bundle: list[Evidence], weight: float) -> tuple[float, str]:
    logs = _find(bundle, "logs")
    count = logs.facts.get("count", 0) if logs else 0
    if count >= 2:
        return weight, f"{count} corroborating log occurrences beyond the triggering one"
    return 0.0, "fewer than 2 corroborating log occurrences"


def _missing_evidence(bundle: list[Evidence], weight: float) -> tuple[float, str]:
    present = {e.source for e in bundle}
    missing = {"logs", "trace", "git", "metric"} - present
    if not missing:
        return 0.0, "no missing evidence sources"
    return -weight * len(missing), f"missing evidence for: {', '.join(sorted(missing))}"


def _conflicting_evidence(
    bundle: list[Evidence], category: str, weight: float
) -> tuple[float, str]:
    hotspot = _dominant_hotspot(bundle)
    if hotspot is None:
        return 0.0, "no dominant hotspot to conflict with"
    hotspot_is_db = any(h in hotspot["name"].lower() for h in _DB_HINTS)
    if hotspot_is_db != (category == "DATABASE"):
        return -weight, f"hotspot {hotspot['name']} conflicts with RCA category {category}"
    return 0.0, "no conflict between trace hotspot and RCA category"


def score_confidence(state: InvestigationState) -> dict:
    """Deterministic, evidence-based score (doc section 8.3) — the LLM's own
    self-reported confidence (rca.llm_confidence) is recorded but never used
    here, on purpose: an LLM sounding certain and an LLM being correct aren't
    reliably the same thing."""
    rca = state["rca"]
    if rca is None:
        return {"confidence": ConfidenceScore(score=0.0, band="low", signals={})}

    policies = load_policies()["confidence"]
    weights = policies["weights"]
    bundle = state["evidence_bundle"]
    category = rca.category.value if hasattr(rca.category, "value") else rca.category

    checks = {
        "trace_hotspot": _trace_hotspot(bundle, category, weights["trace_hotspot"]),
        "code_location": _code_location(state, weights["code_location"]),
        "change_correlation": _change_correlation(bundle, rca, weights["change_correlation"]),
        "metric_corroboration": _metric_corroboration(bundle, weights["metric_corroboration"]),
        "log_corroboration": _log_corroboration(bundle, weights["log_corroboration"]),
        "missing_evidence": _missing_evidence(bundle, weights["missing_evidence_penalty"]),
        "conflicting_evidence": _conflicting_evidence(
            bundle, category, weights["conflicting_evidence_penalty"]
        ),
    }
    checks["historical_match"] = (0.0, "no knowledge base yet (Phase 9)")

    for name, (contribution, note) in checks.items():
        print(f"  [confidence] {name}: {contribution:+.2f} — {note}")

    signals = {name: contribution for name, (contribution, _note) in checks.items()}
    total = max(0.0, min(1.0, sum(signals.values())))
    if total >= policies["high"]:
        band = "high"
    elif total >= policies["medium"]:
        band = "medium"
    else:
        band = "low"

    return {"confidence": ConfidenceScore(score=round(total, 2), band=band, signals=signals)}
