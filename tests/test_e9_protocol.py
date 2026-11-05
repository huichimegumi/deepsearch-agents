import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from evals.diagnostics.score_e9 import judge_chunk, statistics


def test_unknown_grades_are_excluded_from_observed_means():
    rows = [
        {"coverage": None, "support": None, "pass": False, "judge_errors": ["parse"]},
        {"coverage": 0.5, "support": 1, "pass": False, "judge_errors": []},
    ]
    summary = statistics(rows)
    assert summary["coverage_observed"] == 1
    assert summary["mean_observed_coverage"] == 0.5
    assert summary["judge_error_cases"] == 1


@pytest.mark.asyncio
async def test_fixed_judge_fields_reject_extra_keys_and_hide_other_claims():
    class Model:
        def with_structured_output(self, schema, **kwargs):
            self.schema = schema
            with pytest.raises(ValidationError):
                schema(item_0=1, item_1=1)
            return self

        def bind(self, **kwargs):
            return self

        async def ainvoke(self, messages):
            payload = json.loads(messages[-1]["content"])
            assert list(payload["items"]) == ["item_0"]
            assert "hidden" not in json.dumps(payload)
            return {"parsed": self.schema(item_0=1), "raw": SimpleNamespace()}

    result = {
        "report": {
            "title": "Example",
            "answerability": "answered",
            "claims": [{"text": "hidden", "evidence_ids": []}],
        },
        "evidence": [],
    }
    assert (
        await judge_chunk(
            "claims",
            [{"text": "current", "evidence_ids": []}],
            {"question": "test", "oracle": {}},
            result,
            Model(),
        )
    )["scores"] == [1]


def test_public_worker_defaults_to_qwen_without_touching_global_provider(tmp_path, monkeypatch):
    import os

    from app.research import bounded
    from evals.public_benchmarks import run, score

    model = object()
    selected = []
    monkeypatch.setattr(score, "model_for", lambda p: selected.append(p) or model)

    async def execute(*args, **kwargs):
        assert kwargs["model"] is model
        return {"status": "completed"}

    monkeypatch.setattr(bounded, "execute", execute)
    path = tmp_path / "public.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "test",
                    "suite": "authored",
                    "question": "test",
                    "catalog": {"allowed_sources": ["web"]},
                }
            ]
        )
    )
    monkeypatch.setenv("LLM_PROVIDER", "unchanged")
    run.worker(path, "test", "adaptive", tmp_path / "result.json")
    assert selected == ["qwen"]
    assert os.environ["LLM_PROVIDER"] == "unchanged"


def test_component_gate_recomputes_rows_and_rejects_a_different_case_set(tmp_path, monkeypatch):
    from evals.diagnostics import gate_e9
    from evals.diagnostics.e8 import digest

    writer, sql = tmp_path / "writer", tmp_path / "sql"
    writer.mkdir()
    sql.mkdir()
    ids = [f"case-{i}" for i in range(8)]
    lock = tmp_path / "lock.json"
    lock.write_text(
        json.dumps(
            {
                "cases": [
                    {"id": key, "suite": "hybrid" if i >= 2 else "dabstep"}
                    for i, key in enumerate(ids)
                ]
            }
        )
    )
    source = tmp_path / "evals/results/e8-4-recheck/results.json"
    source.parent.mkdir(parents=True)
    source.write_text("[]")
    monkeypatch.setattr(gate_e9, "ROOT", tmp_path)
    monkeypatch.setattr(gate_e9, "LOCK", lock)
    (writer / "manifest.json").write_text(
        json.dumps({"provider": "qwen", "source_results_sha256": digest([])})
    )
    (sql / "manifest.json").write_text(json.dumps({"provider": "qwen"}))
    (writer / "summary.json").write_text(
        json.dumps(
            {
                "live_passes": 8,
                "cases": [
                    {"id": key, "offline_pass": True, "live_pass": i < 5}
                    for i, key in enumerate(ids)
                ],
            }
        )
    )
    queries = {"cases": [{"id": key, "sql_result_match": True} for key in ids[2:]]}
    (sql / "summary.json").write_text(json.dumps(queries))
    result = gate_e9.evaluate(writer, sql)
    assert result["writer_passes"] == 5
    assert not result["components_passed"]
    assert result["full_development"].startswith("NOT RUN")
    queries["cases"][0]["id"] = "different"
    (sql / "summary.json").write_text(json.dumps(queries))
    with pytest.raises(ValueError, match="selection_mismatch"):
        gate_e9.evaluate(writer, sql)
