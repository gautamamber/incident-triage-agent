import enum

from pydantic import BaseModel, Field


class FixOutcome(enum.StrEnum):
    DRAFT_PR_OPENED = "draft_pr_opened"
    NEEDS_HUMAN = "needs_human"


class FixAttempt(BaseModel):
    attempt: int
    diff: str
    diff_policy_ok: bool
    diff_policy_reasons: list[str] = Field(default_factory=list)
    # None for the revert strategy, which has no repro test — only set for
    # code_change, and only True (a repro test that never failed pre-patch
    # never reaches this far; see fix.py's pre-check).
    repro_test_failed_before: bool | None = None
    tests_passed: bool
    ruff_passed: bool
    failure_output: str = ""


class FixResult(BaseModel):
    outcome: FixOutcome
    strategy: str
    branch: str | None = None
    pr_url: str | None = None
    attempts: list[FixAttempt] = Field(default_factory=list)
    give_up_reason: str | None = None
