from pydantic import BaseModel


class KnowledgeHit(BaseModel):
    title: str
    source: str  # file path, relative to the agent repo root
    excerpt: str
    score: float
