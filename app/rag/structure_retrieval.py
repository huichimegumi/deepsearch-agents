"""Explicitly opted-in live source/structure retrieval; ordinary search does not call this."""

from dataclasses import asdict, replace

from sqlalchemy import and_, func, select

from app.rag.database import session_scope
from app.rag.models import Chunk, Document
from app.rag.retrieval import RetrievedChunk, _rank_candidates, collect_candidates
from app.rag.source_structure import (
    SourceStructurePlan,
    plan_source_structure,
    requests_toc,
    resolve_document_sources,
)

DOCUMENT_LIMIT = 256
STRUCTURE_CHUNK_LIMIT = 1024


def _load_documents(knowledge_base_ids):
    with session_scope() as session:
        bounded = (
            session.query(Document.id)
            .filter(Document.knowledge_base_id.in_(knowledge_base_ids), Document.status == "ready")
            .order_by(Document.id)
            .limit(DOCUMENT_LIMIT + 1)
            .subquery()
        )
        return (
            session.query(
                Document.id,
                Document.filename,
                Document.sha256,
                func.max(Chunk.page_end).label("indexed_page_end"),
            )
            .outerjoin(
                Chunk,
                and_(
                    Chunk.document_id == Document.id,
                    Chunk.knowledge_base_id.in_(knowledge_base_ids),
                ),
            )
            .filter(Document.knowledge_base_id.in_(knowledge_base_ids), Document.status == "ready")
            .filter(Document.id.in_(select(bounded.c.id)))
            .group_by(Document.id, Document.filename, Document.sha256)
            .order_by(Document.id)
            .limit(DOCUMENT_LIMIT + 1)
            .all()
        )


def _load_source_chunks(knowledge_base_ids, document_hashes):
    with session_scope() as session:
        return (
            session.query(Chunk, Document)
            .join(Document, Document.id == Chunk.document_id)
            .filter(
                Document.knowledge_base_id.in_(knowledge_base_ids),
                Chunk.knowledge_base_id.in_(knowledge_base_ids),
                Document.status == "ready",
                Document.sha256.in_(document_hashes),
            )
            .order_by(Document.id, Chunk.chunk_index)
            .limit(STRUCTURE_CHUNK_LIMIT + 1)
            .all()
        )


def _row(chunk, document):
    return {
        "filename": document.filename,
        "document_sha256": document.sha256,
        "content": chunk.content,
    }


def search_source_structure(query, knowledge_base_ids, *, diagnostics=None):
    """One ordinary recall/rerank; scoped metadata/TOC reads, no hidden new recall or LLM."""
    from app.rag.config import get_rag_settings

    details = {} if diagnostics is None else diagnostics
    pool = collect_candidates(query, knowledge_base_ids)
    details.update(vector_ids=list(pool.vector_ids), hybrid_ids=list(pool.hybrid_ids))
    baseline = _rank_candidates(query, [pool.rows[i] for i in pool.hybrid_ids], diagnostics=details)

    def fallback(status):
        details["source_structure"] = asdict(SourceStructurePlan(status))
        return baseline

    if not details.get("rerank_applied"):
        return fallback("reranker_unavailable" if pool.hybrid_ids else "empty_pool")
    settings = get_rag_settings()
    if settings.min_relevance_score != 1 or settings.rerank_top_k != 8:
        return fallback("unsupported_ranking_configuration")
    documents = _load_documents(knowledge_base_ids)
    if len(documents) > DOCUMENT_LIMIT:
        return fallback("document_inventory_limit")
    metadata = [
        {
            "filename": d.filename,
            "document_sha256": d.sha256,
            "indexed_page_end": getattr(d, "indexed_page_end", None),
        }
        for d in documents
    ]
    resolution = resolve_document_sources(query, metadata, allow_page_suffix=True)
    if resolution.status != "resolved":
        return fallback(resolution.status)
    corpus = {i: _row(*pair) for i, pair in pool.rows.items()}
    # Metadata stubs participate only in exact name resolution, never as source passages.
    corpus.update(
        {
            f"document:{d.id}": {
                "filename": d.filename,
                "document_sha256": d.sha256,
                "content": "",
                "indexed_page_end": getattr(d, "indexed_page_end", None),
            }
            for d in documents
        }
    )
    plan = resolution
    if requests_toc(query) and len(resolution.document_sha256) <= 2:
        rows = _load_source_chunks(knowledge_base_ids, resolution.document_sha256)
        if len(rows) > STRUCTURE_CHUNK_LIMIT:
            plan = replace(resolution, structure_status="structure_inventory_limit")
        else:
            corpus.update({chunk.id: _row(chunk, document) for chunk, document in rows})
            plan = plan_source_structure(query, corpus, pool.hybrid_ids, allow_page_suffix=True)
    elif requests_toc(query):
        plan = replace(resolution, structure_status="source_limit")
    # Scope full scores before the top-eight cutoff; keep query and model input unchanged.
    retained = [
        i
        for i in details["reranked_ids"]
        if corpus[i]["document_sha256"] in plan.document_sha256
        and details["rerank_scores"][i] >= settings.min_relevance_score
    ][: settings.rerank_top_k]
    selected = list(dict.fromkeys([*plan.structural_ids, *retained]))[: settings.rerank_top_k]
    details["source_structure"] = asdict(plan)
    details["source_structure"]["semantic_score_gate_bypassed_ids"] = list(plan.structural_ids)
    details["source_structure"]["selected_ids"] = selected
    results = []
    for i in selected:
        chunk, document = pool.rows[i]
        results.append(
            RetrievedChunk(
                chunk_id=i,
                content=chunk.content,
                filename=document.filename,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                section=chunk.section,
                score=details["rerank_scores"][i],
                document_sha256=document.sha256,
                chunk_index=chunk.chunk_index,
                rerank_model=settings.rerank_model,
                rerank_applied=True,
                retrieval_method=(
                    "explicit_toc_structure"
                    if i in plan.structural_ids
                    else "scoped_semantic_rerank"
                ),
            )
        )
    return results
