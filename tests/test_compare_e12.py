import json
import sqlite3

import pytest

from app.research.grounded_sql import SQLCandidate
from app.research.metric_selection import MetricSelection
from evals.diagnostics import compare_e12 as comparison
from evals.diagnostics.e8 import digest


def fixture(tmp_path, monkeypatch):
    db = tmp_path / "db.sqlite"
    with sqlite3.connect(db) as conn:
        conn.executescript("CREATE TABLE numbers(n INTEGER); INSERT INTO numbers VALUES(1);")
    ids = json.loads(comparison.PROTOCOL.read_text())["cases"]
    public = [
        {
            "id": key,
            "question": "Return the stored number",
            "catalog": {"sqlite_path": str(db), "allowed_sources": ["sql"]},
        }
        for key in ids
    ]
    refs = [{"id": key, "oracle": {"reference_sql": "SELECT 99 AS n"}} for key in ids]
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    for name, data in [("public", public), ("references", refs)]:
        (inputs / f"{name}.json").write_text(json.dumps(data))
    lock = tmp_path / "lock.json"
    lock.write_text(
        json.dumps({"public_sha256": digest(public), "references_sha256": digest(refs)})
    )
    monkeypatch.setattr(comparison, "INPUTS", inputs)
    monkeypatch.setattr(comparison, "LOCK", lock)


@pytest.mark.asyncio
async def test_same_inputs_equal_budget_no_gold_retry_and_no_paid_resume(tmp_path, monkeypatch):
    fixture(tmp_path, monkeypatch)

    class Model:
        calls = 0
        payloads = []

        def with_structured_output(self, schema, **kwargs):
            self.schema = schema
            return self

        def bind(self, **kwargs):
            return self

        async def ainvoke(self, messages):
            self.calls += 1
            payload = json.loads(messages[-1]["content"])
            self.payloads.append(payload)
            assert "reference_sql" not in json.dumps(payload)
            assert "actual_engine_feedback" not in payload
            if self.schema is MetricSelection:
                parsed = MetricSelection(table="numbers", outputs="c1")
            else:
                assert self.schema is SQLCandidate
                parsed = SQLCandidate(sql="SELECT c1 FROM r1")
            return {"parsed": parsed, "raw": None}

    model = Model()

    def model_for(provider):
        assert provider == "qwen"
        return model

    monkeypatch.setattr(comparison, "model_for", model_for)
    original_grade = comparison.grade

    def grade(output, manifest, results):
        assert (
            model.calls == 4
            and len(json.loads((output / "generation.json").read_text())["cases"]) == 4
        )
        return original_grade(output, manifest, results)

    monkeypatch.setattr(comparison, "grade", grade)
    output = tmp_path / "run"
    comparison.prepare(output)
    summary = await comparison.run(output)
    assert model.calls == 4  # Nonempty wrong answers never receive gold-driven retries.
    assert all(r["status"] == "executed" and not r["sql_result_match"] for r in summary["cases"])
    assert summary["selected_route"] == "projected_sql" and not summary["eligible_for_components"]
    for key in json.loads(comparison.PROTOCOL.read_text())["cases"]:
        assert len({r["input_sha256"] for r in summary["cases"] if r["id"] == key}) == 1
    assert model.payloads[0] == model.payloads[1]
    with pytest.raises(FileExistsError, match="resume_forbidden"):
        await comparison.run(output)
    assert model.calls == 4
    # Backend-only replay can use a changed implementation, but may not create a
    # model, rewrite the candidate or pick the best of multiple attempts.
    monkeypatch.setattr(
        comparison, "model_for", lambda _: pytest.fail("No model in offline replay")
    )
    monkeypatch.setattr(comparison, "code_hash", lambda: "changed-backend")
    replayed = comparison.replay(output, tmp_path / "offline")
    assert replayed["api_calls"] == 0 and replayed["last_attempt_matches"] == 0
    assert all(c["last_attempt"]["attempt"] == 1 for c in replayed["cases"])
    first = json.loads(comparison.PROTOCOL.read_text())["cases"][0]
    candidate = comparison.case_dir(output, first) / "projected_sql/candidate-1.json"
    candidate.write_text(json.dumps({"sql": "SELECT 99 FROM r1"}))
    with pytest.raises(ValueError, match="candidate_trace_changed"):
        comparison.replay(output, tmp_path / "tampered-offline")


@pytest.mark.asyncio
async def test_mutated_common_packet_is_blocked_before_model_creation(tmp_path, monkeypatch):
    fixture(tmp_path, monkeypatch)
    output = tmp_path / "run"
    comparison.prepare(output)
    first = json.loads(comparison.PROTOCOL.read_text())["cases"][0]
    packet = comparison.case_dir(output, first) / "input.json"
    packet.write_text(json.dumps({"question": "changed"}))
    monkeypatch.setattr(comparison, "model_for", lambda _: pytest.fail("Must not create model"))
    with pytest.raises(ValueError, match="packet_changed"):
        await comparison.run(output)
    assert not (output / "started.json").exists()


def test_missing_or_duplicate_arms_cannot_be_scored():
    manifest = {
        "frozen": {"protocol": {"cases": ["a", "b"], "routes": ["selection", "projected_sql"]}}
    }
    with pytest.raises(ValueError, match="arm_set_changed"):
        comparison.grade(None, manifest, [{"id": "a", "route": "selection"}] * 4)
