import asyncio
import json
from types import SimpleNamespace

import pytest

from evals.reports_acceptance import handoff_writer as hw
from evals.reports_acceptance.coverage_review import diagnose_review
from evals.reports_acceptance.writer_fidelity import Assertion, StructuredWriter
from evals.runners.experiment import file_sha256
from tests.test_writer_fidelity import ID, TEXT, record


def case():
    return {
        "parts": [
            {"part_id": "one", "label": "One", "quote_ids": ["q1"]},
            {"part_id": "two", "label": "Two", "quote_ids": ["q2"]},
            {"part_id": "gap", "label": "Gap", "quote_ids": []},
        ],
        "extracts": [
            {"quote_id": q, "part_id": p, "evidence_id": ID, "quote": TEXT}
            for q, p in [("q1", "one"), ("q2", "two")]
        ],
    }


def test_handoff_accounts_for_supported_omission_and_reviewed_gap():
    proposal = StructuredWriter(
        assertions=[Assertion(text="Candidate", quote_ids=["q1"])],
        unanswered_topics=["UNVERIFIED FREE TEXT"],
    )
    audit = hw.audit_handoff(proposal, case())
    assert [p["reason"] for p in audit["parts"]] == [
        "linked_candidate",
        "writer_omission",
        "reviewed_evidence_gap",
    ]
    assert audit["candidate_parts"] == 1 and audit["unresolved_parts"] == 2
    assert "UNVERIFIED FREE TEXT" not in hw.render_candidate(audit)


@pytest.mark.parametrize("ids", [["q1", "q2"], ["invented"]])
def test_mixed_part_or_unknown_links_do_not_create_coverage(ids):
    audit = hw.audit_handoff(
        StructuredWriter(assertions=[Assertion(text="Wrong", quote_ids=ids)]), case()
    )
    assert len(audit["rejected"]) == 1
    assert audit["candidate_parts"] == 0
    assert "Wrong" not in hw.render_candidate(audit)


def test_structurally_valid_overstatement_still_needs_semantic_review():
    audit = hw.audit_handoff(
        StructuredWriter(
            assertions=[Assertion(text="Only this platform works.", quote_ids=["q1"])]
        ),
        case(),
    )
    assert audit["parts"][0]["semantic_support"] == "pending_review"


@pytest.fixture
def bound_handoffs(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    rows = []
    for case_id, domains in hw.OFFICIAL_DOMAINS.items():
        folder = source / case_id
        folder.mkdir()
        inputs = {
            "id": case_id,
            "question": "A frozen question",
            "question_parts": {"supported": "Supported", "gap": "Gap"},
            "records": [record(f"https://{domains[0]}/release")],
            "prior_extracts": [],
        }
        audit = {
            "parts": [{"part_id": p, "status": "unresolved"} for p in inputs["question_parts"]],
            "candidate_parts": 0,
            "unresolved_parts": 2,
        }
        reviews = [
            {
                "part_id": "supported",
                "assessment": "sufficient",
                "quotes": [{"evidence_id": ID, "quote": TEXT}],
                "note": "SECRET_REVIEW_NOTE",
            },
            {"part_id": "gap", "assessment": "insufficient", "quotes": []},
        ]
        for name, content in [
            ("inputs.json", inputs),
            ("coverage.json", audit),
            ("diagnostics.json", diagnose_review(inputs, audit, reviews)),
        ]:
            (folder / name).write_text(json.dumps(content), encoding="utf-8")
        review = {
            "parts": reviews,
            "inputs_sha256": file_sha256(folder / "inputs.json"),
            "coverage_sha256": file_sha256(folder / "coverage.json"),
        }
        (folder / "source_review.json").write_text(json.dumps(review), encoding="utf-8")
        rows.append(
            {
                "id": case_id,
                "artifact_sha256": {
                    n: file_sha256(folder / n) for n in ("inputs.json", "coverage.json")
                },
                "offline_review_artifact_sha256": {
                    n: file_sha256(folder / n) for n in ("source_review.json", "diagnostics.json")
                },
            }
        )
    public = tmp_path / "published.json"
    public.write_text(json.dumps({"experiment_run": source.name, "cases": rows}), encoding="utf-8")
    monkeypatch.setattr(hw, "REVIEW_RECORD", public)
    monkeypatch.setattr(hw, "safe_path", lambda p: tmp_path / p)
    monkeypatch.setattr(hw, "build_manifest", lambda *_: {"source_sha256": "fixed"})
    return source


def test_loader_reproduces_review_without_exposing_review_notes(bound_handoffs):
    inputs, hashes = hw.load_handoffs(bound_handoffs)
    assert len(inputs) == 2 and len(hashes) == 9
    assert "SECRET_REVIEW_NOTE" not in str(inputs)
    assert all(len(item["extracts"]) == 1 for item in inputs)


def test_corruption_blocks_before_model_admission(bound_handoffs, monkeypatch):
    path = bound_handoffs / "report_web_002" / "diagnostics.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(hw, "experiment_model", lambda: pytest.fail("model admitted"))
    with pytest.raises(ValueError, match="hash_mismatch"):
        asyncio.run(hw.run(bound_handoffs, execute=True))


def test_default_is_offline_and_retains_every_gap(bound_handoffs, monkeypatch):
    monkeypatch.setattr(hw, "experiment_model", lambda: pytest.fail("offline model call"))
    output = asyncio.run(hw.run(bound_handoffs))
    results = json.loads((output / "results.json").read_text(encoding="utf-8"))
    assert sum(row["logical_calls"] for row in results["cases"]) == 0
    assert sum(row["unresolved_parts"] for row in results["cases"]) == 4


def test_two_calls_keep_parse_failure_and_pass_only_assisted_extracts(bound_handoffs, monkeypatch):
    calls = []

    class Model:
        def with_structured_output(self, schema, include_raw):
            assert schema is StructuredWriter and include_raw
            return self

        async def ainvoke(self, messages):
            calls.append(messages)
            payload = json.loads(messages[1][1])
            assert set(payload) == {"id", "question", "parts", "extracts"}
            assert "SECRET_REVIEW_NOTE" not in str(messages)
            raw = SimpleNamespace(content="raw", usage_metadata={})
            proposal = StructuredWriter(
                assertions=[
                    Assertion(text="Candidate", quote_ids=[payload["extracts"][0]["quote_id"]])
                ]
            )
            return {"raw": raw, "parsed": None if len(calls) == 1 else proposal}

    monkeypatch.setattr(hw, "experiment_model", Model)
    output = asyncio.run(hw.run(bound_handoffs, execute=True))
    results = json.loads((output / "results.json").read_text(encoding="utf-8"))
    assert len(calls) == 2
    assert results["cases"][0]["status"] == "parse_failed"
    assert results["cases"][1]["candidate_parts"] == 1
    assert results["human_accuracy"] is None
