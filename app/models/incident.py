import enum
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import BigInteger, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class IncidentStatus(enum.StrEnum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RCA_READY = "RCA_READY"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    FIX_PROPOSED = "FIX_PROPOSED"
    RESOLVED = "RESOLVED"
    REOPENED = "REOPENED"


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fingerprint: Mapped[str] = mapped_column(String(40), index=True)
    service: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(2))
    status: Mapped[str] = mapped_column(String(20), default=IncidentStatus.OPEN.value)

    exception_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    normalized_message: Mapped[str] = mapped_column(String)
    sample_message: Mapped[str] = mapped_column(String)
    top_frame: Mapped[str | None] = mapped_column(String(300), nullable=True)

    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    error_count: Mapped[int] = mapped_column(Integer, default=0)

    sample_trace_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    affected_routes: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    category: Mapped[str | None] = mapped_column(String(20), nullable=True)
    rca_json: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_band: Mapped[str | None] = mapped_column(String(10), nullable=True)

    @property
    def key(self) -> str:
        return f"INC-{self.id:04d}"


class IncidentSnapshot(BaseModel):
    """Plain, DB-session-free copy of an Incident row — what actually flows
    through the LangGraph state. The ORM object stays with the worker; nodes
    only ever see this snapshot, so nothing breaks if the session closes or
    the state gets checkpointed/serialized later."""

    model_config = {"from_attributes": True}

    id: int
    key: str
    fingerprint: str
    service: str
    severity: str
    status: str
    exception_type: str | None
    normalized_message: str
    sample_message: str
    top_frame: str | None
    first_seen: datetime
    last_seen: datetime
    error_count: int
    sample_trace_ids: list[str]
    affected_routes: list[str]


class OccurrenceBucket(Base):
    """One row per (fingerprint, 1-minute bucket). The aggregator upserts into
    this and sums recent rows to check the open-incident threshold (section 5.3)."""

    __tablename__ = "occurrence_buckets"
    __table_args__ = (
        UniqueConstraint("fingerprint", "bucket_start", name="uq_fingerprint_bucket"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fingerprint: Mapped[str] = mapped_column(String(40), index=True)
    service: Mapped[str] = mapped_column(String(100))
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    count: Mapped[int] = mapped_column(Integer, default=0)


class DetectorCursor(Base):
    """Single row (id='loki') tracking the last processed timestamp, so a
    restart resumes instead of reprocessing or skipping data (section 5.1)."""

    __tablename__ = "detector_cursor"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    last_timestamp_ns: Mapped[int] = mapped_column(BigInteger)


class AgentRunLog(Base):
    """One row per investigation the worker actually starts — a durable
    counter across process restarts, since each `run_once` invocation is its
    own short-lived process, not a long-running loop with in-memory state to
    rate-limit against."""

    __tablename__ = "agent_run_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
