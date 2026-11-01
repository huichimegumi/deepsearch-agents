import json

import pytest

from evals.calibrate_v4 import fixtures
from evals.scoring_v4 import aggregate, mechanical, score


def test_medians_are_independent_and_even_samples_not_upper_middle():
    assert aggregate(
        [
            {"checklist_coverage": 0.3, "claim_support": 1.0},
            {"checklist_coverage": 1.0, "claim_support": 0.7},
            {"checklist_coverage": 0.9, "claim_support": 0.0},
        ]
    ) == {"checklist_coverage": 0.9, "claim_support": 0.7}
    assert aggregate(
        [
            {"checklist_coverage": 0.2, "claim_support": 0.5},
            {"checklist_coverage": 0.8, "claim_support": 1.0},
        ]
    ) == {"checklist_coverage": 0.5, "claim_support": 0.75}


def test_mechanical_gates_reject_known_corruptions_and_allow_semantic_review():
    cases, results = fixtures()
    for case, result in zip(cases, results, strict=True):
        issues = mechanical(case, result)["issues"]
        if case["id"].endswith(("_correct", "_contradiction")):
            assert not issues
        else:
            assert issues


@pytest.mark.asyncio
async def test_interrupted_scoring_resumes_checkpoints_without_repeat(tmp_path):
    cases, results = fixtures()
    calls = []

    async def interrupted(case, result):
        calls.append(case["id"])
        if len(calls) == 2:
            raise KeyboardInterrupt("simulated kill")
        return {"checklist_coverage": 1.0, "claim_support": 1.0}

    with pytest.raises(KeyboardInterrupt):
        await score(cases[:2], results[:2], tmp_path, judge_fn=interrupted)
    assert json.loads((tmp_path / "scores.json").read_text())["terminal"] == 1

    async def resumed(case, result):
        calls.append(case["id"])
        return {"checklist_coverage": 1.0, "claim_support": 1.0}

    summary = await score(cases[:2], results[:2], tmp_path, judge_fn=resumed)
    assert len(calls) == 3
    assert summary["passes"] == 1  # wrong numeric answer cannot pass a generous judge
    assert summary["generator_usage_missing"] == 2
    results[0]["report"]["facts"][0]["value"] = "999"
    with pytest.raises(ValueError, match="scoring_resume_mismatch"):
        await score(cases[:2], results[:2], tmp_path, judge_fn=resumed)
