from dataclasses import dataclass

import httpx


@dataclass
class MetricComparison:
    promql: str
    baseline_value: float | None
    incident_value: float | None
    change_ratio: float | None


def _instant_query(prometheus_url: str, promql: str, at_unix: float) -> float | None:
    resp = httpx.get(
        f"{prometheus_url}/api/v1/query",
        params={"query": promql, "time": at_unix},
        timeout=10,
    )
    resp.raise_for_status()
    result = resp.json()["data"]["result"]
    if not result:
        return None
    # scalar/vector result: [timestamp, "value string"]
    return float(result[0]["value"][1])


def query_metric(
    prometheus_url: str, promql: str, baseline_at: float, incident_at: float
) -> MetricComparison:
    """Compares one PromQL expression at two points in time — just before the
    incident vs during it (doc section 7.1's baseline_value/incident_value/
    change_ratio). Simplification vs the full doc spec: this samples two
    instants rather than averaging over two windows — good enough to show
    "did this jump," not precise enough for a real change-point detector."""
    baseline = _instant_query(prometheus_url, promql, baseline_at)
    incident = _instant_query(prometheus_url, promql, incident_at)

    ratio = None
    if baseline is not None and incident is not None and baseline != 0:
        ratio = round(incident / baseline, 2)

    return MetricComparison(
        promql=promql, baseline_value=baseline, incident_value=incident, change_ratio=ratio
    )
