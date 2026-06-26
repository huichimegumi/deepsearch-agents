"""Hybrid PostgreSQL/Qdrant retrieval with RRF fusion and local reranking."""

from dataclasses import dataclass

from sqlalchemy import text

from app.rag.config import get_rag_settings
from app.rag.database import session_scope
from app.rag.embeddings import embed_query, rerank
from app.rag.models import Chunk, Document
from app.rag.parsing import lexicalize
from app.rag.vector_store import search_vectors


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    content: str
    filename: str
    page_start: int | None
    page_end: int | None
    section: str | None
    score: float

    @property
    def citation(self) -> str:
        if self.page_start is None:
            location = f"，{self.section}" if self.section else ""
        elif self.page_end and self.page_end != self.page_start:
            location = f"，第{self.page_start}-{self.page_end}页"
        else:
            location = f"，第{self.page_start}页"
        return f"{self.filename}{location}"


def _lexical_search(query: str, knowledge_base_id: str, limit: int) -> list[tuple[str, float]]:
    tokens = lexicalize(query).split()
    if not tokens:
        return []
    ts_query = " | ".join(list(dict.fromkeys(tokens))[:64])
    statement = text(
        """
        SELECT chunks.id,
               ts_rank_cd(
                   to_tsvector('simple', chunks.lexical_text),
                   to_tsquery('simple', :ts_query)
               ) AS score
        FROM rag_chunks AS chunks
        JOIN rag_documents AS documents ON documents.id = chunks.document_id
        WHERE chunks.knowledge_base_id = :knowledge_base_id
          AND documents.status = 'ready'
          AND to_tsvector('simple', chunks.lexical_text) @@ to_tsquery('simple', :ts_query)
        ORDER BY score DESC
        LIMIT :limit
        """
    )
    with session_scope() as session:
        rows = session.execute(
            statement,
            {
                "ts_query": ts_query,
                "knowledge_base_id": knowledge_base_id,
                "limit": limit,
            },
        ).all()
    return [(str(row.id), float(row.score)) for row in rows]


def _filter_ranked_candidates(
    ranked: list[tuple[tuple[Chunk, Document], float]],
    min_relevance_score: float,
    limit: int,
) -> list[tuple[tuple[Chunk, Document], float]]:
    return [item for item in ranked if item[1] >= min_relevance_score][:limit]


def _load_candidate_chunks(
    candidate_ids: list[str],
) -> list[tuple[Chunk, Document]]:
    if not candidate_ids:
        return []
    with session_scope() as session:
        rows = (
            session.query(Chunk, Document)
            .join(Document, Document.id == Chunk.document_id)
            .filter(Chunk.id.in_(candidate_ids), Document.status == "ready")
            .all()
        )
        by_id = {chunk.id: (chunk, document) for chunk, document in rows}
    return [by_id[chunk_id] for chunk_id in candidate_ids if chunk_id in by_id]


def _rank_candidates(
    query: str,
    candidates: list[tuple[Chunk, Document]],
    limit: int | None = None,
) -> list[RetrievedChunk]:
    settings = get_rag_settings()
    if not candidates:
        return []

    rerank_scores = rerank(query, [chunk.content for chunk, _document in candidates])
    ranked = _filter_ranked_candidates(
        sorted(zip(candidates, rerank_scores), key=lambda item: item[1], reverse=True),
        settings.min_relevance_score,
        limit or settings.rerank_top_k,
    )
    return [
        RetrievedChunk(
            chunk_id=chunk.id,
            content=chunk.content,
            filename=document.filename,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            section=chunk.section,
            score=float(score),
        )
        for ((chunk, document), score) in ranked
    ]


def _fused_candidate_ids(
    lexical: list[tuple[str, float]], vector: list[tuple[str, float]]
) -> list[str]:
    fused: dict[str, float] = {}
    for results in (lexical, vector):
        for rank, (chunk_id, _raw_score) in enumerate(results, start=1):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (60 + rank)
    return [item[0] for item in sorted(fused.items(), key=lambda x: x[1], reverse=True)]


def hybrid_search(
    query: str,
    knowledge_base_id: str,
    query_vector: list[float] | None = None,
) -> list[RetrievedChunk]:
    settings = get_rag_settings()
    vector_query = query_vector if query_vector is not None else embed_query(query)
    lexical = _lexical_search(query, knowledge_base_id, settings.lexical_top_k)
    vector = search_vectors(vector_query, knowledge_base_id, settings.vector_top_k)

    candidate_ids = _fused_candidate_ids(lexical, vector)
    if not candidate_ids:
        return []

    return _rank_candidates(query, _load_candidate_chunks(candidate_ids))


def hybrid_search_many(query: str, knowledge_base_ids: list[str]) -> list[RetrievedChunk]:
    settings = get_rag_settings()
    if not knowledge_base_ids:
        return []

    query_vector = embed_query(query)
    candidate_ids: list[str] = []
    seen: set[str] = set()
    per_base_limit = max(settings.rerank_top_k, settings.vector_top_k, settings.lexical_top_k)

    for knowledge_base_id in knowledge_base_ids:
        lexical = _lexical_search(query, knowledge_base_id, settings.lexical_top_k)
        vector = search_vectors(query_vector, knowledge_base_id, settings.vector_top_k)
        for chunk_id in _fused_candidate_ids(lexical, vector)[:per_base_limit]:
            if chunk_id not in seen:
                seen.add(chunk_id)
                candidate_ids.append(chunk_id)

    return _rank_candidates(
        query,
        _load_candidate_chunks(candidate_ids),
        limit=settings.rerank_top_k,
    )
