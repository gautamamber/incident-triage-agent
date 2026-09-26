from app.agents.prompts.rca import RCA_SYSTEM, build_rca_prompt
from app.agents.state import InvestigationState
from app.llm import get_chat_model
from app.models.rca import RCA
from app.security.budget import extract_tokens


def _validate(rca: RCA, valid_ids: set[str]) -> list[str]:
    problems = []
    if len(rca.evidence_ids) < 2:
        problems.append("must cite at least 2 evidence_ids")
    unknown = [eid for eid in rca.evidence_ids if eid not in valid_ids]
    if unknown:
        problems.append(f"cites unknown evidence_ids: {unknown}")
    return problems


def rca_node(state: InvestigationState) -> dict:
    """Structured-output RCA, validated against the evidence bundle's real
    IDs, retried once on failure (doc section 6.1's VAL -> retry -> RCA loop).
    `include_raw=True` is only here to expose usage_metadata for the token
    budget (doc 11.7) — this loop is already bounded to 2 calls, so it's
    accounting, not active gating."""
    incident = state["incident"]
    bundle = state["evidence_bundle"]
    valid_ids = {item.id for item in bundle}

    model = get_chat_model(tier="strong").with_structured_output(RCA, include_raw=True)
    prompt = build_rca_prompt(incident, bundle)
    messages: list[tuple[str, str]] = [("system", RCA_SYSTEM), ("human", prompt)]

    tokens_used = 0
    problems: list[str] = []
    for attempt in range(2):
        try:
            response = model.invoke(messages)
        except Exception as exc:
            return {"errors": [f"rca: {exc}"], "token_usage": tokens_used}

        tokens_used += extract_tokens(response)
        if response["parsing_error"] is not None:
            return {"errors": [f"rca: {response['parsing_error']}"], "token_usage": tokens_used}
        result: RCA = response["parsed"]

        problems = _validate(result, valid_ids)
        if not problems:
            return {"rca": result, "token_usage": tokens_used}

        if attempt == 0:
            feedback = (
                "Your previous answer was invalid: "
                + "; ".join(problems)
                + f". Valid evidence IDs are: {sorted(valid_ids)}. Try again."
            )
            messages.append(("human", feedback))

    return {"errors": [f"rca: failed validation twice: {problems}"], "token_usage": tokens_used}
