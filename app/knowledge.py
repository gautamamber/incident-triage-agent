import re
from pathlib import Path

from app.models.knowledge import KnowledgeHit

AGENT_ROOT = Path(__file__).resolve().parent.parent
RUNBOOKS_DIR = AGENT_ROOT / "knowledge" / "runbooks"
INCIDENTS_DIR = AGENT_ROOT / "knowledge" / "incidents"

_WORD_RE = re.compile(r"[a-z0-9_]+")


def _tokenize(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _load_documents() -> list[tuple[str, str, str]]:
    """(title, source_path, content) for every runbook and past-incident
    write-up. Runbooks are hand-written; incident write-ups accumulate over
    time via the write-back in worker.py — the knowledge base grows on its
    own as more incidents get resolved."""
    docs = []
    for directory in (RUNBOOKS_DIR, INCIDENTS_DIR):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            content = path.read_text()
            first_line = content.splitlines()[0] if content else path.stem
            title = first_line.lstrip("#").strip() or path.stem
            docs.append((title, str(path.relative_to(AGENT_ROOT)), content))
    return docs


def search_knowledge(query: str, top_k: int = 2, min_score: float = 0.3) -> list[KnowledgeHit]:
    """Keyword-overlap search — the doc's own sequencing (section 2's
    decision table) is 'runbooks loaded directly / keyword search first, add
    pgvector when the knowledge base grows.' Score = fraction of the query's
    words found in the document; nothing fancier than that until there's
    enough content for plain keyword matching to start missing things."""
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    hits = []
    for title, source, content in _load_documents():
        doc_tokens = _tokenize(content)
        overlap = query_tokens & doc_tokens
        score = len(overlap) / len(query_tokens)
        if score >= min_score:
            excerpt = " ".join(content.strip().splitlines()[:6])[:300]
            hits.append(
                KnowledgeHit(title=title, source=source, excerpt=excerpt, score=round(score, 2))
            )

    hits.sort(key=lambda h: -h.score)
    return hits[:top_k]
