from dataclasses import dataclass, field

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


@dataclass
class TraceSummary:
    trace_id: str
    root: str
    total_ms: float
    components: list[ComponentTiming] = field(default_factory=list)
    error_spans: list[ErrorSpan] = field(default_factory=list)


def _component_key(span: dict, resource_attrs: dict) -> str:
    span_attrs = {a["key"]: a["value"] for a in span.get("attributes", [])}
    if "db.system" in span_attrs:
        return span_attrs["db.system"].get("stringValue", "database")
    service = resource_attrs.get("service.name", {}).get("stringValue", "unknown")
    if span.get("parentSpanId") is None:
        return f"{service} (self)"
    return service


def get_trace(tempo_url: str, trace_id: str) -> TraceSummary:
    """Trace duration + per-component percentage breakdown (doc section 7.1's
    worked example). Percentages, not raw spans — the RCA step (Phase 5+)
    reads "postgresql: 88%", not a wall of nanosecond timestamps."""
    resp = httpx.get(f"{tempo_url}/api/traces/{trace_id}", timeout=10)
    resp.raise_for_status()
    data = resp.json()

    all_spans: list[tuple[dict, dict]] = []
    root_span = None
    root_start = None
    root_end = None

    for batch in data.get("batches", []):
        resource_attrs = {a["key"]: a["value"] for a in batch["resource"]["attributes"]}
        for scope_span in batch.get("scopeSpans", []):
            for span in scope_span.get("spans", []):
                all_spans.append((span, resource_attrs))
                if not span.get("parentSpanId"):
                    root_span = span
                    root_start = int(span["startTimeUnixNano"])
                    root_end = int(span["endTimeUnixNano"])

    if root_span is None:
        raise ValueError(f"trace {trace_id} has no root span")

    total_ns = root_end - root_start
    totals: dict[str, int] = {}
    error_spans: list[ErrorSpan] = []

    for span, resource_attrs in all_spans:
        duration_ns = int(span["endTimeUnixNano"]) - int(span["startTimeUnixNano"])
        key = _component_key(span, resource_attrs)
        totals[key] = totals.get(key, 0) + duration_ns

        status = span.get("status", {})
        if status.get("code") == "STATUS_CODE_ERROR" or status.get("code") == 2:
            span_attrs = {a["key"]: a["value"] for a in span.get("attributes", [])}
            exc_type = span_attrs.get("exception.type", {}).get("stringValue")
            error_spans.append(ErrorSpan(name=span["name"], exception_type=exc_type))

    components = [
        ComponentTiming(name=name, ms=round(ns / 1e6, 2), pct=round(100 * ns / total_ns, 1))
        for name, ns in sorted(totals.items(), key=lambda kv: -kv[1])
    ]

    return TraceSummary(
        trace_id=trace_id,
        root=root_span["name"],
        total_ms=round(total_ns / 1e6, 2),
        components=components,
        error_spans=error_spans,
    )
