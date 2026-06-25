"""Lazy local embedding and reranking providers backed by FastEmbed."""

from functools import lru_cache
from pathlib import Path
from typing import Sequence

from fastembed import TextEmbedding

from app.rag.config import get_rag_settings


def _cache_dir() -> str | None:
    cache_path = get_rag_settings().fastembed_cache_path
    if not cache_path:
        return None
    path = Path(cache_path)
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


@lru_cache(maxsize=1)
def get_embedding_model() -> TextEmbedding:
    return TextEmbedding(model_name=get_rag_settings().embedding_model, cache_dir=_cache_dir())


def embed_documents(texts: Sequence[str]) -> list[list[float]]:
    return [vector.tolist() for vector in get_embedding_model().embed(list(texts))]


def embed_query(text: str) -> list[float]:
    return next(get_embedding_model().query_embed(text)).tolist()


@lru_cache(maxsize=1)
def _get_reranker():
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    return TextCrossEncoder(model_name=get_rag_settings().rerank_model, cache_dir=_cache_dir())


def rerank(query: str, documents: Sequence[str]) -> list[float]:
    if not documents:
        return []
    try:
        return [float(score) for score in _get_reranker().rerank(query, list(documents))]
    except Exception:
        # Retrieval remains usable if the optional reranker model is unavailable.
        return [float(len(documents) - index) for index in range(len(documents))]
