from app.policies import load_policies


def score_severity(
    error_count_5m: int,
    error_ratio: float | None = None,
    critical_route_failing: bool = False,
) -> str:
    """Deterministic severity (architecture doc section 5.5). `error_ratio` is
    optional for now — computing it needs a Prometheus query for total request
    volume in the same window, which the detector doesn't do yet (log-only in
    Phase 3). Count-based thresholds alone are enough for S01/S06; ratio gets
    wired in once the detector also reads Prometheus."""
    policies = load_policies()["severity"]
    p1 = policies["p1"]
    p2 = policies["p2"]

    ratio_breaches_p1 = error_ratio is not None and error_ratio > p1["error_ratio"]
    ratio_breaches_p2 = error_ratio is not None and error_ratio > p2["error_ratio"]

    if critical_route_failing:
        return "P1"
    if error_count_5m > p1["errors_5m"] or ratio_breaches_p1:
        return "P1"
    if error_count_5m > p2["errors_5m"] or ratio_breaches_p2:
        return "P2"
    return "P3"
