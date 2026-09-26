"""Proves every evidence builder redacts free text before it becomes part of
an Evidence object — not just the one field each builder happened to redact
before. Found live during the Phase 11 security review: build_log_evidence's
summary, build_trace_evidence's error_spans, and build_git_evidence's
non-latest commit messages all bypassed redaction entirely."""

from datetime import UTC, datetime

from app import evidence as evidence_module
from app.models.incident import IncidentSnapshot
from app.tools.git_repo import CommitInfo
from app.tools.loki import LogRecord
from app.tools.tempo import ComponentTiming, ErrorSpan, TraceSummary

SECRET_EMAIL = "leaked-user@example.com"
SECRET_TOKEN = "Bearer sk-proj-verySecretToken123"


def _incident(**overrides) -> IncidentSnapshot:
    base = dict(
        id=1,
        key="INC-0001",
        fingerprint="fp123",
        service="payment-service",
        severity="P2",
        status="OPEN",
        exception_type="ValueError",
        normalized_message=f"failed: {SECRET_EMAIL}",
        sample_message="failed",
        top_frame="app/api/payments.py:refund_payment",
        first_seen=datetime.now(UTC),
        last_seen=datetime.now(UTC),
        error_count=5,
        sample_trace_ids=["trace123"],
        affected_routes=[],
    )
    base.update(overrides)
    return IncidentSnapshot(**base)


def test_build_log_evidence_redacts_the_summary_line(monkeypatch):
    incident = _incident()
    record = LogRecord(
        timestamp_ns=1,
        service_name="payment-service",
        severity_text="ERROR",
        body=f"lookup failed for {SECRET_EMAIL}",
        exception_type="ValueError",
        top_frame=incident.top_frame,
        trace_id="trace123",
    )
    monkeypatch.setattr(evidence_module.loki, "search_logs", lambda *a, **k: [record])
    monkeypatch.setattr(
        evidence_module, "compute_fingerprint", lambda *a, **k: incident.fingerprint
    )

    result = evidence_module.build_log_evidence(incident)
    assert result is not None
    assert SECRET_EMAIL not in result.summary
    assert SECRET_EMAIL not in " ".join(result.facts["sample_lines"])


def test_build_trace_evidence_redacts_error_span_messages(monkeypatch):
    incident = _incident()
    trace = TraceSummary(
        trace_id="trace123",
        root="POST /payments",
        total_ms=12.0,
        components=[ComponentTiming(name="payment-service", ms=12.0, pct=100.0)],
        error_spans=[
            ErrorSpan(
                name="refund", exception_type="ValueError", message=f"bad token: {SECRET_TOKEN}"
            )
        ],
    )
    monkeypatch.setattr(evidence_module.tempo, "get_trace", lambda *a, **k: trace)

    result = evidence_module.build_trace_evidence(incident)
    assert result is not None
    assert SECRET_TOKEN not in str(result.facts["error_spans"])
    assert "<secret>" in result.facts["error_spans"][0]["message"]


def test_build_git_evidence_redacts_every_commit_message_not_just_the_latest(monkeypatch):
    incident = _incident()
    monkeypatch.setattr(
        evidence_module,
        "get_service",
        lambda service: type("S", (), {"repo_path": "/tmp/fake-repo"})(),
    )
    commits = [
        CommitInfo(
            sha="aaa111", author="a", timestamp="t1",
            message="fix refund bug", files=["app/api/payments.py"],
        ),
        CommitInfo(
            sha="bbb222", author="b", timestamp="t2",
            message=f"debug commit, leaked {SECRET_EMAIL} in commit body",
            files=["app/api/payments.py"],
        ),
    ]  # fmt: skip
    monkeypatch.setattr(evidence_module.git_repo, "recent_commits", lambda *a, **k: commits)

    result = evidence_module.build_git_evidence(incident)
    assert result is not None
    assert SECRET_EMAIL not in str(result.facts["commits"])
    assert result.facts["commits"][1]["message"] != commits[1].message
