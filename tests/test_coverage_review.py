import copy

import pytest

from evals.reports_acceptance.coverage_review import diagnose_review, render_reviewed_handoff
from tests.test_writer_fidelity import ID, TEXT, record


def fixture():
    inputs = {
        "question_parts": {"date": "发布日期", "backup": "备份", "other": "其他"},
        "records": [record()],
        "prior_extracts": [],
    }
    audit = {
        "parts": [{"part_id": key, "status": "unresolved"} for key in inputs["question_parts"]],
        "candidate_parts": 0,
        "unresolved_parts": 3,
    }
    reviews = [
        {
            "part_id": key,
            "assessment": "sufficient" if key != "other" else "insufficient",
            "quotes": [{"evidence_id": ID, "quote": TEXT}] if key != "other" else [],
        }
        for key in inputs["question_parts"]
    ]
    return inputs, audit, reviews


def test_verified_recovery_does_not_overwrite_model_failure_or_attest_accuracy():
    inputs, audit, reviews = fixture()
    before = copy.deepcopy(audit)
    result = diagnose_review(inputs, audit, reviews)
    assert [row["classification"] for row in result["diagnostics"]] == [
        "selected_extract_gap",
        "selected_extract_gap",
        "insufficient_saved_evidence",
    ]
    assert result["model_candidate_parts"] == 0 and result["human_accuracy"] is None
    assert audit == before
    assert TEXT in render_reviewed_handoff(result)
    assert "待补证据" in render_reviewed_handoff(result)
    inputs["prior_extracts"] = [{"evidence_id": ID, "quote": TEXT}]
    result = diagnose_review(inputs, audit, reviews)
    assert result["diagnostics"][0]["classification"] == "selected_support_not_used"


@pytest.mark.parametrize(
    "change", ["missing", "duplicate", "unknown", "fabricated", "empty_support"]
)
def test_invalid_or_unbound_review_cannot_create_recovered_evidence(change):
    inputs, audit, reviews = fixture()
    if change == "missing":
        reviews.pop()
    elif change == "duplicate":
        reviews[-1] = reviews[0]
    elif change == "unknown":
        reviews[-1]["part_id"] = "unknown"
    elif change == "fabricated":
        reviews[0]["quotes"][0]["quote"] = TEXT.upper()
    else:
        reviews[0]["quotes"] = []
    with pytest.raises(ValueError):
        diagnose_review(inputs, audit, reviews)
