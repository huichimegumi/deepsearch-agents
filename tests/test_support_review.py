import json
from copy import deepcopy

import pytest

from evals.reports_acceptance import support_review as support
from evals.runners.experiment import file_sha256

ID = "ev1_local_document_" + "a" * 24


def payload():
    return support.prepare_input(
        f"# Heading\nFact [{ID}]",
        {
            "records": [
                {
                    "evidence_id": ID,
                    "content": "Original source fact",
                    "metadata": {},
                    "source": "local_document",
                }
            ]
        },
        {
            "question": "question",
            "answerable": True,
            "evidence_units": [{"id": "key", "keypoint": "fact"}],
        },
        [{"sha256": "a", "filename": "real.pdf"}],
    )


def review():
    return support.SupportReview.model_validate(
        {
            "segments": [
                {
                    "segment_id": "segment_001",
                    "verdict": "supported",
                    "report_quote": "Fact",
                    "evidence_quotes": [{"evidence_id": ID, "quote": "source fact"}],
                    "reason": "model suggestion",
                }
            ],
            "keypoints": [
                {
                    "unit_id": "key",
                    "coverage": "covered",
                    "report_quote": "Fact",
                    "reason": "model suggestion",
                }
            ],
            "abstention": "not_applicable",
            "abstention_report_quote": "",
            "abstention_reason": "answerable",
        }
    )


def test_heading_adjacent_body_and_rejected_drafts_are_handled():
    text = f"# Title\nBody [{ID}]\n## Rejected claim drafts\n- False [{ID}]\n\n## Conflicts\n- conflict\n\n## Tail\n- None recorded"
    rows = support.segment_report(text, exclude_rejected_drafts=True)
    assert [row["text"] for row in rows] == [f"Body [{ID}]", "- conflict"]
    assert rows[0]["cited_ids"] == [ID]
    assert "False" in support.segment_report(text)[1]["text"]


def test_filename_flags_are_not_fabrication_verdicts():
    flags = support.filename_flags(
        "《real.pdf》 《REAL.PDF》 《invented.docx》 《short title》", [{"filename": "real.pdf"}]
    )
    assert flags == [{"filename": "invented.docx", "status": "unverified_filename_pending_review"}]


def test_quote_validation_accepts_whitespace_only_difference_not_semantic_approval():
    suggested = review()
    suggested.segments[0].evidence_quotes[0].quote = "source\n fact"
    support.validate_review(suggested, payload())


@pytest.mark.parametrize(
    "failure",
    [
        "missing_segment",
        "duplicate_segment",
        "unknown_segment",
        "report_quote",
        "passage_quote",
        "unrelated_id",
        "uncited",
        "no_quote",
        "missing_key",
        "key_quote",
        "key_empty",
        "abstention",
    ],
)
def test_invalid_model_outputs_never_become_valid_reviews(failure):
    suggested, inputs = review(), payload()
    if failure == "missing_segment":
        suggested.segments = []
    elif failure == "duplicate_segment":
        suggested.segments.append(deepcopy(suggested.segments[0]))
    elif failure == "unknown_segment":
        suggested.segments[0].segment_id = "unknown"
    elif failure == "report_quote":
        suggested.segments[0].report_quote = "invented report phrase"
    elif failure == "passage_quote":
        suggested.segments[0].evidence_quotes[0].quote = "invented passage"
    elif failure == "unrelated_id":
        suggested.segments[0].evidence_quotes[0].evidence_id = "unknown"
    elif failure == "uncited":
        inputs["segments"][0]["cited_ids"] = []
    elif failure == "no_quote":
        suggested.segments[0].evidence_quotes = []
    elif failure == "missing_key":
        suggested.keypoints = []
    elif failure == "key_quote":
        suggested.keypoints[0].report_quote = "invented coverage"
    elif failure == "key_empty":
        suggested.keypoints[0].report_quote = ""
    else:
        suggested.abstention = "appropriate"
    with pytest.raises(ValueError):
        support.validate_review(suggested, inputs)


def test_negative_case_requires_explicit_quoted_abstention_review():
    suggested, inputs = review(), payload()
    inputs["answerable_draft_label"] = False
    with pytest.raises(ValueError):
        support.validate_review(suggested, inputs)
    suggested.abstention = "inappropriate"
    suggested.abstention_report_quote = "Fact"
    support.validate_review(suggested, inputs)


def test_oversized_inputs_are_blocked_not_truncated(monkeypatch):
    monkeypatch.setattr(support, "MAX_INPUT_CHARS", 1)
    with pytest.raises(ValueError, match="no silent truncation"):
        payload()


