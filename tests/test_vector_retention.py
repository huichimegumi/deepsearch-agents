import json

import pytest

from app.rag.retention import order_retained_by_rerank, retain_vector_head
from evals.rag import run_retention as vr
from evals.rag.protocol import canonical_sha256


def test_protection_keeps_unique_head_and_fills_with_reranked_without_exceeding_budget():
    assert retain_vector_head(["a", "a", "b", "c", "d"], ["b", "e", "f", "g", "h"]) == [
        "a",
        "b",
        "c",
        "e",
        "f",
        "g",
    ]
    assert retain_vector_head(["a", "b", "c", "d"], []) == ["a", "b", "c"]
    assert retain_vector_head(["a"], ["b", "c"], protected=0) == ["b", "c"]


@pytest.mark.parametrize("budget,protected", [(0, 0), (2, 3), (2, -1)])
def test_invalid_retention_budgets_fail(budget, protected):
    with pytest.raises(ValueError):
        retain_vector_head([], [], budget=budget, protected=protected)


def test_sixth_position_is_scored_as_six_not_five_and_negative_not_scored():
    anchor = "actual supporting passage"
    from evals.rag.scoring import passage_sha256

    positive = {
        "answerable": True,
        "evidence_units": [
            {
                "id": "unit",
                "locations": [
                    {
                        "document_sha256": "doc",
                        "anchor": anchor,
                        "anchor_sha256": passage_sha256(anchor),
                    }
                ],
            }
        ],
    }
    hits = [{"document_sha256": "doc", "content": "unrelated"}] * 5 + [
        {"document_sha256": "doc", "content": anchor}
    ]
    scored = vr.score(positive, hits)
    assert scored["recall_at_6"] == 1 and scored["mrr_at_6"] == 1 / 6
    assert "recall_at_5" not in scored
    negative = vr.score({"answerable": False}, hits)
    assert negative["recall_at_6"] is None and not negative["abstention_evaluated"]


@pytest.fixture
def suite(tmp_path, monkeypatch):
    rows = [
        {
            "id": "one",
            "split": "dev",
            "question": "Question",
            "answerable": False,
            "evidence_units": [],
        }
    ]
    dataset = tmp_path / "dev.jsonl"
    dataset.write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
    lock = tmp_path / "lock.json"
    lock.write_text(
        json.dumps({"datasets": {"dev": {"count": 1, "canonical_sha256": canonical_sha256(rows)}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(vr, "DATASET", dataset)
    monkeypatch.setattr(vr, "LOCK", lock)
    monkeypatch.setattr(vr, "ROOT", tmp_path)
    monkeypatch.setattr(vr, "build_manifest", lambda *_: {"source_sha256": "fixed"})
    return dataset


def test_changed_dev_dataset_rejected(suite):
    suite.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="frozen_development_changed"):
        vr.load_development()


def test_default_is_plan_only_and_does_not_run_retrieval(suite, monkeypatch):
    monkeypatch.setattr(vr, "evaluate", lambda *_: pytest.fail("plan ran inference"))
    output = vr.run()
    result = json.loads((output / "results.json").read_text(encoding="utf-8"))
    assert result["status"] == "plan_only" and not result["cases"]


def test_summary_excludes_negative_cases_from_both_denominators():
    positive = {
        "recall_at_6": 0.5,
        "mrr_at_6": 0.5,
        "all_evidence_found": False,
        "no_answer": False,
    }
    negative = {"no_answer": True, "recall_at_6": None}
    rows = [
        {
            "status": "ok",
            "policies": {name: {"metrics": metric} for name in ("baseline", "protected")},
        }
        for metric in (positive, negative)
    ]
    summary = vr.summarize(rows)
    assert summary["policies"]["baseline"]["answerable"] == 1
    assert summary["policies"]["protected"]["recall_at_6"] == 0.5


def test_ordering_replay_changes_rank_without_changing_membership_text_or_original_rows():
    case = {
        "id": "one",
        "answerable": True,
        "evidence_units": [
            {"id": "unit", "locations": [{"document_sha256": "doc", "anchor": "wanted"}]}
        ],
    }
    hits = [
        {"chunk_id": key, "document_sha256": "doc", "content": text}
        for key, text in [("a", "other"), ("b", "other"), ("c", "wanted")]
    ]
    rows = [
        {
            "id": "one",
            "status": "ok",
            "diagnostics": {"reranked_ids": ["c", "a", "b"]},
            "policies": {
                "protected": {
                    "hits": hits,
                    "budget": {"answer_hits": 3},
                    "metrics": vr.score(case, hits),
                }
            },
        }
    ]
    before = json.dumps(rows, sort_keys=True)
    replay = vr.reorder_rows(rows, [case])[0]["policies"]["protected_rerank_order"]
    assert replay["metrics"]["mrr_at_6"] == 1
    assert [h["chunk_id"] for h in replay["hits"]] == ["c", "a", "b"]
    assert sorted(replay["hits"], key=lambda h: h["chunk_id"]) == hits
    assert replay["budget"] == rows[0]["policies"]["protected"]["budget"]
    assert json.dumps(rows, sort_keys=True) == before


@pytest.mark.parametrize("ids", [["unknown"], ["a", "a"]])
def test_ordering_rejects_unbound_or_duplicate_members(ids):
    with pytest.raises(ValueError):
        order_retained_by_rerank(ids, ["a", "b"])
