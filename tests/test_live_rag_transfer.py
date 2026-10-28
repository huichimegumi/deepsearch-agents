import asyncio
import json
from types import SimpleNamespace

import pytest

from evals.reports_acceptance import handoff_writer as hw
from evals.reports_acceptance import rag_transfer as rt
from evals.reports_acceptance.transfer import PartSelection, SelectionProposal
from evals.reports_acceptance.writer_fidelity import Assertion, StructuredWriter
from evals.runners.experiment import file_sha256
from tests.test_writer_fidelity import ID, record


@pytest.fixture
def configured(tmp_path, monkeypatch):
    dataset = tmp_path / "questions.json"
    dataset.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": f"case_{n}",
                        "question": f"Question {n}",
                        "parts": {"detail": "Detail"},
                        "snapshot": "MUST_NOT_READ",
                        "record_ids": ["OLD_POOL_ID"],
                    }
                    for n in range(3)
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(rt, "DATASET", dataset)
    monkeypatch.setattr(rt, "safe_path", lambda p: tmp_path / p)
    monkeypatch.setattr(hw, "safe_path", lambda p: tmp_path / p)

    def manifest(path, config):
        return {
            "source_sha256": "fixed",
            "dataset_sha256": file_sha256(path),
            "configuration": config,
        }

    monkeypatch.setattr(rt, "build_manifest", manifest)
    monkeypatch.setattr(hw, "build_manifest", manifest)
    monkeypatch.setattr(rt, "corpus", lambda: [{"document": "actual_corpus"}])
    return tmp_path


def batch(query):
    records = (
        []
        if query == "Question 2"
        else [
            {
                **record(),
                "source": "local_document",
                "metadata": {"filename": "Actual.pdf", "rerank_applied": True},
            }
        ]
    )
    return {"query": query, "status": "OK" if records else "NO_EVIDENCE", "records": records}


def test_plan_does_not_touch_services_or_known_source_pools(configured, monkeypatch):
    monkeypatch.setattr(rt, "corpus", lambda: pytest.fail("plan accessed corpus"))
    monkeypatch.setattr(rt, "retrieve_case", lambda _: pytest.fail("plan retrieved"))
    output = rt.prepare()
    result = json.loads((output / "results.json").read_text(encoding="utf-8"))
    assert result["status"] == "plan_only" and result["model_calls"] == 0


def test_retrieval_uses_original_questions_once_and_binds_only_actual_records(
    configured, monkeypatch
):
    calls = []
    monkeypatch.setattr(rt, "retrieve_case", lambda q: (calls.append(q), batch(q))[1])
    output = rt.prepare(retrieve=True)
    assert calls == ["Question 0", "Question 1", "Question 2"]
    cases, _ = rt.load_retrieved(output)
    assert cases[0]["records"][0]["evidence_id"] == ID
    assert "OLD_POOL_ID" not in str(cases)
    assert cases[-1]["records"] == []


@pytest.mark.parametrize("failure", ["error", "corpus_change"])
def test_infrastructure_error_or_corpus_drift_cannot_feed_writer(configured, monkeypatch, failure):
    if failure == "error":

        def failed(_):
            raise RuntimeError("private infrastructure detail")

        monkeypatch.setattr(rt, "retrieve_case", failed)
    else:
        monkeypatch.setattr(rt, "retrieve_case", batch)
        snapshots = iter([[{"version": 1}], [{"version": 2}]])
        monkeypatch.setattr(rt, "corpus", lambda: next(snapshots))
    output = rt.prepare(retrieve=True)
    monkeypatch.setattr(hw, "experiment_model", lambda: pytest.fail("model admitted"))
    with pytest.raises(ValueError, match="invalid_retrieval"):
        asyncio.run(rt.write(output, execute=True))
    assert "private infrastructure detail" not in (output / "results.json").read_text(
        encoding="utf-8"
    )


def test_mutated_retrieved_inputs_block_model_admission(configured, monkeypatch):
    monkeypatch.setattr(rt, "retrieve_case", batch)
    output = rt.prepare(retrieve=True)
    (output / "case_1/inputs.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(hw, "experiment_model", lambda: pytest.fail("model admitted"))
    with pytest.raises(ValueError, match="hash_mismatch"):
        asyncio.run(rt.write(output, execute=True))


def test_actual_empty_retrieval_skips_both_models(configured, monkeypatch):
    monkeypatch.setattr(rt, "retrieve_case", batch)
    output = rt.prepare(retrieve=True)
    calls, schema = [], None

    class Model:
        def with_structured_output(self, value, include_raw):
            nonlocal schema
            schema = value
            return self

        async def ainvoke(self, messages):
            calls.append(schema)
            payload = json.loads(messages[1][1])
            assert "OLD_POOL_ID" not in str(payload)
            raw = SimpleNamespace(content="raw", usage_metadata={})
            proposal = (
                SelectionProposal(parts=[PartSelection(part_id="detail", evidence_ids=[ID])])
                if schema is SelectionProposal
                else StructuredWriter(
                    assertions=[
                        Assertion(text="Candidate", quote_ids=[payload["extracts"][0]["quote_id"]])
                    ]
                )
            )
            return {"raw": raw, "parsed": proposal}

    monkeypatch.setattr(hw, "experiment_model", Model)
    result_path = asyncio.run(rt.write(output, execute=True))
    result = json.loads((result_path / "results.json").read_text(encoding="utf-8"))
    assert len(calls) == 4
    assert result["cases"][-1]["logical_calls"] == 0
    assert result["cases"][-1]["unresolved_parts"] == 1
