import json

import pytest

from evals.reports_acceptance import two_case_triage as triage
from evals.runners.experiment import file_sha256


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(triage, "private_path", lambda path: path)
    packet = tmp_path / "results.json"
    rows = []
    cases = []
    for case_id in triage.CASES:
        folder = tmp_path / case_id
        folder.mkdir()
        source = {
            "case_id": case_id,
            "answer_keypoints": ["point"],
            "segments": [
                {
                    "id": "segment_001",
                    "text": "Report fact [ev1_local_document_valid].",
                    "cited_ids": ["ev1_local_document_valid"],
                }
            ],
            "actual_cited_evidence": {"ev1_local_document_valid": {"content": "Source fact."}},
        }
        path = folder / "input.json"
        save(path, source)
        rows.append(
            {
                "id": case_id,
                "delivery_protocol_ready": True,
                "review_input_sha256": file_sha256(path),
            }
        )
        cases.append(
            {
                "case_id": case_id,
                "keypoints": [
                    {
                        "keypoint": "point",
                        "verdict": "covered_candidate",
                        "report_quote": "Report fact",
                        "evidence_id": "ev1_local_document_valid",
                        "evidence_quote": "Source fact",
                        "reason": "Source supports the cited fact.",
                    }
                ],
            }
        )
    save(packet, {"rows": rows})
    review = tmp_path / "review.json"
    value = {
        "reviewer_type": "ai_assistant_preliminary",
        "human_review": "pending",
        "packet_sha256": file_sha256(packet),
        "cases": cases,
    }
    save(review, value)
    return packet, review, value


def test_review_accepts_only_bound_preliminary_candidate(tmp_path, monkeypatch):
    packet, review, _ = fixture(tmp_path, monkeypatch)
    result = triage.validate(packet, review)
    assert [row["id"] for row in result["rows"]] == list(triage.CASES)
    assert result["human_accuracy"] is None


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("report_quote", "Invented text", "Invented report quote"),
        ("evidence_quote", "Invented source", "Invented or uncited Evidence quote"),
        ("evidence_id", "ev1_local_document_other", "Invented or uncited Evidence quote"),
    ],
)
def test_review_rejects_unbound_quotes(tmp_path, monkeypatch, field, value, reason):
    packet, review, payload = fixture(tmp_path, monkeypatch)
    payload["cases"][0]["keypoints"][0][field] = value
    save(review, payload)
    with pytest.raises(ValueError, match=reason):
        triage.validate(packet, review)


def test_review_rejects_missing_case(tmp_path, monkeypatch):
    packet, review, payload = fixture(tmp_path, monkeypatch)
    payload["cases"].pop()
    save(review, payload)
    with pytest.raises(ValueError, match="two delivery-ready"):
        triage.validate(packet, review)
