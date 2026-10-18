"""Frozen split, comparison-denominator, and annotation revision contracts."""

import json
from pathlib import Path

import pytest

from evals.rag.protocol import (
    canonical_sha256,
    check_dataset_files,
    check_lock,
    validate_splits,
)
from evals.rag.rescore import rescore
from evals.rag.run_retrieval import paired_summary, run, validate_annotations
from evals.runners.common import load_jsonl

SUITE = Path(__file__).resolve().parents[1] / "evals/rag/suites/v2"


def test_v2_suite_has_frozen_disjoint_20_and_10_questions():
    check_dataset_files(SUITE / "suite.lock.json")
    dev = load_jsonl(SUITE / "development.jsonl")
    test = load_jsonl(SUITE / "test.jsonl")
    assert len(dev) == 20 and len(test) == 10
    assert sum(not c["answerable"] for c in test) == 2
    assert sum(c["kind"] == "multi_document" for c in test) == 2
    assert all(c["annotation_review"].endswith("pending_human_review") for c in dev + test)


def test_frozen_hash_is_independent_of_newline_encoding():
    rows = load_jsonl(SUITE / "development.jsonl")
    reparsed = [json.loads(line) for line in "\r\n".join(json.dumps(r) for r in rows).splitlines()]
    assert canonical_sha256(rows) == canonical_sha256(reparsed)


def test_a_rephrased_split_label_cannot_hide_a_duplicate_question():
    dev = load_jsonl(SUITE / "development.jsonl")[:1]
    test = [{**dev[0], "id": "different-id", "split": "test"}]
    with pytest.raises(ValueError, match="duplicates"):
        validate_splits(dev, test)


@pytest.mark.parametrize("dimension", ["data", "corpus", "configuration", "models"])
def test_freeze_rejects_changed_inputs_before_inference(dimension):
    lock_path = SUITE / "suite.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    cases = load_jsonl(SUITE / "test.jsonl")
    config = {**lock["configuration"], "knowledge_base_names": lock["knowledge_base_names"]}
    corpus = lock["corpus_sha256"]
    models = lock["model_artifacts"]
    if dimension == "data":
        cases[0]["question"] += "changed"
    elif dimension == "corpus":
        corpus = "changed"
    elif dimension == "configuration":
        config["vector_top_k"] += 1
    else:
        models = []
    with pytest.raises(ValueError, match="changed"):
        check_lock(lock_path, cases, "test", config, corpus, models)


def test_test_execution_needs_a_lock_before_database_or_model_access():
    with pytest.raises(ValueError, match="requires a frozen suite lock"):
        run(Path("nonexistent"), [], "test")


def test_paired_summary_excludes_the_same_failed_case_from_all_groups():
    rows = [
        {
            "case_id": case_id,
            "mode": mode,
            "status": "invalid_reranker" if case_id == "bad" and mode.startswith("C") else "ok",
            "metrics": {
                "no_answer": False,
                "recall_at_5": 1,
                "mrr_at_5": 1,
                "all_evidence_found": True,
            },
            "elapsed_ms": 1,
        }
        for case_id in ("good", "bad")
        for mode in ("A_vector", "B_hybrid", "C_hybrid_rerank")
    ]
    result = paired_summary(rows)
    assert result["case_ids"] == ["good"]
    assert result["excluded_case_ids"] == ["bad"]
    assert all(s["scored_answerable"] == 1 for s in result["summary"].values())


def test_rescoring_alternative_anchor_preserves_rank_time_and_model_status():
    original_case = load_jsonl(SUITE / "development.jsonl")[0]
    old_case = json.loads(json.dumps(original_case))
    old_case["evidence_units"][0]["locations"] = old_case["evidence_units"][0]["locations"][:1]
    location = original_case["evidence_units"][0]["locations"][1]
    original = {
        "run_id": "before",
        "summary": {},
        "annotation_snapshot": [old_case],
        "results": [
            {
                "case_id": old_case["id"],
                "mode": "C_hybrid_rerank",
                "status": "ok",
                "elapsed_ms": 17,
                "candidate_pool_sha256": "same-pool",
                "reranker": {"applied": True},
                "metrics": {"recall_at_5": 0},
                "top_hits": [
                    {"document_sha256": location["document_sha256"], "content": location["anchor"]}
                ],
            }
        ],
    }
    rescored = rescore(original, [original_case])
    row = rescored["results"][0]
    assert row["metrics"]["recall_at_5"] == 1
    assert row["elapsed_ms"] == 17
    assert row["candidate_pool_sha256"] == "same-pool"
    assert row["reranker"] == {"applied": True}
    assert original["results"][0]["metrics"]["recall_at_5"] == 0


def test_every_alternative_anchor_is_checked_even_when_the_first_resolves():
    case = load_jsonl(SUITE / "development.jsonl")[0]
    first = case["evidence_units"][0]["locations"][0]
    with pytest.raises(ValueError, match="Unresolved evidence anchor"):
        validate_annotations(
            [case], [{"document_sha256": first["document_sha256"], "content": first["anchor"]}]
        )


def test_rescoring_cannot_reuse_passages_for_a_changed_question():
    case = load_jsonl(SUITE / "development.jsonl")[0]
    original = {
        "run_id": "before",
        "summary": {},
        "annotation_snapshot": [case],
        "results": [{"case_id": case["id"], "mode": "A_vector", "status": "blocked"}],
    }
    changed = {**case, "question": "different question"}
    with pytest.raises(ValueError, match="changed question"):
        rescore(original, [changed])
