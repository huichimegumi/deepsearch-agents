import json
from types import SimpleNamespace

import pytest

from app.rag.rerank_context import source_context_text
from evals.rag import run_context_rerank as cr
from evals.runners.experiment import file_sha256


def test_metadata_context_keeps_raw_body_and_omits_unavailable_structure():
    body = "原始\n文本\n01 标题"
    result = source_context_text(body, filename="Report.pdf", page_start=7, page_end=8)
    assert result == "来源文档：Report.pdf\n页码：7-8\n正文：\n" + body
    assert source_context_text(body) == body
    assert "结构位置" not in result
    assert source_context_text(body, section="Actual heading").endswith(body)


def test_metadata_headers_are_bounded_without_truncating_source():
    body = "x" * 1000
    result = source_context_text(body, filename="a" * 1000, section="b" * 1000)
    assert result.endswith(body)
    assert "a" * 241 not in result and "b" * 241 not in result


@pytest.fixture
def paired(monkeypatch):
    from app.rag import config, embeddings, retrieval
    from app.tools import local_rag_tools

    settings = SimpleNamespace(rerank_model="model", min_relevance_score=1, rerank_top_k=8)
    monkeypatch.setattr(config, "get_rag_settings", lambda: settings)
    monkeypatch.setattr(
        local_rag_tools, "_limit_hits_for_answer", lambda hits: (hits[:6], {"limit": 6})
    )
    monkeypatch.setattr(retrieval, "collect_candidates", lambda *_: pytest.fail("fresh recall"))
    corpus = {
        key: {
            "content": content,
            "filename": "Source.pdf",
            "page_start": None,
            "page_end": None,
            "chunk_index": index,
            "document_sha256": "doc",
        }
        for index, (key, content) in enumerate([("a", "wanted"), ("b", "other")])
    }
    task = {
        "id": "one",
        "query": "Question",
        "hybrid_ids": ["a", "b"],
        "cached_delivery_ids": ["b"],
        "case": {
            "answerable": True,
            "evidence_units": [
                {
                    "id": "SECRET_LABEL",
                    "locations": [{"document_sha256": "doc", "anchor": "wanted"}],
                }
            ],
        },
    }
    return task, corpus, embeddings


def test_pair_uses_same_pool_and_query_but_evidence_is_not_augmented(paired, monkeypatch):
    task, corpus, embeddings = paired
    calls = []

    def rerank(query, texts):
        calls.append((query, list(texts)))
        assert "SECRET_LABEL" not in str(texts)
        return embeddings.RerankResult([0.5, 3] if len(calls) == 1 else [4, 2], "model", True)

    monkeypatch.setattr(embeddings, "rerank_with_status", rerank)
    result = cr.evaluate(task, corpus)
    assert len(calls) == 2 and calls[0][0] == calls[1][0]
    assert calls[0][1] == ["wanted", "other"]
    assert calls[1][1][0].startswith("来源文档：Source.pdf")
    assert result["cached_baseline_delivery_equal"]
    assert result["policies"]["source_context"]["metrics"]["recall_at_6"] == 1
    assert all(
        h["content"] in {"wanted", "other"} for h in result["policies"]["source_context"]["hits"]
    )


def test_reranker_fallback_is_retained_as_invalid_with_call_count(paired, monkeypatch):
    task, corpus, embeddings = paired
    monkeypatch.setattr(
        embeddings, "rerank_with_status", lambda *_: embeddings.RerankResult([2, 1], "model", False)
    )
    result = cr.evaluate(task, corpus)
    assert result["status"] == "invalid" and result["local_rerank_calls"] == 1


def test_plan_does_not_load_model_or_run_inference(tmp_path, monkeypatch):
    monkeypatch.setattr(cr, "ROOT", tmp_path)
    monkeypatch.setattr(cr, "load_pools", lambda **_: ([], {}, {}))
    monkeypatch.setattr(cr, "build_manifest", lambda *_: {"source_sha256": "fixed"})
    monkeypatch.setattr(cr, "model_artifacts", lambda: pytest.fail("plan loads model"))
    monkeypatch.setattr(cr, "evaluate", lambda *_: pytest.fail("plan inference"))
    path = cr.run()
    assert json.loads((path / "results.json").read_text())["status"] == "plan_only"


def test_corrupt_saved_corpus_fails_before_pool_use(tmp_path, monkeypatch):
    monkeypatch.setattr(cr, "ROOT", tmp_path)
    report = tmp_path / "evals/reports/e4-9-vector-retention-2026-10-28.json"
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({"live_run": "prior", "corpus_file_sha256": "wrong"}))
    corpus = tmp_path / "evals/results/prior/corpus.json"
    corpus.parent.mkdir(parents=True)
    corpus.write_text("[]")
    with pytest.raises(ValueError, match="saved_corpus_changed"):
        cr.load_pools()


def test_changed_frozen_reranker_files_are_rejected(tmp_path, monkeypatch):
    from app.rag import config

    artifact = tmp_path / "reranker/config.json"
    artifact.parent.mkdir()
    artifact.write_text("{}")
    lock = tmp_path / "lock.json"
    spec = {"path": "reranker/config.json", "sha256": file_sha256(artifact)}
    lock.write_text(json.dumps({"model_artifacts": [spec]}))
    monkeypatch.setattr(cr, "LOCK", lock)
    monkeypatch.setattr(
        config, "get_rag_settings", lambda: SimpleNamespace(fastembed_cache_path=str(tmp_path))
    )
    assert cr.model_artifacts() == [spec]
    artifact.write_text("changed")
    with pytest.raises(ValueError, match="artifact_changed"):
        cr.model_artifacts()


def test_dev_loader_rebuilds_full_membership_from_archived_rerank_order(tmp_path, monkeypatch):
    monkeypatch.setattr(cr, "ROOT", tmp_path)
    dataset = tmp_path / "dev.jsonl"
    dataset.write_text("frozen")
    lock = tmp_path / "lock.json"
    lock.write_text("{}")
    monkeypatch.setattr(cr, "DATASET", dataset)
    monkeypatch.setattr(cr, "LOCK", lock)
    monkeypatch.setattr(cr, "load_development", lambda: [{"id": "one", "question": "Question"}])
    source = tmp_path / "evals/results/prior"
    source.mkdir(parents=True)
    corpus = source / "corpus.json"
    corpus.write_text(json.dumps([{"chunk_id": "a", "content": "source"}]))
    results = source / "results.json"
    results.write_text(
        json.dumps(
            {
                "manifest": {"dataset_sha256": file_sha256(dataset)},
                "cases": [
                    {
                        "id": "one",
                        "diagnostics": {"reranked_ids": ["a"]},
                        "policies": {"baseline": {"hits": [{"chunk_id": "a"}]}},
                    }
                ],
            }
        )
    )
    report = tmp_path / "evals/reports/e4-9-vector-retention-2026-10-28.json"
    report.parent.mkdir(parents=True)
    report.write_text(
        json.dumps(
            {
                "live_run": "prior",
                "corpus_file_sha256": file_sha256(corpus),
                "live_results_sha256": file_sha256(results),
            }
        )
    )
    tasks, _, _ = cr.load_pools()
    assert tasks[0]["hybrid_ids"] == ["a"]
    assert tasks[0]["pool_order_source"] == "saved_full_rerank_order"
