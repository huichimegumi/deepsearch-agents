"""Checks that the retrieval experiment measures evidence and preserves its paired comparison."""

from types import SimpleNamespace

from app.rag.embeddings import RerankResult
from app.rag.retrieval import CandidatePool
from evals.rag.run_retrieval import evaluate_case, summarize, validate_annotations
from evals.rag.scoring import passage_sha256, score_retrieval


def case():
    return {
        "id": "case",
        "question": "question",
        "split": "dev",
        "answerable": True,
        "evidence_units": [
            {
                "id": name,
                "locations": [
                    {
                        "document_sha256": "document",
                        "anchor": text,
                        "anchor_sha256": passage_sha256(text),
                    }
                ],
            }
            for name, text in (("one", "first fact"), ("two", "second fact"))
        ],
    }


def test_duplicate_chunks_do_not_inflate_evidence_recall():
    hits = [{"document_sha256": "document", "content": "first fact"}] * 5
    metrics = score_retrieval(case(), hits)
    assert metrics["recall_at_5"] == 0.5
    assert metrics["mrr_at_5"] == 1
    assert not metrics["all_evidence_found"]


def test_filename_or_wrong_document_cannot_satisfy_an_evidence_unit():
    metrics = score_retrieval(case(), [{"document_sha256": "other", "content": "first fact"}])
    assert metrics["recall_at_5"] == metrics["mrr_at_5"] == 0


def test_no_answer_retrieval_is_not_mistaken_for_answer_accuracy():
    metrics = score_retrieval(
        {"answerable": False, "evidence_units": []},
        [{"document_sha256": "irrelevant", "content": "irrelevant"}],
    )
    assert metrics["recall_at_5"] is None
    assert metrics["mrr_at_5"] is None
    assert metrics["abstention_evaluated"] is False


def test_annotation_preflight_rejects_missing_evidence():
    import pytest

    with pytest.raises(ValueError, match="Unresolved evidence anchor"):
        validate_annotations([case()], [])


def test_vector_control_avoids_lexical_recall_and_applies_global_cap(monkeypatch):
    from app.rag import retrieval

    monkeypatch.setattr(
        retrieval, "get_rag_settings", lambda: SimpleNamespace(vector_top_k=2, lexical_top_k=2)
    )
    monkeypatch.setattr(retrieval, "embed_query", lambda query: [0.1])

    def unexpected(*args):
        raise AssertionError("Vector control executed lexical recall")

    monkeypatch.setattr(retrieval, "_lexical_search", unexpected)
    monkeypatch.setattr(
        retrieval,
        "search_vectors",
        lambda vector, kb, limit: [(kb + "-best", 0.9), (kb + "-second", 0.1)],
    )
    monkeypatch.setattr(
        retrieval,
        "_load_candidate_chunks",
        lambda ids: [(SimpleNamespace(id=chunk_id), object()) for chunk_id in ids],
    )
    pool = retrieval.collect_candidates("query", ["kb-b", "kb-a"], include_lexical=False)
    assert pool.vector_ids == ["kb-a-best", "kb-b-best"]
    assert pool.hybrid_ids == pool.vector_ids


def test_paired_hybrid_candidates_and_invalid_reranker_are_preserved(monkeypatch):
    from evals.rag import run_retrieval as runner

    def row(name, text):
        return (
            SimpleNamespace(id=name, content=text, chunk_index=int(name), page_start=1, page_end=1),
            SimpleNamespace(sha256="document", filename="document.pdf"),
        )

    pool = CandidatePool(
        ["1"], ["1", "2"], {"1": row("1", "first fact"), "2": row("2", "second fact")}
    )
    calls = []

    def collect(*args, **kwargs):
        calls.append(kwargs.get("include_lexical", True))
        return pool

    monkeypatch.setattr(runner, "collect_candidates", collect)
    monkeypatch.setattr(
        runner,
        "rerank_with_status",
        lambda *args: RerankResult([2.0, 1.0], "test", False, "RuntimeError"),
    )
    rows = evaluate_case(case(), ["kb"])
    assert calls == [False, True]
    assert rows[1]["candidate_pool_sha256"] == rows[2]["candidate_pool_sha256"]
    assert rows[1]["metrics"]["recall_at_5"] == 1
    assert rows[2]["status"] == "invalid_reranker"
    assert rows[2]["metrics"] is None
    summary = summarize(rows)
    assert summary["C_hybrid_rerank"]["valid"] == 0
    assert summary["C_hybrid_rerank"]["recall_at_5"] is None
