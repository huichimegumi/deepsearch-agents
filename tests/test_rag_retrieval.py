"""Tests for local RAG retrieval ranking helpers."""

from app.rag.retrieval import _filter_ranked_candidates, hybrid_search_many


def test_filter_ranked_candidates_applies_min_relevance_and_limit():
    ranked = [
        (("chunk-a", "doc-a"), 3.0),
        (("chunk-b", "doc-b"), 0.9),
        (("chunk-c", "doc-c"), 2.0),
    ]

    filtered = _filter_ranked_candidates(ranked, min_relevance_score=1.0, limit=1)

    assert filtered == [(("chunk-a", "doc-a"), 3.0)]


def test_filter_ranked_candidates_returns_empty_when_all_scores_are_too_low():
    ranked = [
        (("chunk-a", "doc-a"), 0.2),
        (("chunk-b", "doc-b"), -1.0),
    ]

    assert _filter_ranked_candidates(ranked, min_relevance_score=1.0, limit=8) == []


def test_hybrid_search_many_reuses_query_embedding_and_reranks_globally(monkeypatch):
    calls = {"embed": 0, "rerank": 0}

    class FakeSettings:
        lexical_top_k = 2
        vector_top_k = 2
        rerank_top_k = 2
        min_relevance_score = 0.0

    class FakeChunk:
        def __init__(self, chunk_id, content):
            self.id = chunk_id
            self.content = content
            self.page_start = None
            self.page_end = None
            self.section = None

    class FakeDocument:
        filename = "doc.pdf"

    def fake_embed_query(query):
        calls["embed"] += 1
        return [0.1, 0.2]

    def fake_rerank(query, documents):
        calls["rerank"] += 1
        return [float(len(documents) - index) for index, _document in enumerate(documents)]

    monkeypatch.setattr("app.rag.retrieval.get_rag_settings", lambda: FakeSettings())
    monkeypatch.setattr("app.rag.retrieval.embed_query", fake_embed_query)
    monkeypatch.setattr("app.rag.retrieval.rerank", fake_rerank)
    monkeypatch.setattr(
        "app.rag.retrieval._lexical_search",
        lambda query, knowledge_base_id, limit: [(f"{knowledge_base_id}-lexical", 1.0)],
    )
    monkeypatch.setattr(
        "app.rag.retrieval.search_vectors",
        lambda vector, knowledge_base_id, limit: [(f"{knowledge_base_id}-vector", 0.9)],
    )
    monkeypatch.setattr(
        "app.rag.retrieval._load_candidate_chunks",
        lambda candidate_ids: [
            (FakeChunk(chunk_id, f"content {chunk_id}"), FakeDocument())
            for chunk_id in candidate_ids
        ],
    )

    hits = hybrid_search_many("query", ["kb-a", "kb-b"])

    assert calls == {"embed": 1, "rerank": 1}
    assert [hit.chunk_id for hit in hits] == ["kb-a-lexical", "kb-a-vector"]
