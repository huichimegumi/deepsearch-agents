import copy

import pytest

from evals.rag import audit_evidence_loss as audit
from evals.rag.protocol import canonical_sha256


@pytest.fixture
def data():
    corpus = {
        str(i): {
            "chunk_id": str(i),
            "content": "support" if i == 9 else "other",
            "document_sha256": "doc",
        }
        for i in range(10)
    }
    unit = {"id": "u", "locations": [{"document_sha256": "doc", "anchor": "support"}]}
    policy = {
        "reranked_ids": list(corpus),
        "rerank_scores": {str(i): 10 - i for i in range(10)},
        "hits": [corpus[str(i)] for i in range(6)],
    }
    return unit, corpus, policy


@pytest.mark.parametrize(
    "gate",
    [
        "corpus_reference_absent",
        "candidate_pool",
        "score_threshold",
        "retained_top_k",
        "delivery_budget",
        "delivered_text",
        "delivered",
    ],
)
def test_first_gate_with_finite_alternatives(data, gate):
    unit, corpus, policy = data
    if gate == "corpus_reference_absent":
        unit["locations"][0]["anchor"] = "not present"
    elif gate == "candidate_pool":
        policy["reranked_ids"].remove("9")
        del policy["rerank_scores"]["9"]
    elif gate == "score_threshold":
        policy["rerank_scores"]["9"] = 0.5
    elif gate in {"delivery_budget", "delivered_text", "delivered"}:
        corpus["6"]["content"] = "support"
        if gate != "delivery_budget":
            corpus["5"]["content"] = "support"
            policy["hits"] = [copy.deepcopy(corpus[str(i)]) for i in range(6)]
            if gate == "delivered_text":
                policy["hits"][5]["content"] = "truncated"
    result = audit.attribute(unit, corpus, policy)
    assert result["first_loss"] == gate
    assert result["delivered_from_reference_documents"] == len(policy["hits"])
    # Source identity counts alone cannot turn an unmatched passage into support.
    if gate != "delivered":
        assert result["delivered_reference_document_without_anchor"] == len(policy["hits"])


def test_any_surviving_alternative_prevents_false_loss(data):
    unit, corpus, policy = data
    unit["locations"].append({"document_sha256": "doc", "anchor": "other"})
    assert audit.attribute(unit, corpus, policy)["first_loss"] == "delivered"


@pytest.mark.parametrize(
    "mutation", ["duplicate", "unknown", "nonfinite", "order", "delivery", "document"]
)
def test_rejects_inconsistent_saved_ranking(data, mutation):
    unit, corpus, policy = data
    if mutation == "duplicate":
        policy["reranked_ids"].append("9")
    elif mutation == "unknown":
        del corpus["9"]
    elif mutation == "nonfinite":
        policy["rerank_scores"]["9"] = float("nan")
    elif mutation == "order":
        policy["reranked_ids"].reverse()
    elif mutation == "delivery":
        policy["hits"].reverse()
    else:
        policy["hits"] = copy.deepcopy(policy["hits"])
        policy["hits"][0]["document_sha256"] = "foreign"
    with pytest.raises(ValueError):
        audit.attribute(unit, corpus, policy)


def test_pool_membership_and_metric_reproduction_are_checked(data):
    _, corpus, policy = data
    task = {
        "id": "case",
        "hybrid_ids": list(corpus),
        "case": {"answerable": False, "evidence_units": []},
    }
    row = {
        "id": "case",
        "status": "ok",
        "candidate_pool_sha256": canonical_sha256(list(corpus)),
        "policies": {"baseline": policy, "source_context": policy},
    }
    saved = {"status": "evaluated", "cases": [row]}
    policy["metrics"] = {"forged": True}
    with pytest.raises(ValueError, match="saved_metrics"):
        audit.audit_rows([task], corpus, saved)
    policy["metrics"] = audit.score(task["case"], policy["hits"])
    assert audit.audit_rows([task], corpus, saved)[0]["units"] == []
    task["hybrid_ids"] = []
    with pytest.raises(ValueError, match="candidate_binding"):
        audit.audit_rows([task], corpus, saved)


def test_corrupt_paired_results_rejected_before_audit(monkeypatch, tmp_path):
    report = tmp_path / "report.json"
    report.write_text('{"development_run":"absent","development_results_sha256":"wrong"}')
    monkeypatch.setattr(audit, "REPORT", report)
    monkeypatch.setattr(audit, "load_pools", lambda **_: ([], {}, {}))
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    saved = tmp_path / "evals/results/absent/results.json"
    saved.parent.mkdir(parents=True)
    saved.write_text("{}")
    with pytest.raises(ValueError, match="paired_results_changed"):
        audit.run(tmp_path / "output.json")
    assert not (tmp_path / "output.json").exists()
