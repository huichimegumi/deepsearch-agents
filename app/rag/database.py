"""PostgreSQL session and schema lifecycle helpers."""

from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.rag.config import get_rag_settings
from app.rag.models import Base


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(
        get_rag_settings().database_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_schema() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE chat_conversations ADD COLUMN IF NOT EXISTS summary TEXT DEFAULT ''")
        )
        connection.execute(
            text(
                "ALTER TABLE chat_conversations "
                "ADD COLUMN IF NOT EXISTS summary_message_count INTEGER DEFAULT 0"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE chat_conversations "
                "ADD COLUMN IF NOT EXISTS summary_updated_at TIMESTAMP WITH TIME ZONE"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_rag_chunk_lexical_fts "
                "ON rag_chunks USING gin (to_tsvector('simple', lexical_text))"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_user_memory_content_fts "
                "ON user_memories USING gin (to_tsvector('simple', content))"
            )
        )
