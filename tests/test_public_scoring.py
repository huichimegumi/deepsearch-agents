import json
import sqlite3
from types import SimpleNamespace

import pytest

from evals.public_benchmarks import score as scoring


def test_independent_sql_audit_checks_values_direction_and_readonly(tmp_path):
    db = tmp_path / "data.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE items (name TEXT)")
        conn.execute("INSERT INTO items VALUES ('update')")
    sql = "SELECT name FROM items WHERE name = 'update'"
    case = {
        "oracle": {
            "reference_sql": sql,
            "sql_reference": {"rows": [["update"]]},
            "direction": "search_to_sql",
        }
    }
    result = {
        "operations": [
            {"id": "s0", "source": "web", "record_count": 1},
            {
                "id": "s1",
                "source": "sql",
                "record_count": 1,
                "query": sql,
                "depends_on": ["s0"],
                "bindings": [{"value": "update"}],
            },
        ]
    }
    audit = scoring.reference_audit(case, result, db)
    assert audit["available"] and audit["sql_result_match"] and audit["executed_direction"]
    result["operations"][1]["depends_on"] = []
    assert not scoring.reference_audit(case, result, db)["executed_direction"]
    result["operations"][1]["query"] = "SELECT 'wrong' FROM items"
    assert not scoring.reference_audit(case, result, db)["sql_result_match"]
    with pytest.raises(sqlite3.Error):
        scoring.query(db, "DELETE FROM items")
    assert scoring.query(db, "SELECT COUNT(*) FROM items") == [(1,)]
    assert scoring.canonical([[True]]) != scoring.canonical([[1]])
    assert scoring.canonical([[None]]) != scoring.canonical([["null"]])


@pytest.mark.asyncio
async def test_public_judge_checkpoints_do_not_repeat_requests_and_reject_changed_answer(
    tmp_path, monkeypatch
):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    run = tmp_path / "run"
    run.mkdir()
    case = {
        "id": "one",
        "suite": "dabstep",
        "question": "Where?",
        "oracle": {"answerable": True, "checklist": ["Kyoto"]},
    }
    result = {
        "id": "one",
        "status": "completed",
        "report": {
            "title": "City",
            "answerability": "answered",
            "claims": [{"text": "Kyoto", "evidence_ids": ["ev1_test"]}],
            "facts": [],
            "limitations": [],
        },
        "evidence": [{"source": "local_document", "evidence_id": "ev1_test", "content": "Kyoto"}],
    }
    (inputs / "references.json").write_text(json.dumps([case]))
    (inputs / "public.json").write_text(json.dumps([{"id": "one"}]))
    (run / "results.json").write_text(json.dumps([result]))
    calls = []

    async def judge(*args):
        calls.append(1)
        return {"checklist_coverage": 1, "claim_support": 1}

    monkeypatch.setattr(scoring, "model_for", lambda provider: SimpleNamespace(model_name="test"))
    monkeypatch.setattr(scoring, "judge", judge)
    output = tmp_path / "score"
    assert (await scoring.score(run, inputs, output))["suites"]["dabstep"]["passes"] == 1
    await scoring.score(run, inputs, output)
    assert len(calls) == 1
    result["report"]["claims"][0]["text"] = "Wrong"
    (run / "results.json").write_text(json.dumps([result]))
    with pytest.raises(ValueError, match="scoring_resume_mismatch"):
        await scoring.score(run, inputs, output)


def test_published_rubric_weights_are_not_replaced_by_uniform_mean():
    case = {
        "oracle": {
            "published_rubric": {
                "dimension_weight": {"coverage": 0.7, "style": 0.3},
                "criterions": {"coverage": [{"weight": 1}], "style": [{"weight": 1}]},
            }
        }
    }
    assert scoring.weighted_rubric(case, {"criteria": [{"score": 1}, {"score": 0}]}) == 0.7
