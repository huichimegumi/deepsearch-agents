"""Lazy local embedding and reranking providers backed by FastEmbed."""

from functools import lru_cache
from typing import Sequence

from fastembed import TextEmbedding

from app.rag.config import get_rag_settings


@lru_cache(maxsize=1)
def get_embedding_model() -> TextEmbedding:
    return TextEmbedding(model_name=get_rag_settings().embedding_model)


def embed_documents(texts: Sequence[str]) -> list[list[float]]:
    return [vector.tolist() for vector in get_embedding_model().embed(list(texts))]


def embed_query(text: str) -> list[float]:
    return next(get_embedding_model().query_embed(text)).tolist()


@lru_cache(maxsize=1)
def _get_reranker():
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    return TextCrossEncoder(model_name=get_rag_settings().rerank_model)


def rerank(query: str, documents: Sequence[str]) -> list[float]:
    if not documents:
        return []
    try:
        return [float(score) for score in _get_reranker().rerank(query, list(documents))]
    except Exception:
        # Retrieval remains usable if the optional reranker model is unavailable.
        return [float(len(documents) - index) for index in range(len(documents))]
