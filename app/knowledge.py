import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.embeddings import embed
from app.models.knowledge import KnowledgeHit
from app.models.knowledge_document import KnowledgeDocument

AGENT_ROOT = Path(__file__).resolve().parent.parent
RUNBOOKS_DIR = AGENT_ROOT / "knowledge" / "runbooks"
INCIDENTS_DIR = AGENT_ROOT / "knowledge" / "incidents"

_WORD_RE = re.compile(r"[a-z0-9_]+")


def _tokenize(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _excerpt(content: str) -> str:
    return " ".join(content.strip().splitlines()[:6])[:300]


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


def _keyword_scores(query: str) -> dict[str, tuple[str, str, float]]:
    """source -> (title, excerpt, score). Score = fraction of the query's
    words found in the document — the doc's own sequencing (section 2's
    decision table) starts here before adding vector search."""
    query_tokens = _tokenize(query)
    if not query_tokens:
        return {}

    scores = {}
    for title, source, content in _load_documents():
        overlap = query_tokens & _tokenize(content)
        score = len(overlap) / len(query_tokens)
        scores[source] = (title, _excerpt(content), score)
    return scores


def search_knowledge(query: str, top_k: int = 2, min_score: float = 0.3) -> list[KnowledgeHit]:
    """Keyword-only search — no DB needed, works standalone."""
    hits = [
        KnowledgeHit(title=title, source=source, excerpt=excerpt, score=round(score, 2))
        for source, (title, excerpt, score) in _keyword_scores(query).items()
        if score >= min_score
    ]
    hits.sort(key=lambda h: -h.score)
    return hits[:top_k]


def reindex_knowledge(db: Session) -> int:
    """(Re)computes embeddings for every runbook/incident doc and upserts
    them into knowledge_documents. Called whenever the knowledge base
    changes — cheap enough (a handful of small files) to just always
    recompute rather than tracking what changed."""
    count = 0
    for title, source, content in _load_documents():
        embedding = embed(f"{title} {content}")
        existing = db.get(KnowledgeDocument, source)
        if existing:
            existing.title = title
            existing.content = content
            existing.embedding = embedding
        else:
            db.add(
                KnowledgeDocument(source=source, title=title, content=content, embedding=embedding)
            )
        count += 1
    db.commit()
    return count


def hybrid_search(
    db: Session, query: str, top_k: int = 2, min_score: float = 0.3
) -> list[KnowledgeHit]:
    """Keyword score (exact word overlap) blended 50/50 with vector
    similarity (catches paraphrases the keyword pass would miss — the whole
    point of adding this once keyword-only search starts leaving things on
    the table). Falls back to keyword-only if the vector index is empty or
    unreachable, so this never hard-fails the graph over a DB hiccup."""
    keyword = _keyword_scores(query)

    vector_scores: dict[str, tuple[str, str, float]] = {}
    try:
        query_embedding = embed(query)
        rows = db.execute(
            select(
                KnowledgeDocument.source,
                KnowledgeDocument.title,
                KnowledgeDocument.content,
                KnowledgeDocument.embedding.cosine_distance(query_embedding).label("distance"),
            )
            .order_by("distance")
            .limit(10)
        ).all()
        for source, title, content, distance in rows:
            vector_scores[source] = (title, _excerpt(content), max(0.0, 1 - distance))
    except Exception:
        pass  # no index yet, or DB unreachable — keyword-only result is still valid

    if not vector_scores:
        return search_knowledge(query, top_k=top_k, min_score=min_score)

    all_sources = set(keyword) | set(vector_scores)
    hits = []
    for source in all_sources:
        title, excerpt, kw_score = keyword.get(source, ("", "", 0.0))
        v_title, v_excerpt, vec_score = vector_scores.get(source, ("", "", 0.0))
        blended = 0.5 * kw_score + 0.5 * vec_score
        if blended >= min_score:
            hits.append(
                KnowledgeHit(
                    title=title or v_title,
                    source=source,
                    excerpt=excerpt or v_excerpt,
                    score=round(blended, 2),
                )
            )

    hits.sort(key=lambda h: -h.score)
    return hits[:top_k]
