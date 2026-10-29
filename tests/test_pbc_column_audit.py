import pytest

from evals.rag.audit_pbc_columns import attribute_probe


@pytest.fixture
def stages():
    ranked = [f"hit{i}" for i in range(1, 10)] + ["below"]
    corpus = {name: {"document_sha256": "target"} for name in [*ranked, "outside_pool"]}
    scores = {name: float(11 - index) for index, name in enumerate(ranked[:9], 1)}
    scores["below"] = 0.5
    diagnostics = {
        "rerank_applied": True,
        "vector_ids": ranked[:3],
        "hybrid_ids": ranked,
        "reranked_ids": ranked,
        "rerank_scores": scores,
        "source_structure": {"selected_ids": ranked[:8]},
        "delivered_ids": ranked[:6],
    }
    return diagnostics, corpus


@pytest.mark.parametrize(
    "chunk_id,expected",
    [
        ("hit1", "delivered"),
        ("hit7", "delivery_budget"),
        ("hit9", "retained_top8"),
        ("below", "score_threshold"),
        ("outside_pool", "candidate_pool"),
        ("missing", "corpus_reference_absent"),
    ],
)
def test_first_losing_stage_is_identified_without_answer_claim(stages, chunk_id, expected):
    diagnostics, corpus = stages
    assert attribute_probe(chunk_id, diagnostics, corpus, "target")["first_loss"] == expected


def test_saved_selection_must_reproduce_threshold_and_budget(stages):
    diagnostics, corpus = stages
    diagnostics["source_structure"]["selected_ids"] = ["hit2"]
    with pytest.raises(ValueError, match="saved_stage_binding_invalid"):
        attribute_probe("hit1", diagnostics, corpus, "target")
