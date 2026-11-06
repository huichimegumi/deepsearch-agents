import json
import sqlite3

import pytest

from app.research.compact_report import SectionDraft
from app.research.query_plan import QueryPlan
from evals.diagnostics import canary_e10 as canary
from evals.diagnostics.e8 import digest


def fixture(tmp_path, monkeypatch):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    database = tmp_path / "control.sqlite"
    with sqlite3.connect(database) as conn:
        conn.executescript("CREATE TABLE numbers(n INTEGER); INSERT INTO numbers VALUES (1);")
    controls = json.loads(canary.PROTOCOL.read_text())["controls"]
    public = [
        {
            "id": c["id"],
            "question": "Return 99",
            "catalog": {
                "allowed_sources": ["sql"],
                "sqlite_path": str(database),
            },
        }
        for c in controls
    ]
    references = [{"id": c["id"], "oracle": {"reference_sql": "SELECT 99 AS n"}} for c in controls]
    evidence = [
        {
            "id": c["id"],
            "evidence": [
                {
                    "evidence_id": "original",
                    "source": "sql",
                    "locator": "fixture:query",
                    "content": {"n": 1},
                    "metadata": {"query": "SELECT n FROM numbers", "truncated": False},
                }
            ],
        }
        for c in controls
    ]
    for name, data in [("public", public), ("references", references)]:
        (inputs / f"{name}.json").write_text(json.dumps(data))
    lock = tmp_path / "lock.json"
    lock.write_text(
        json.dumps({"public_sha256": digest(public), "references_sha256": digest(references)})
    )
    archived = tmp_path / "archived.json"
    archived.write_text(json.dumps(evidence))
    monkeypatch.setattr(canary, "INPUTS", inputs)
    monkeypatch.setattr(canary, "LOCK", lock)
    monkeypatch.setattr(canary, "EVIDENCE", archived)
    return database


@pytest.mark.asyncio
async def test_canary_never_retries_on_reference_mismatch_and_forbids_resume(tmp_path, monkeypatch):
    fixture(tmp_path, monkeypatch)

    class Model:
        sql_calls = 0
        writer_calls = 0

        def with_structured_output(self, schema, **kwargs):
            self.schema = schema
            return self

        def bind(self, **kwargs):
            return self

        async def ainvoke(self, messages):
            payload = json.loads(messages[-1]["content"])
            assert "reference_sql" not in json.dumps(payload)
            assert "actual_engine_feedback" not in payload
            if self.schema is QueryPlan:
                self.sql_calls += 1
                parsed = QueryPlan.model_validate(
                    {
                        "table": "numbers",
                        "grain": "rows",
                        "expressions": [{"key": "value", "op": "column", "ref": "numbers.n"}],
                        "outputs": [{"expression": "value", "alias": "n"}],
                    }
                )
            else:
                assert self.schema is SectionDraft
                self.writer_calls += 1
                parsed = SectionDraft(claim_1="An observed row", refs_1="e1")
            return {"parsed": parsed, "raw": None}

    model = Model()

    def model_for(provider):
        assert provider == "qwen"
        return model

    monkeypatch.setattr(canary, "model_for", model_for)
    output = tmp_path / "run"
    canary.prepare(output)
    summary = await canary.run(output)
    assert model.sql_calls == 1 and model.writer_calls == 2
    assert summary["passes"] == 2 and not summary["canary_passed"]
    assert summary["full_development"].startswith("NOT RUN")
    with pytest.raises(FileExistsError):
        await canary.run(output)
    assert model.sql_calls == 1


@pytest.mark.asyncio
async def test_frozen_database_change_blocks_before_any_model_creation(tmp_path, monkeypatch):
    database = fixture(tmp_path, monkeypatch)
    output = tmp_path / "run"
    canary.prepare(output)
    with sqlite3.connect(database) as conn:
        conn.execute("INSERT INTO numbers VALUES (2)")
    monkeypatch.setattr(
        canary, "model_for", lambda provider: pytest.fail("model must not be created")
    )
    with pytest.raises(ValueError, match="snapshot_changed"):
        await canary.run(output)
    assert not (output / "started.json").exists()


def test_canary_rejects_missing_reordered_or_duplicate_controls():
    manifest = {
        "protocol": {
            "version": "test",
            "controls": [{"id": "a", "kind": "writer"}, {"id": "b", "kind": "assisted_sql"}],
        }
    }
    with pytest.raises(ValueError, match="case_set_or_order"):
        canary.summarize([{"id": "a", "kind": "writer", "passed": True}] * 2, manifest)
