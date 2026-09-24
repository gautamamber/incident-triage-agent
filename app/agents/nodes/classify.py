from app.agents.prompts.classify import CLASSIFY_SYSTEM, build_classify_prompt
from app.agents.state import InvestigationState
from app.llm import get_chat_model
from app.models.rca import Category

# Deliberately narrow and unambiguous — anything not covered here (like our
# S01 AttributeError) is exactly the case meant to fall through to the LLM
# (doc section 6.3: "only if no rule matches, a cheap LLM call picks").
_RULES = {
    "sqlalchemy.exc.TimeoutError": Category.DATABASE,
    "sqlalchemy.exc.OperationalError": Category.DATABASE,
    "psycopg.OperationalError": Category.DATABASE,
    "httpx.ReadTimeout": Category.DEPENDENCY,
    "httpx.ConnectTimeout": Category.DEPENDENCY,
    "httpx.ConnectError": Category.DEPENDENCY,
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
