from app.agents.prompts.classify import CLASSIFY_SYSTEM, build_classify_prompt
from app.agents.state import InvestigationState
from app.llm import get_chat_model
from app.models.rca import Category

# Keys are SHORT exception class names (`type(exc).__name__`), not fully-
# qualified paths — confirmed against real data (S03): OTel's logging
# instrumentation records exception_type as just "TimeoutError", never
# "sqlalchemy.exc.TimeoutError". A short name is a coarser, occasionally
# ambiguous signal (a plain built-in TimeoutError would also match) — that
# ambiguity is acceptable here because this table only exists to shortcut
# the obvious cases; anything it gets wrong or doesn't recognize still falls
# through to the LLM below, which is the actual safety net.
_RULES = {
    "TimeoutError": Category.DATABASE,
    "OperationalError": Category.DATABASE,
    "ReadTimeout": Category.DEPENDENCY,
    "ConnectTimeout": Category.DEPENDENCY,
    "ConnectError": Category.DEPENDENCY,
    "MemoryError": Category.MEMORY,
}


def classify(state: InvestigationState) -> dict:
    incident = state["incident"]
    rule_hit = _RULES.get(incident.exception_type or "")
    if rule_hit is not None:
        return {"classification": {"category": rule_hit.value, "method": "rule"}}

    model = get_chat_model(tier="fast")
    prompt = build_classify_prompt(incident.exception_type, incident.normalized_message)
    try:
        response = model.invoke([("system", CLASSIFY_SYSTEM), ("human", prompt)])
        text = str(response.content).strip().upper()
        category = text if text in Category.__members__ else Category.UNKNOWN.value
        return {"classification": {"category": category, "method": "llm"}}
    except Exception as exc:
        return {
            "classification": {"category": Category.UNKNOWN.value, "method": "llm"},
            "errors": [f"classify: {exc}"],
        }
