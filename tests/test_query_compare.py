import json
from types import SimpleNamespace

import pytest

from app.rag import retrieval as rr
from app.rag.embeddings import RerankResult
from app.tools import evidence_tool as et
from evals.reports_acceptance import query_compare as qc


def test_concise_query_uses_question_title_parts_and_explicit_directory_cue():
    task = {
        "question": "依据《报告2025》列出目录。不要假定正文内容。",
        "parts": [{"label": "第一章标题"}],
        "answer_key": "SECRET_ANSWER",
    }
    assert qc.concise_query(task) == "报告2025 目录 第一章标题"
    assert qc.concise_query({"question": "Question", "parts": [{"label": "Detail"}]}) == "Detail"


def test_optional_rank_diagnostics_preserve_output_and_trace_threshold_loss(monkeypatch):
    document = SimpleNamespace(filename="Source.pdf", sha256="source")
    rows = [
        (
            SimpleNamespace(
                id=key,
                content="private text",
                page_start=None,
                page_end=None,
                section=None,
                chunk_index=i,
            ),
            document,
        )
        for i, key in enumerate(["a", "b", "c"])
    ]
    pool = rr.CandidatePool(["a", "b"], ["a", "b", "c"], {row[0].id: row for row in rows})
    monkeypatch.setattr(rr, "collect_candidates", lambda *args: pool)
    monkeypatch.setattr(
        rr, "get_rag_settings", lambda: SimpleNamespace(min_relevance_score=1, rerank_top_k=1)
    )
    monkeypatch.setattr(
        rr, "rerank_with_status", lambda *_: RerankResult([2, 0.2, 3], "model", True)
    )
    plain = rr.hybrid_search("query", "kb")
    diagnostics = {}
    traced = rr.hybrid_search("query", "kb", diagnostics=diagnostics)
    assert traced == plain
    assert diagnostics["hybrid_ids"] == ["a", "b", "c"]
    assert diagnostics["reranked_ids"] == ["c", "a", "b"]
    assert diagnostics["retained_ids"] == ["c"]
    assert diagnostics["rerank_scores"]["b"] == 0.2
    assert "private text" not in str(diagnostics)


def test_budget_delivery_diagnostics_do_not_change_evidence(monkeypatch):
    hits = [
        rr.RetrievedChunk(key, "private text", "Source.pdf", None, None, None, 2)
        for key in ["a", "b"]
    ]
    monkeypatch.setattr(et, "_resolve_knowledge_bases", lambda _: [SimpleNamespace(id="kb")])
    monkeypatch.setattr(et, "hybrid_search", lambda *args, **kwargs: hits)
    monkeypatch.setattr(et, "_limit_hits_for_answer", lambda _: (hits[:1], {"truncated": True}))
    plain = et._collect_local_documents("query", "base")
    diagnostics = {}
    traced = et._collect_local_documents("query", "base", diagnostics=diagnostics)
    assert traced == plain
    assert diagnostics["delivered_ids"] == ["a"]
    assert diagnostics["context_budget"]["truncated"] is True


@pytest.fixture
def configured(tmp_path, monkeypatch):
    tasks = [
        {"id": f"case_{i}", "question": f"Full question {i}", "parts": [{"label": f"Part {i}"}]}
        for i in range(3)
    ]
    monkeypatch.setattr(qc, "questions", lambda: tasks)
    monkeypatch.setattr(qc, "safe_path", lambda p: tmp_path / p)
    monkeypatch.setattr(qc, "build_manifest", lambda *_: {"source_sha256": "fixed"})
    monkeypatch.setattr(qc, "corpus", lambda: [{"stable": "corpus"}])
    return tasks


def test_plan_is_offline(configured, monkeypatch):
    monkeypatch.setattr(qc, "retrieve", lambda _: pytest.fail("plan retrieved"))
    monkeypatch.setattr(qc, "corpus", lambda: pytest.fail("plan contacted services"))
    output = qc.run()
    assert (
        json.loads((output / "results.json").read_text(encoding="utf-8"))["status"] == "plan_only"
    )


def test_comparison_freezes_plan_and_executes_exactly_six_queries(configured, monkeypatch):
    calls = []

    def retrieve(query):
        calls.append(query)
        return {"batch": {"status": "NO_EVIDENCE"}, "diagnostics": {}}

    monkeypatch.setattr(qc, "retrieve", retrieve)
    output = qc.run(execute=True)
    result = json.loads((output / "results.json").read_text(encoding="utf-8"))
    assert calls == [q for i in range(3) for q in [f"Full question {i}", f"Part {i}"]]
    assert result["manifest"]["source_sha256"] == "fixed"
    assert result["status"] == "compared"
    assert len(result["cases"]) == 6


def test_retrieval_failure_is_preserved_without_retry(configured, monkeypatch):
    calls = []

    def retrieve(query):
        calls.append(query)
        raise RuntimeError("private error")

    monkeypatch.setattr(qc, "retrieve", retrieve)
    output = qc.run(execute=True)
    result = json.loads((output / "results.json").read_text(encoding="utf-8"))
    assert len(calls) == 6 and result["status"] == "invalid"
    assert "private error" not in str(result)
