"""Hybrid PostgreSQL/Qdrant retrieval with RRF fusion and local reranking."""

from dataclasses import dataclass

from sqlalchemy import text

from app.rag.config import get_rag_settings
from app.rag.database import session_scope
from app.rag.embeddings import embed_query, rerank_with_status
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
    document_sha256: str | None = None
    chunk_index: int | None = None
    rerank_model: str | None = None
    rerank_applied: bool | None = None
    rerank_error_type: str | None = None

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

    reranking = rerank_with_status(query, [chunk.content for chunk, _document in candidates])
    ranked = _filter_ranked_candidates(
        sorted(zip(candidates, reranking.scores), key=lambda item: item[1], reverse=True),
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
            document_sha256=getattr(document, "sha256", None),
            chunk_index=getattr(chunk, "chunk_index", None),
            rerank_model=reranking.model,
            rerank_applied=reranking.applied,
            rerank_error_type=reranking.error_type,
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


@dataclass(frozen=True)
class CandidatePool:
    """Reusable recall stage: production and experiments share these exact candidates."""

    vector_ids: list[str]
    hybrid_ids: list[str]
    rows: dict[str, tuple[Chunk, Document]]


def collect_candidates(
    query: str,
    knowledge_base_ids: list[str],
    query_vector: list[float] | None = None,
    *,
    include_lexical: bool = True,
) -> CandidatePool:
    settings = get_rag_settings()
    if not knowledge_base_ids:
        return CandidatePool([], [], {})
    vector_query = query_vector if query_vector is not None else embed_query(query)
    lexical_scores: dict[str, float] = {}
    vector_scores: dict[str, float] = {}
    for knowledge_base_id in sorted(set(knowledge_base_ids)):
        if include_lexical:
            for chunk_id, score in _lexical_search(
                query, knowledge_base_id, settings.lexical_top_k
            ):
                lexical_scores[chunk_id] = max(lexical_scores.get(chunk_id, float("-inf")), score)
        for chunk_id, score in search_vectors(
            vector_query, knowledge_base_id, settings.vector_top_k
        ):
            vector_scores[chunk_id] = max(vector_scores.get(chunk_id, float("-inf")), score)

    def ranked(scores, limit):
        return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]

    lexical = ranked(lexical_scores, settings.lexical_top_k)
    vector = ranked(vector_scores, settings.vector_top_k)
    hybrid_ids = (
        _fused_candidate_ids(lexical, vector)
        if include_lexical
        else [chunk_id for chunk_id, _ in vector]
    )
    rows = {chunk.id: (chunk, document) for chunk, document in _load_candidate_chunks(hybrid_ids)}
    return CandidatePool(
        [chunk_id for chunk_id, _ in vector if chunk_id in rows],
        [chunk_id for chunk_id in hybrid_ids if chunk_id in rows],
        rows,
    )


def hybrid_search(
    query: str,
    knowledge_base_id: str,
    query_vector: list[float] | None = None,
) -> list[RetrievedChunk]:
    pool = collect_candidates(query, [knowledge_base_id], query_vector)
    return _rank_candidates(query, [pool.rows[chunk_id] for chunk_id in pool.hybrid_ids])


def hybrid_search_many(query: str, knowledge_base_ids: list[str]) -> list[RetrievedChunk]:
    pool = collect_candidates(query, knowledge_base_ids)
    return _rank_candidates(query, [pool.rows[chunk_id] for chunk_id in pool.hybrid_ids])
