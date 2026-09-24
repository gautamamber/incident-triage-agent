import enum

from pydantic import BaseModel, Field


class Category(enum.StrEnum):
    DATABASE = "DATABASE"
    API = "API"
    NETWORK = "NETWORK"
    MEMORY = "MEMORY"
    CPU = "CPU"
    DEPENDENCY = "DEPENDENCY"
    APPLICATION = "APPLICATION"
    UNKNOWN = "UNKNOWN"


class FixStrategy(enum.StrEnum):
    REVERT_COMMIT = "revert_commit"
    CODE_CHANGE = "code_change"
    CONFIG_CHANGE = "config_change"
    NO_CODE_FIX = "no_code_fix"
    UNKNOWN = "unknown"


class AlternativeHypothesis(BaseModel):
    hypothesis: str
    why_less_likely: str


class RCA(BaseModel):
    root_cause: str = Field(description="One or two sentences: what actually went wrong.")
    category: Category
    affected_component: str = Field(
        description="file:function most responsible, e.g. 'app/api/payments.py:refund_payment'"
    )
    causal_chain: list[str] = Field(description="symptom -> ... -> root cause, as short steps")
    evidence_ids: list[str] = Field(
        description="Evidence IDs (e.g. 'E1', 'E3') that support this RCA. Must cite at least 2."
    )
    alternative_hypotheses: list[AlternativeHypothesis] = Field(default_factory=list)
    fix_strategy: FixStrategy
    suspect_commit: str | None = Field(
        default=None, description="Full commit SHA from the git evidence, if one caused this."
    )
    recommended_action: str
    unknowns: list[str] = Field(default_factory=list, description="What could not be verified.")
    # No ge=/le= here on purpose: those compile to JSON Schema minimum/maximum,
    # which this project's Bedrock-backed gateway rejects for structured
    # output ("properties maximum, minimum are not supported"). The prompt
    # asks for a 0-1 value; this field is advisory only, never used for
    # gating, so an unclamped float is harmless.
    llm_confidence: float = Field(
        description="Your own confidence, roughly 0-1 — recorded only, never used for gating."
    )
