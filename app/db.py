from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

engine = create_engine(settings.agent_database_url, pool_size=5, max_overflow=5)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def checkpointer_conn_string() -> str:
    # langgraph's PostgresSaver wants a plain psycopg DSN, not SQLAlchemy's
    # dialect+driver URL style (`postgresql+psycopg://`).
    return settings.agent_database_url.replace("postgresql+psycopg://", "postgresql://")


def init_db() -> None:
    from langgraph.checkpoint.postgres import PostgresSaver

    from app.models import incident  # noqa: F401 — import registers the tables on Base

    Base.metadata.create_all(bind=engine)

    with PostgresSaver.from_conn_string(checkpointer_conn_string()) as checkpointer:
        checkpointer.setup()  # idempotent — creates its tables only if missing
