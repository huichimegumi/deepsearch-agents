import json
from pathlib import Path

import pytest

from evals.reports_acceptance import source_transfer_review as reviewer
from evals.runners.experiment import file_sha256


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return file_sha256(path)


@pytest.fixture
def saved(monkeypatch, tmp_path):
    suite = tmp_path / "suite.json"
    write(suite, {"cases": []})
    source = tmp_path / "evals/results/generation"
    folder = source / "case"
    evidence_id = "ev1_local_document_test"
    inputs = [
        {
            "id": "case",
            "question": "question",
            "records": [{"evidence_id": evidence_id, "content": "Source says 42%."}],
        }
    ]
    hashes = {str(suite): file_sha256(suite)}
    monkeypatch.setattr(reviewer, "DATASET", suite)
    monkeypatch.setattr(reviewer, "load_inputs", lambda: (inputs, hashes))
    monkeypatch.setattr(reviewer, "safe_path", lambda value: Path(value).resolve())
    artifacts = {
        "writer_inputs.json": write(
            folder / "writer_inputs.json",
            {
                "question": "question",
                "extracts": [
                    {
                        "quote_id": "qtx1_test",
                        "evidence_id": evidence_id,
                        "quote": "Source says 42%.",
                    }
                ],
            },
        ),
        "assertions.json": write(
            folder / "assertions.json",
            {
                "parts": [
                    {
                        "part_id": "part",
                        "assertions": [
                            {
                                "text": "The figure is 42%.",
                                "quote_ids": ["qtx1_test"],
                                "evidence_ids": [evidence_id],
                            }
                        ],
                    }
                ]
            },
        ),
    }
    results_sha = write(
        source / "results.json",
        {
            "inputs_unchanged": True,
            "source_unchanged": True,
            "manifest": {"dataset_sha256": file_sha256(suite)},
            "input_sha256": hashes,
            "cases": [
                {
                    "id": "case",
                    "status": "generated_pending_semantic_review",
                    "artifact_sha256": artifacts,
                }
            ],
        },
    )
    review = {
        "reviewer_type": "ai_assistant_preliminary",
        "human_review": "pending",
        "generation_results_sha256": results_sha,
        "items": [
            {
                "case_id": "case",
                "part_id": "part",
                "assertion_index": 0,
                "verdict": "supported",
                "reason": "Source gives the figure.",
                "evidence_quotes": [{"evidence_id": evidence_id, "quote": "42%"}],
            }
        ],
    }
    review_file = source / "review.json"
    write(review_file, review)
    return source, review_file, review


def test_review_accepts_grounded_literal_quote(saved):
    source, review_file, _ = saved
    result = reviewer.validate(source, review_file)
    assert result["quote_links_valid"] and result["verdict_counts"] == {"supported": 1}
    assert result["human_accuracy"] is None


def test_review_rejects_invented_source_quote(saved):
    source, review_file, review = saved
    review["items"][0]["evidence_quotes"][0]["quote"] = "43%"
    write(review_file, review)
    with pytest.raises(ValueError, match="review_quote_not_in_linked_original_evidence"):
        reviewer.validate(source, review_file)


def test_review_rejects_missing_assertion_or_forged_reviewer(saved):
    source, review_file, review = saved
    review["items"] = []
    write(review_file, review)
    with pytest.raises(ValueError, match="review_must_cover_every_assertion_or_gap_once"):
        reviewer.validate(source, review_file)
    review["reviewer_type"] = "human"
    write(review_file, review)
    with pytest.raises(ValueError, match="source_transfer_review_provenance_invalid"):
        reviewer.validate(source, review_file)
