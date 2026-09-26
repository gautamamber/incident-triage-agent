from typing import Any, Literal

from pydantic import BaseModel


class Evidence(BaseModel):
    id: str  # "E3" — stable ID the RCA step must cite
    source: Literal["logs", "trace", "metric", "git", "code", "knowledge"]
    summary: str  # one line, produced by code where possible
    facts: dict[str, Any]
    ref: str | None = None  # Grafana/Tempo URL, commit SHA, file:line
