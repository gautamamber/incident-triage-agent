from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx


@dataclass
class ComponentTiming:
    name: str
    ms: float
    pct: float


@dataclass
class ErrorSpan:
    name: str
    exception_type: str | None
    message: str | None = None


@dataclass
class TraceSummary:
    trace_id: str
    root: str
    total_ms: float
    components: list[ComponentTiming] = field(default_factory=list)
    error_spans: list[ErrorSpan] = field(default_factory=list)


def _component_key(span: dict, resource_attrs: dict, is_root: bool) -> str:
    span_attrs = {a["key"]: a["value"] for a in span.get("attributes", [])}
    if "db.system" in span_attrs:
        return span_attrs["db.system"].get("stringValue", "database")
    if "http.url" in span_attrs:
        # An outbound call (e.g. to fraud-mock) — the span's own resource is
        # always the CALLER's service (this is a client-side span emitted by
        # payment-service's own httpx instrumentation), so falling back to
        # resource.service.name here would mislabel the call as the caller
        # itself, hiding that the time was spent in a downstream dependency.
        host = urlparse(span_attrs["http.url"]["stringValue"]).hostname
        if host:
            return host
    service = resource_attrs.get("service.name", {}).get("stringValue", "unknown")
    return f"{service} (self)" if is_root else service


def get_trace(tempo_url: str, trace_id: str) -> TraceSummary:
    """Trace duration + per-component percentage breakdown. Percentages, not
    raw spans — the RCA step reads "postgresql: 88%", not a wall of
    nanosecond timestamps.

    Uses each span's EXCLUSIVE duration (its own time minus its direct
    children's time), not raw span duration — summing raw durations
    double-counts: a parent span's wall time already includes everything its
    children spent, so parent and child both showing ~100% just because one
    child dominates the parent's time was a real bug here (found live, on
    S04 — a slow outbound call to fraud-mock and its parent request span
    both reported ~100%, diluting the actual signal)."""
    resp = httpx.get(f"{tempo_url}/api/traces/{trace_id}", timeout=10)
    resp.raise_for_status()
    data = resp.json()

    all_spans: list[tuple[dict, dict]] = []
    root_span_id = None
    root_start = None
    root_end = None

    for batch in data.get("batches", []):
        resource_attrs = {a["key"]: a["value"] for a in batch["resource"]["attributes"]}
        for scope_span in batch.get("scopeSpans", []):
            for span in scope_span.get("spans", []):
                all_spans.append((span, resource_attrs))
                if not span.get("parentSpanId"):
                    root_span_id = span["spanId"]
                    root_start = int(span["startTimeUnixNano"])
                    root_end = int(span["endTimeUnixNano"])

    if root_span_id is None:
        raise ValueError(f"trace {trace_id} has no root span")

    total_ns = root_end - root_start

    # Sum each span's DIRECT children's duration, so exclusive time can be
    # computed as own_duration - children_duration.
    children_ns: dict[str, int] = {}
    for span, _resource_attrs in all_spans:
        parent_id = span.get("parentSpanId")
        if parent_id:
            duration = int(span["endTimeUnixNano"]) - int(span["startTimeUnixNano"])
            children_ns[parent_id] = children_ns.get(parent_id, 0) + duration

    totals: dict[str, int] = {}
    error_spans: list[ErrorSpan] = []

    for span, resource_attrs in all_spans:
        duration_ns = int(span["endTimeUnixNano"]) - int(span["startTimeUnixNano"])
        exclusive_ns = max(0, duration_ns - children_ns.get(span["spanId"], 0))
        is_root = span["spanId"] == root_span_id
        key = _component_key(span, resource_attrs, is_root)
        totals[key] = totals.get(key, 0) + exclusive_ns

        status = span.get("status", {})
        if status.get("code") in ("STATUS_CODE_ERROR", 2):
            span_attrs = {a["key"]: a["value"] for a in span.get("attributes", [])}
            exc_type = span_attrs.get("exception.type", {}).get("stringValue")
            error_spans.append(
                ErrorSpan(name=span["name"], exception_type=exc_type, message=status.get("message"))
            )

    components = [
        ComponentTiming(name=name, ms=round(ns / 1e6, 2), pct=round(100 * ns / total_ns, 1))
        for name, ns in sorted(totals.items(), key=lambda kv: -kv[1])
        if ns > 0
    ]

    return TraceSummary(
        trace_id=trace_id,
        root=next(s["name"] for s, _ in all_spans if s["spanId"] == root_span_id),
        total_ms=round(total_ns / 1e6, 2),
        components=components,
        error_spans=error_spans,
    )
