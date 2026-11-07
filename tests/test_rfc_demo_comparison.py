from types import SimpleNamespace

import pytest

from evals.rfc_demo import compare


def test_comparison_uses_one_pool_and_changes_only_order(monkeypatch):
    records = [{"content": f"chunk {i}"} for i in range(10)]
    queries = []

    def collect(question):
        queries.append(question)
        return records, 8

    def rank(question, documents):
        assert question == "demo question"
        assert documents == [r["content"] for r in records]
        return SimpleNamespace(model="cpu fixture", applied=True, scores=list(range(10)))

    monkeypatch.setattr(compare, "candidate_records", collect)
    monkeypatch.setattr(compare, "rerank_with_status", rank)
    packet = compare.prepare("demo question")
    assert queries == ["demo question"]
    assert packet["pool"] == records
    assert packet["selected"] == {"hybrid": list(range(8)), "rerank": list(range(9, 1, -1))}


def test_comparison_rejects_fallback(monkeypatch):
    monkeypatch.setattr(compare, "candidate_records", lambda _: ([{"content": "candidate"}], 8))
    monkeypatch.setattr(
        compare,
        "rerank_with_status",
        lambda *_: SimpleNamespace(applied=False, error_type="Unavailable"),
    )
    with pytest.raises(RuntimeError, match="reranker_not_applied"):
        compare.prepare("demo question")
