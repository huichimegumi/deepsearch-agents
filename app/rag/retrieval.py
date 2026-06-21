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


def hybrid_search(query: str, knowledge_base_id: str) -> list[RetrievedChunk]:
    settings = get_rag_settings()
    lexical = _lexical_search(query, knowledge_base_id, settings.lexical_top_k)
    vector = search_vectors(
        embed_query(query), knowledge_base_id, settings.vector_top_k
    )

    fused: dict[str, float] = {}
    for results in (lexical, vector):
        for rank, (chunk_id, _raw_score) in enumerate(results, start=1):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (60 + rank)
    if not fused:
        return []

    candidate_ids = [item[0] for item in sorted(fused.items(), key=lambda x: x[1], reverse=True)]
    with session_scope() as session:
        rows = (
            session.query(Chunk, Document)
            .join(Document, Document.id == Chunk.document_id)
            .filter(Chunk.id.in_(candidate_ids), Document.status == "ready")
            .all()
        )
        by_id = {chunk.id: (chunk, document) for chunk, document in rows}

    ordered = [by_id[chunk_id] for chunk_id in candidate_ids if chunk_id in by_id]
    rerank_scores = rerank(query, [chunk.content for chunk, _document in ordered])
    ranked = sorted(
        zip(ordered, rerank_scores), key=lambda item: item[1], reverse=True
    )[: settings.rerank_top_k]
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
