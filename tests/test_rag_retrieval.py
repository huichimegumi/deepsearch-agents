"""Tests for local RAG retrieval ranking helpers."""

from app.rag.retrieval import _filter_ranked_candidates


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
