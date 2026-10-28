import asyncio
import json
from types import SimpleNamespace

import pytest

from evals.reports_acceptance import handoff_writer as hw
from evals.reports_acceptance import transfer as tr
from evals.reports_acceptance.writer_fidelity import Assertion, StructuredWriter
from evals.runners.experiment import file_sha256
from tests.test_writer_fidelity import ID, record


def local_record():
    return {**record(), "source": "local_document", "metadata": {"filename": "Source.pdf"}}


def test_backend_resolves_short_or_multiline_source_without_rewriting():
    original = {**local_record(), "content": "目录\n第一章\n第二章"}
    case = {
        "parts": [{"part_id": "a", "label": "A", "quote_ids": []}],
        "records": [original],
        "extracts": [],
    }
    result, _ = tr.check_selection(
        tr.SelectionProposal(parts=[tr.PartSelection(part_id="a", evidence_ids=[ID])]), case
    )
    assert result["extracts"][0]["quote"] == original["content"]


def test_selection_cannot_replace_parts_with_unknown_or_duplicate_entries():
    case = {
        "id": "case",
        "parts": [{"part_id": "a", "label": "A", "quote_ids": []}],
        "records": [local_record()],
        "extracts": [],
        "assisted_source_selection": False,
    }
    proposal = tr.SelectionProposal(
        parts=[
            tr.PartSelection(part_id="a", evidence_ids=[ID]),
            tr.PartSelection(part_id="a", evidence_ids=[ID]),
            tr.PartSelection(part_id="unknown", evidence_ids=[ID]),
        ]
    )
    writer_input, checked = tr.check_selection(proposal, case)
    assert not writer_input["extracts"]
    assert not checked["parts"][0]["cardinality_valid"]
    assert checked["unknown_part_ids"] == ["unknown"]
    assert "records" not in writer_input


def test_unknown_id_does_not_reach_writer():
    case = {
        "parts": [{"part_id": "a", "label": "A", "quote_ids": []}],
        "records": [local_record()],
        "extracts": [],
    }
    result, checked = tr.check_selection(
        tr.SelectionProposal(parts=[tr.PartSelection(part_id="a", evidence_ids=["invented"])]),
        case,
    )
    assert not result["extracts"]
    assert checked["parts"][0]["rejected_ids"][0]["reason"] == "unknown_empty_or_oversized_chunk"


@pytest.fixture
def frozen_suite(tmp_path, monkeypatch):
    snapshot = tmp_path / "evidence.json"
    snapshot.write_text(json.dumps({"records": [local_record()]}), encoding="utf-8")
    dataset = tmp_path / "dataset.json"
    dataset.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": f"new_{n}",
                        "question": f"Question {n}",
                        "parts": {"a": "A"},
                        "snapshot": str(snapshot),
                        "snapshot_sha256": file_sha256(snapshot),
                        "record_ids": [ID],
                        "answer_key": "SECRET_KEY",
                    }
                    for n in range(3)
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(tr, "DATASET", dataset)
    monkeypatch.setattr(tr, "safe_path", lambda p: tmp_path / p)
    monkeypatch.setattr(hw, "safe_path", lambda p: tmp_path / p)
    monkeypatch.setattr(hw, "build_manifest", lambda *_: {"source_sha256": "fixed"})
    return snapshot


def test_snapshot_mutation_blocks_before_model_admission(frozen_suite, monkeypatch):
    frozen_suite.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(hw, "experiment_model", lambda: pytest.fail("model admitted"))
    with pytest.raises(ValueError, match="snapshot_changed"):
        asyncio.run(tr.run(execute=True))


def test_default_run_is_offline(frozen_suite, monkeypatch):
    monkeypatch.setattr(hw, "experiment_model", lambda: pytest.fail("offline model call"))
    output = asyncio.run(tr.run())
    result = json.loads((output / "results.json").read_text(encoding="utf-8"))
    assert len(result["cases"]) == 3
    assert sum(row["logical_calls"] for row in result["cases"]) == 0


def test_auto_selection_and_writer_are_separate_and_skip_empty_negative(frozen_suite, monkeypatch):
    stages, schema = [], None

    class Model:
        def with_structured_output(self, value, include_raw):
            nonlocal schema
            schema = value
            return self

        async def ainvoke(self, messages):
            stages.append(schema)
            assert "SECRET_KEY" not in str(messages)
            payload = json.loads(messages[1][1])
            raw = SimpleNamespace(content="raw", usage_metadata={})
            if schema is tr.SelectionProposal:
                assert "records" in payload
                ids = [] if payload["question"] == "Question 2" else [ID]
                proposal = tr.SelectionProposal(
                    parts=[tr.PartSelection(part_id="a", evidence_ids=ids)]
                )
            else:
                assert schema is StructuredWriter and "records" not in payload
                proposal = StructuredWriter(
                    assertions=[
                        Assertion(text="Candidate", quote_ids=[payload["extracts"][0]["quote_id"]])
                    ]
                )
            return {"raw": raw, "parsed": proposal}

    monkeypatch.setattr(hw, "experiment_model", Model)
    output = asyncio.run(tr.run(execute=True))
    result = json.loads((output / "results.json").read_text(encoding="utf-8"))
    assert stages == [
        tr.SelectionProposal,
        StructuredWriter,
        tr.SelectionProposal,
        StructuredWriter,
        tr.SelectionProposal,
    ]
    assert sum(row["logical_calls"] for row in result["cases"]) == 5
    assert result["cases"][-1]["status"] == "no_valid_selected_quotes"
    audit = json.loads((output / "new_2/assertions.json").read_text(encoding="utf-8"))
    assert audit["parts"][0]["reason"] == "no_valid_selected_quote"
    assert not audit["assisted_source_selection"]
