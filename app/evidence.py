from datetime import timedelta

from app.config import settings
from app.detector.fingerprint import fingerprint as compute_fingerprint
from app.models.evidence import Evidence
from app.models.incident import Incident, IncidentSnapshot
from app.security.redaction import redact
from app.services.repo_registry import get_service
from app.tools import git_repo, loki, prometheus, tempo

IncidentLike = Incident | IncidentSnapshot

# Fixed source order used when the fuse step assigns final E1/E2/E3... IDs —
# keeps the numbering stable and readable regardless of which parallel
# collector happens to finish first.
_SOURCE_ORDER = ["logs", "trace", "git", "metric", "code", "knowledge"]


def renumber_evidence(items: list[Evidence]) -> list[Evidence]:
    """Assigns final sequential IDs (E1, E2, ...) after all evidence has been
    collected. Collectors themselves don't know the final ID — if they ran in
    parallel (section 6.1's fan-out), none of them knows what the others
    produced yet. This runs once, after the fan-in, exactly like the doc's
    separate `build_evidence_bundle` node."""
    ordered = sorted(items, key=lambda e: _SOURCE_ORDER.index(e.source))
    return [item.model_copy(update={"id": f"E{i + 1}"}) for i, item in enumerate(ordered)]


def build_log_evidence(incident: IncidentLike) -> Evidence | None:
    start_ns = int((incident.first_seen - timedelta(minutes=10)).timestamp() * 1e9)
    end_ns = int(incident.last_seen.timestamp() * 1e9)
    records = loki.search_logs(
        settings.loki_url, incident.service, start_ns, end_ns, level="ERROR|FATAL"
    )
    matching = [
        r
        for r in records
        if compute_fingerprint(r.service_name, r.exception_type, r.body, r.top_frame)
        == incident.fingerprint
    ]
    if not matching:
        return None
    return Evidence(
        id="",
        source="logs",
        # normalized_message is regex-normalized (IDs/UUIDs stripped) but not
        # redacted — a free-text field a request can set (e.g. a "reason"
        # query param) survives normalization untouched, so this still needs
        # its own redaction pass, same as the sample lines below.
        summary=redact(
            f"{len(matching)} occurrences of '{incident.normalized_message}' in the last 10 min"
        ),
        facts={"count": len(matching), "sample_lines": [redact(r.body) for r in matching[:3]]},
    )


def build_trace_evidence(incident: IncidentLike) -> Evidence | None:
    if not incident.sample_trace_ids:
        return None
    trace_id = incident.sample_trace_ids[0]
    try:
        trace = tempo.get_trace(settings.tempo_url, trace_id)
    except Exception as exc:
        return Evidence(id="", source="trace", summary=f"trace lookup failed: {exc}", facts={})

    hotspot = trace.components[0] if trace.components else None
    summary = f"trace {trace.trace_id[:12]}...: {trace.total_ms}ms total"
    if hotspot:
        summary += f", {hotspot.name} {hotspot.pct}% ({hotspot.ms}ms)"
    return Evidence(
        id="",
        source="trace",
        summary=summary,
        facts={
            "total_ms": trace.total_ms,
            "components": [c.__dict__ for c in trace.components],
            # error_spans.message is an exception message — the same class
            # of user-reachable free text doc 11.1's threat model calls out
            # ("A user submits ... it is logged and reaches the LLM").
            "error_spans": [
                {**e.__dict__, "message": redact(e.message) if e.message else e.message}
                for e in trace.error_spans
            ],
        },
        ref=f"{settings.tempo_url}/api/traces/{trace.trace_id}",
    )


def build_metric_evidence(incident: IncidentLike) -> Evidence:
    promql = (
        f'sum(rate(http_server_duration_milliseconds_count{{exported_job="{incident.service}"}}[2m]))'
    )
    baseline_at = incident.first_seen.timestamp() - 300
    incident_at = incident.last_seen.timestamp()
    try:
        comparison = prometheus.query_metric(
            settings.prometheus_url, promql, baseline_at, incident_at
        )
        summary = (
            f"request rate baseline={comparison.baseline_value} "
            f"incident={comparison.incident_value} ratio={comparison.change_ratio}"
        )
        facts = {
            "promql": promql,
            "baseline_value": comparison.baseline_value,
            "incident_value": comparison.incident_value,
            "change_ratio": comparison.change_ratio,
        }
    except Exception as exc:
        summary = f"metric lookup failed: {exc}"
        facts = {}
    return Evidence(id="", source="metric", summary=summary, facts=facts)


def build_git_evidence(incident: IncidentLike) -> Evidence | None:
    try:
        service_cfg = get_service(incident.service)
    except (KeyError, ValueError):
        return None

    path = None
    if incident.top_frame:
        path = incident.top_frame.split(":")[0]

    commits = git_repo.recent_commits(
        service_cfg.repo_path, since_hours=48, paths=[path] if path else None
    )
    if not commits:
        return None

    latest = commits[0]
    return Evidence(
        id="",
        source="git",
        summary=(
            f"commit {latest.sha[:8]} '{redact(latest.message)}' by {latest.author} "
            f"touched {path or 'the affected file'}, {latest.timestamp}"
        ),
        # Only `latest.message` was redacted above (for the summary line) —
        # every OTHER commit's message here was going into the LLM prompt
        # completely unredacted (a commit message is exactly the kind of
        # free text someone can accidentally paste a secret into).
        facts={"commits": [{**c.__dict__, "message": redact(c.message)} for c in commits]},
        ref=latest.sha,
    )


def build_evidence_bundle(incident: IncidentLike) -> list[Evidence]:
    """Sequential convenience wrapper for the debug CLI (Phase 4) — the worker
    (Phase 5) instead runs these same builder functions as parallel graph
    nodes and calls renumber_evidence() once they've all finished."""
    raw = []
    for builder in (build_log_evidence, build_trace_evidence, build_git_evidence):
        item = builder(incident)
        if item is not None:
            raw.append(item)
    raw.append(build_metric_evidence(incident))
    return renumber_evidence(raw)
