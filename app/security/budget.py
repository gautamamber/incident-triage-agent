from datetime import UTC, datetime
from typing import Any


def extract_tokens(response: Any) -> int:
    """Best-effort total-token count from either a plain langchain AIMessage
    or a `with_structured_output(..., include_raw=True)` result (a dict with
    'raw'/'parsed'/'parsing_error'). Returns 0 if the provider/response
    doesn't expose usage — a missing count must never itself abort a run;
    budgets gate cost, they aren't a new failure mode of their own."""
    if isinstance(response, dict):
        response = response.get("raw")
    usage = getattr(response, "usage_metadata", None) if response is not None else None
    if not usage:
        return 0
    return usage.get("total_tokens") or 0


def wall_time_exceeded(started_at_iso: str | None, max_seconds: int) -> bool:
    if not started_at_iso:
        return False
    started = datetime.fromisoformat(started_at_iso)
    return (datetime.now(UTC) - started).total_seconds() > max_seconds


def token_budget_exceeded(tokens_used_so_far: int, max_tokens: int) -> bool:
    return tokens_used_so_far >= max_tokens
