import asyncio
import json
from types import SimpleNamespace

import pytest

from evals.reports_acceptance import coverage as cv
from evals.reports_acceptance import writer_fidelity as wf
from tests.test_writer_fidelity import ID, TEXT, frozen_inputs, record  # noqa: F401


def answer(**overrides):
    return cv.PartAnswer(
        **{
            "part_id": "part",
            "status": "candidate_answer",
            "text": "A candidate",
            "quotes": [{"evidence_id": ID, "quote": TEXT}],
            **overrides,
        }
    )


def test_omitted_and_unknown_parts_cannot_hide_required_gaps():
    audit = cv.audit_parts(
        cv.CoverageProposal(parts=[answer(part_id="invented")]),
        {"first": "First part", "second": "Second part"},
        [record()],
        [],
    )
    assert audit["candidate_parts"] == 0 and audit["unresolved_parts"] == 2
    assert audit["unknown_part_ids"] == ["invented"]
    assert all(row["reason"] == "omitted_part" for row in audit["parts"])
    assert "First part" in cv.render_coverage(audit)
    assert "Second part" in cv.render_coverage(audit)
    assert "A candidate" not in cv.render_coverage(audit)


def test_duplicate_part_is_unresolved_instead_of_last_write_winning():
    audit = cv.audit_parts(
        cv.CoverageProposal(parts=[answer(), answer()]), {"part": "Part"}, [record()], []
    )
    assert audit["parts"][0]["reason"] == "duplicate_part"


@pytest.mark.parametrize(
    "overrides",
    [
        {"quotes": []},
        {"text": " "},
        {"text": "Bad [ev1_web_unknown]"},
        {"quotes": [{"evidence_id": ID, "quote": TEXT.upper()}]},
        {"quotes": [{"evidence_id": "unknown", "quote": TEXT}]},
    ],
)
def test_unusable_quote_or_answer_remains_unresolved(overrides):
    audit = cv.audit_parts(
        cv.CoverageProposal(parts=[answer(**overrides)]), {"part": "Part"}, [record()], []
    )
    assert audit["parts"][0]["reason"] == "invalid_answer_or_source_quote"
    assert not audit["parts"][0]["text"]


def test_unresolved_payload_cannot_smuggle_factual_answer():
    audit = cv.audit_parts(
        cv.CoverageProposal(parts=[answer(status="unresolved")]), {"part": "Part"}, [record()], []
    )
    assert audit["parts"][0]["reason"] == "inconsistent_unresolved_payload"
    assert "A candidate" not in cv.render_coverage(audit)


def test_new_source_span_differs_from_semantic_support_or_completeness():
    proposal = cv.CoverageProposal(parts=[answer(text="Only these installers work.")])
    audit = cv.audit_parts(proposal, {"part": "Part"}, [record()], [])
    row = audit["parts"][0]
    assert row["additional_source_spans"] == 1
    assert row["semantic_support"] == "pending_review"  # Wrong scope still passes links.
    carried = cv.audit_parts(
        proposal, {"part": "Part"}, [record()], [{"evidence_id": ID, "quote": TEXT}]
    )
    assert carried["parts"][0]["additional_source_spans"] == 0


@pytest.fixture
def configured(request, monkeypatch, tmp_path):
    saved_inputs = request.getfixturevalue("frozen_inputs")
    monkeypatch.setattr(cv, "safe_path", lambda p: tmp_path / p)
    monkeypatch.setattr(cv, "DATASET", wf.DATASET)
    monkeypatch.setattr(cv, "build_manifest", lambda *_: {"source_sha256": "fixed"})
    return saved_inputs


def test_offline_run_accounts_for_all_seven_parts_without_model(configured, monkeypatch):
    monkeypatch.setattr(cv, "experiment_model", lambda: pytest.fail("offline model call"))
    output = asyncio.run(cv.run(configured))
    result = json.loads((output / "results.json").read_text(encoding="utf-8"))
    assert sum(row["logical_calls"] for row in result["cases"]) == 0
    assert sum(row["unresolved_parts"] for row in result["cases"]) == 7
    assert result["inputs_unchanged"] and result["source_unchanged"]


def test_execute_uses_actual_sources_not_answer_keys_and_retains_parse_failure(
    configured, monkeypatch
):
    calls = []

    class FakeModel:
        def with_structured_output(self, schema, include_raw):
            assert schema is cv.CoverageProposal and include_raw
            return self

        async def ainvoke(self, messages):
            calls.append(messages)
            payload = json.loads(messages[1][1])
            assert set(payload) == {"question", "question_parts", "records"}
            assert "SECRET_ANSWER_KEY" not in str(messages)
            raw = SimpleNamespace(content="raw", usage_metadata={})
            return {"raw": raw, "parsed": None if len(calls) == 1 else cv.CoverageProposal()}

    monkeypatch.setattr(cv, "experiment_model", FakeModel)
    output = asyncio.run(cv.run(configured, execute=True))
    result = json.loads((output / "results.json").read_text(encoding="utf-8"))
    assert len(calls) == 2
    assert result["cases"][0]["status"] == "parse_failed"
    assert sum(row["unresolved_parts"] for row in result["cases"]) == 7
    assert result["human_accuracy"] is None