def load_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(support, "ROOT", tmp_path)
    directory = tmp_path / "evals/results/original/case"
    directory.mkdir(parents=True)
    (directory / "report.md").write_text("# Title\nFact", encoding="utf-8")
    (directory / "evidence.json").write_text(json.dumps({"records": []}), encoding="utf-8")
    corpus = [{"document_sha256": "a", "filename": "real.pdf"}]
    monkeypatch.setattr(support, "corpus_snapshot", lambda _: ([], corpus))
    monkeypatch.setattr(
        support,
        "load_cases",
        lambda _: (
            {},
            [{"id": "case", "question": "question", "answerable": True, "evidence_units": []}],
        ),
    )
    original = {
        "inputs_unchanged": True,
        "manifest": {
            "dataset_sha256": file_sha256(support.DEFAULT_DATASET),
            "configuration": {"knowledge_bases": ["test"]},
        },
        "corpus_sha256": support.canonical_sha256(corpus),
        "results": [
            {
                "id": "case",
                "review_directory": "evals/results/original/case",
                "report_sha256": file_sha256(directory / "report.md"),
                "evidence_sha256": file_sha256(directory / "evidence.json"),
            }
        ],
    }
    return directory.parent / "results.json", original


def test_selected_segments_cannot_claim_whole_report_acceptance():
    original = payload()
    selected = support.select_segments(original, ["segment_001"])
    assert selected["keypoints"] == []
    assert original["keypoints"]
    suggested = review()
    suggested.keypoints = []
    with pytest.raises(support.GroundingError):
        support.validate_review(suggested, selected)
    suggested.abstention = "not_evaluated"
    support.validate_review(suggested, selected)
    with pytest.raises(support.GroundingError):
        support.validate_review(suggested, original)


@pytest.mark.parametrize("ids", [[], ["unknown"], ["segment_001", "segment_001"]])
def test_invalid_segment_selection_is_rejected(ids):
    with pytest.raises(ValueError):
        support.select_segments(payload(), ids)


def test_human_worksheet_includes_report_and_sources_without_approval():
    worksheet = support.render_worksheet(payload(), {"status": "not_requested"})
    assert "Fact" in worksheet and "Original source fact" in worksheet
    assert "- [x]" not in worksheet
    assert "Human verdict: pending" in worksheet


@pytest.mark.parametrize(
    "failure",
    ["unfinished", "suite", "hash", "outside", "corpus", "missing_case", "duplicate_case"],
)
def test_loading_rejects_changed_or_unexecuted_artifacts(tmp_path, monkeypatch, failure):
    path, original = load_fixture(tmp_path, monkeypatch)
    if failure == "unfinished":
        original["inputs_unchanged"] = False
    elif failure == "suite":
        original["manifest"]["dataset_sha256"] = "changed"
    elif failure == "hash":
        original["results"][0]["report_sha256"] = "changed"
    elif failure == "outside":
        original["results"][0]["review_directory"] = "outside"
    elif failure == "corpus":
        original["corpus_sha256"] = "changed"
    elif failure == "missing_case":
        original["results"] = []
    else:
        original["results"].append(deepcopy(original["results"][0]))
    path.write_text(json.dumps(original), encoding="utf-8")
    with pytest.raises(ValueError):
        support.load_saved(path, "case")


def test_valid_saved_artifact_loads_reference_and_verified_inventory(tmp_path, monkeypatch):
    path, original = load_fixture(tmp_path, monkeypatch)
    path.write_text(json.dumps(original), encoding="utf-8")
    _, row, inputs = support.load_saved(path, "case")
    assert row["id"] == "case"
    assert inputs["selected_document_inventory"] == [{"sha256": "a", "filename": "real.pdf"}]


@pytest.mark.parametrize("mode", ["none", "valid", "invalid", "drift"])
def test_cli_keeps_model_suggestions_provisional_or_invalid(tmp_path, monkeypatch, mode):
    import sys

    monkeypatch.setattr(support, "ROOT", tmp_path)
    path = tmp_path / "original.json"
    path.write_text("{}", encoding="utf-8")
    row = {"report_sha256": "report", "evidence_sha256": "evidence"}
    monkeypatch.setattr(
        support,
        "load_saved",
        lambda *args: ({"run_id": "original", "manifest": {}}, row, payload()),
    )
    invoked = []

    async def judge(_):
        invoked.append(True)
        result = review()
        if mode == "invalid":
            result.segments[0].report_quote = "invented"
        if mode == "drift":
            next((tmp_path / "evals/results").glob("*/review_input.json")).write_text(
                "{}", encoding="utf-8"
            )
        return result

    monkeypatch.setattr(support, "judge", judge)
    argv = ["review", "--report-results", str(path), "--case-id", "case"]
    if mode != "none":
        argv.append("--execute-judge")
    monkeypatch.setattr(sys, "argv", argv)
    assert support.main() == int(mode in {"invalid", "drift"})
    directory = next((tmp_path / "evals/results").iterdir())
    result = json.loads((directory / "results.json").read_text(encoding="utf-8"))
    assert result["semantic_acceptance"] == "pending_human_review"
    assert result["human_review"] == "pending"
    assert (
        result["status"]
        == {
            "none": "not_requested",
            "valid": "valid_provisional",
            "invalid": "invalid_review",
            "drift": "invalid_input_drift",
        }[mode]
    )
    assert bool(invoked) == (mode != "none")
    assert result["status"] in (directory / "REVIEW.md").read_text(encoding="utf-8")
    if mode == "invalid":
        assert result["grounding_error"] == "Invented report quote"
        assert not (directory / "judge.json").exists()
        assert (directory / "judge_proposal.json").exists()
