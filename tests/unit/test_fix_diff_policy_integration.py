"""Proves the retry loop's WIRING to diff_policy, not the policy logic
itself (already unit-tested 8/8 in test_diff_policy.py). A live LLM won't
reliably produce a policy-violating diff on demand — it either writes a
compliant one or a syntactically broken one (confirmed live against
INC-0039) — so this mocks just the two model calls to prove: a rejected
diff is recorded with its rejection reasons, the loop retries instead of
giving up, and a subsequent compliant diff still reaches _publish."""

from unittest.mock import MagicMock

from app.agents.nodes import fix as fix_module
from app.models.rca import RCA, Category, FixStrategy
from app.tools.sandbox import SandboxResult

BAD_DIFF = (
    "diff --git a/pyproject.toml b/pyproject.toml\n"
    "--- a/pyproject.toml\n+++ b/pyproject.toml\n@@ -1,1 +1,2 @@\n+evil = 1\n"
)
GOOD_DIFF = (
    "diff --git a/app/api/payments.py b/app/api/payments.py\n"
    "--- a/app/api/payments.py\n+++ b/app/api/payments.py\n@@ -1,1 +1,2 @@\n+# fixed\n"
)


def _rca() -> RCA:
    return RCA(
        root_cause="test root cause",
        category=Category.APPLICATION,
        affected_component="app/api/payments.py:refund_payment",
        causal_chain=["a", "b"],
        evidence_ids=["E1", "E2"],
        fix_strategy=FixStrategy.CODE_CHANGE,
        recommended_action="fix it",
        llm_confidence=0.8,
    )


def test_diff_policy_rejection_triggers_retry_then_succeeds(monkeypatch, tmp_path):
    repo_path = tmp_path / "repo"
    scratch_dir = tmp_path / "scratch"
    repo_path.mkdir()
    scratch_dir.mkdir()

    repro_structured = MagicMock()
    repro_structured.invoke.return_value = {
        "parsed": fix_module.ReproTestOutput(test_code="def test_bug():\n    assert False\n"),
        "raw": None,
        "parsing_error": None,
    }
    patch_structured = MagicMock()
    patch_structured.invoke.side_effect = [
        {
            "parsed": fix_module.PatchOutput(unified_diff=BAD_DIFF),
            "raw": None,
            "parsing_error": None,
        },
        {
            "parsed": fix_module.PatchOutput(unified_diff=GOOD_DIFF),
            "raw": None,
            "parsing_error": None,
        },
    ]

    fake_model = MagicMock()
    fake_model.with_structured_output.side_effect = lambda schema, include_raw=False: (
        repro_structured if schema is fix_module.ReproTestOutput else patch_structured
    )
    monkeypatch.setattr(fix_module, "get_chat_model", lambda tier="fast": fake_model)

    sandbox_calls: list[str] = []

    def fake_run_in_sandbox(scratch, image_tag, command_id, file=None):
        sandbox_calls.append(command_id)
        if command_id == "pytest_file" and len(sandbox_calls) == 1:
            return SandboxResult(command_id=command_id, returncode=1, stdout="", stderr="fails")
        return SandboxResult(command_id=command_id, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(fix_module, "run_in_sandbox", fake_run_in_sandbox)
    monkeypatch.setattr(fix_module.repo_write, "apply_patch", lambda *a, **k: None)

    published = {}

    def fake_publish(changes, incident, rca, confidence, strategy, attempts, evidence_bundle):
        published["changes"] = changes
        published["attempts"] = attempts
        return fix_module.FixResult(
            outcome=fix_module.FixOutcome.DRAFT_PR_OPENED, strategy=strategy.value
        )

    monkeypatch.setattr(fix_module, "_publish", fake_publish)

    incident = MagicMock(key="INC-TEST01", service="payment-service")
    result, tokens = fix_module._run_code_change(
        repo_path, scratch_dir, "fake-image:tag", incident, _rca(),
        MagicMock(score=0.8, band="high"), evidence_bundle=[], max_attempts=3,
        attempts=[], run_started_at=None, tokens_so_far=0,
    )  # fmt: skip

    assert result.outcome == fix_module.FixOutcome.DRAFT_PR_OPENED
    rejected, accepted = published["attempts"]
    assert rejected.diff_policy_ok is False
    assert any("pyproject.toml" in r for r in rejected.diff_policy_reasons)
    assert accepted.diff_policy_ok is True
    assert accepted.tests_passed is True
    assert accepted.ruff_passed is True


def test_diff_policy_rejection_exhausts_attempts_when_every_patch_is_bad(monkeypatch, tmp_path):
    repo_path = tmp_path / "repo"
    scratch_dir = tmp_path / "scratch"
    repo_path.mkdir()
    scratch_dir.mkdir()

    repro_structured = MagicMock()
    repro_structured.invoke.return_value = {
        "parsed": fix_module.ReproTestOutput(test_code="def test_bug():\n    assert False\n"),
        "raw": None,
        "parsing_error": None,
    }
    patch_structured = MagicMock()
    patch_structured.invoke.return_value = {
        "parsed": fix_module.PatchOutput(unified_diff=BAD_DIFF),
        "raw": None,
        "parsing_error": None,
    }

    fake_model = MagicMock()
    fake_model.with_structured_output.side_effect = lambda schema, include_raw=False: (
        repro_structured if schema is fix_module.ReproTestOutput else patch_structured
    )
    monkeypatch.setattr(fix_module, "get_chat_model", lambda tier="fast": fake_model)
    monkeypatch.setattr(
        fix_module,
        "run_in_sandbox",
        lambda scratch, image_tag, command_id, file=None: SandboxResult(
            command_id=command_id, returncode=1, stdout="", stderr="fails"
        ),
    )

    incident = MagicMock(key="INC-TEST02", service="payment-service")
    result, tokens = fix_module._run_code_change(
        repo_path, scratch_dir, "fake-image:tag", incident, _rca(),
        MagicMock(score=0.8, band="high"), evidence_bundle=[], max_attempts=3,
        attempts=[], run_started_at=None, tokens_so_far=0,
    )  # fmt: skip

    assert result.outcome == fix_module.FixOutcome.NEEDS_HUMAN
    assert len(result.attempts) == 3
    assert all(not a.diff_policy_ok for a in result.attempts)
