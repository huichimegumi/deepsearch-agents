"""Environment-backed configuration for the local RAG stack."""

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())


@dataclass(frozen=True)
class RagSettings:
    database_url: str
    redis_url: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    minio_secure: bool
    qdrant_url: str
    qdrant_api_key: str | None
    qdrant_collection: str
    memory_qdrant_collection: str
    embedding_model: str
    rerank_model: str
    chunk_size: int
    chunk_overlap: int
    vector_top_k: int
    lexical_top_k: int
    rerank_top_k: int
    memory_top_k: int
    memory_min_confidence: float
    short_term_memory_backend: str
    short_term_memory_database_url: str | None
    short_term_memory_pool_size: int
    short_term_memory_fallback_enabled: bool


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_rag_settings() -> RagSettings:
    return RagSettings(
        database_url=os.getenv(
            "RAG_DATABASE_URL",
            "postgresql+psycopg://deepsearch:deepsearch@localhost:5432/deepsearch_rag",
        ),
        redis_url=os.getenv("RAG_REDIS_URL", "redis://localhost:6379/0"),
        minio_endpoint=os.getenv("RAG_MINIO_ENDPOINT", "localhost:9000"),
        minio_access_key=os.getenv("RAG_MINIO_ACCESS_KEY", "deepsearch"),
        minio_secret_key=os.getenv("RAG_MINIO_SECRET_KEY", "deepsearch-secret"),
        minio_bucket=os.getenv("RAG_MINIO_BUCKET", "knowledge-documents"),
        minio_secure=_as_bool(os.getenv("RAG_MINIO_SECURE")),
        qdrant_url=os.getenv("RAG_QDRANT_URL", "http://localhost:6333"),
        qdrant_api_key=os.getenv("RAG_QDRANT_API_KEY") or None,
        qdrant_collection=os.getenv("RAG_QDRANT_COLLECTION", "knowledge_chunks"),
        memory_qdrant_collection=os.getenv("MEMORY_QDRANT_COLLECTION", "user_memories"),
        embedding_model=os.getenv("RAG_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5"),
        rerank_model=os.getenv("RAG_RERANK_MODEL", "BAAI/bge-reranker-base"),
        chunk_size=int(os.getenv("RAG_CHUNK_SIZE", "900")),
        chunk_overlap=int(os.getenv("RAG_CHUNK_OVERLAP", "150")),
        vector_top_k=int(os.getenv("RAG_VECTOR_TOP_K", "24")),
        lexical_top_k=int(os.getenv("RAG_LEXICAL_TOP_K", "24")),
        rerank_top_k=int(os.getenv("RAG_RERANK_TOP_K", "8")),
        memory_top_k=int(os.getenv("MEMORY_TOP_K", "6")),
        memory_min_confidence=float(os.getenv("MEMORY_MIN_CONFIDENCE", "0.55")),
        short_term_memory_backend=os.getenv("SHORT_TERM_MEMORY_BACKEND", "postgres"),
        short_term_memory_database_url=os.getenv("SHORT_TERM_MEMORY_DATABASE_URL") or None,
        short_term_memory_pool_size=int(os.getenv("SHORT_TERM_MEMORY_POOL_SIZE", "8")),
        short_term_memory_fallback_enabled=_as_bool(
            os.getenv("SHORT_TERM_MEMORY_FALLBACK_ENABLED"),
            default=True,
        ),
    )
