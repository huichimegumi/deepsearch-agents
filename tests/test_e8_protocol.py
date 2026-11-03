import sqlite3

import pytest

from app.research.report import ReportFact, ResearchReport, fact_identity
from evals.diagnostics.score_e8 import equivalent, execute_sql, mechanical


def test_sql_alignment_keeps_row_associations_and_value_types():
    expected = (["name", "n"], [("A", 1), ("B", 2)])
    assert equivalent(expected, (["count", "label"], [(2, "B"), (1, "A")]))
    assert not equivalent(expected, (["count", "label"], [(1, "B"), (2, "A")]))
    assert equivalent(
        expected, (["other", "name", "n"], [("ignored", "A", 1), ("ignored", "B", 2)])
    )
    assert not equivalent((["id"], [("001",)]), (["id"], [(1,)]))
    assert not equivalent((["flag"], [(True,)]), (["flag"], [(1,)]))
    assert not equivalent((["x"], [(None,)]), (["x"], [("null",)]))
    assert not equivalent((["n"], [(0,)]), (["n"], []))


def test_independent_sql_accepts_bound_quoted_values_and_rejects_writes(tmp_path):
    db = tmp_path / "data.sqlite"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE items(name TEXT)")
        c.execute("INSERT INTO items VALUES (?)", ("O'Reilly update",))
    assert execute_sql(
        db, "SELECT COUNT(*) AS n FROM items WHERE name=:name", {"name": "O'Reilly update"}
    )[1] == [(1,)]
    with pytest.raises(sqlite3.Error):
        execute_sql(db, "DELETE FROM items")


def test_scoped_metrics_and_sections_do_not_hide_duplicate_or_unbound_facts():
    a = ReportFact(
        metric="count",
        entity="A",
        period="2026",
        unit="items",
        value="1",
        evidence_id="a",
        path=["n"],
        section="Counts",
    )
    b = ReportFact(
        metric="count",
        entity="B",
        period="2026",
        unit="items",
        value="2",
        evidence_id="b",
        path=["n"],
        section="Counts",
    )
    assert fact_identity(a) != fact_identity(b)
    report = ResearchReport(title="Counts", answerability="answered", facts=[a, b], claims=[])
    result = {
        "status": "completed",
        "report": report.model_dump(),
        "evidence": [
            {"evidence_id": "a", "source": "sql", "content": {"n": 1}},
            {"evidence_id": "b", "source": "sql", "content": {"n": 2}},
        ],
    }
    case = {"oracle": {"answerable": True}}
    assert not mechanical(case, result)
    assert "## Counts" in report.render()
    assert "| A | 2026 | 1 | items |" in report.render()
    result["report"]["facts"].append(a.model_dump())
    assert "duplicate_scoped_metric" in mechanical(case, result)
    result["report"]["facts"][0]["value"] = "99"
    assert any("numeric_binding_mismatch" in error for error in mechanical(case, result))


def test_development_gate_rejects_stale_scores_and_changed_references(tmp_path, monkeypatch):
    import json

    from evals.diagnostics import gate_e8
    from evals.diagnostics.e8 import digest

    run, score = tmp_path / "run", tmp_path / "score"
    run.mkdir()
    score.mkdir()
    ids = [str(i) for i in range(8)]
    results = [
        {
            "id": key,
            "model_reservations": {"requests": 8, "reserved_tokens": 180000},
            "elapsed_seconds": 299,
            "operations": [None] * 5,
        }
        for key in ids
    ]
    grades = [{"id": key, "pass": i < 6, "issues": []} for i, key in enumerate(ids)]
    lock = tmp_path / "lock.json"
    lock.write_text(
        json.dumps({"cases": [{"id": key} for key in ids], "references_sha256": "original"})
    )
    monkeypatch.setattr(gate_e8, "LOCK", lock)
    (run / "results.json").write_text(json.dumps(results))
    (score / "scores.json").write_text(json.dumps({"rows": grades}))
    manifest = {"version": "e8.1", "results_sha256": digest(results), "cases_sha256": "original"}
    (score / "manifest.json").write_text(json.dumps(manifest))
    assert gate_e8.evaluate(run, score)["passed"]
    grades[0]["issues"] = ["unknown_citation"]
    (score / "scores.json").write_text(json.dumps({"rows": grades}))
    assert not gate_e8.evaluate(run, score)["passed"]
    manifest["cases_sha256"] = "changed"
    (score / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="references_changed"):
        gate_e8.evaluate(run, score)
    manifest.update(cases_sha256="original", results_sha256="stale")
    (score / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="scores_stale"):
        gate_e8.evaluate(run, score)
