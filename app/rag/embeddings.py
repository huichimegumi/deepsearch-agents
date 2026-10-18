"""Lazy local embedding and reranking providers backed by FastEmbed."""

from dataclasses import dataclass
from functools import lru_cache
from math import isfinite
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


@dataclass(frozen=True)
class RerankResult:
    scores: list[float]
    model: str
    applied: bool
    error_type: str | None = None


def rerank_with_status(query: str, documents: Sequence[str]) -> RerankResult:
    """Keep availability fallback explicit so evaluations cannot count it as model inference."""
    model_name = get_rag_settings().rerank_model
    if not documents:
        return RerankResult([], model_name, False)
    try:
        scores = [float(score) for score in _get_reranker().rerank(query, list(documents))]
        if len(scores) != len(documents) or not all(isfinite(score) for score in scores):
            raise ValueError("Invalid reranker score count or non-finite score")
        return RerankResult(scores, model_name, True)
    except Exception as exc:
        return RerankResult(
            [float(len(documents) - index) for index in range(len(documents))],
            model_name,
            False,
            type(exc).__name__,
        )


def rerank(query: str, documents: Sequence[str]) -> list[float]:
    """Compatibility wrapper; new callers should retain inference status."""
    return rerank_with_status(query, documents).scores
