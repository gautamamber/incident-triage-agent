from pydantic import BaseModel


class CodeFinding(BaseModel):
    summary: str
    file: str | None = None
    detail: str


class CodeFindingsList(BaseModel):
    """Wrapper so the investigation loop's wrap-up call can ask for structured
    output directly — a free-text summary split by newline was the first
    attempt and it was a real mess (markdown headers, code fences and blank
    lines each became their own "finding")."""

    findings: list[CodeFinding]
