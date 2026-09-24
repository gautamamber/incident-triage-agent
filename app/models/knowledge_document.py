from pgvector.sqlalchemy import Vector
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.embeddings import DIMENSIONS


class KnowledgeDocument(Base):
    """One row per indexed runbook/incident write-up — content plus its
    embedding, so pgvector can do a similarity search over it. Populated by
    reindex_knowledge(); read by hybrid_search()."""

    __tablename__ = "knowledge_documents"

    source: Mapped[str] = mapped_column(String(300), primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(String)
    embedding: Mapped[list[float]] = mapped_column(Vector(DIMENSIONS))
