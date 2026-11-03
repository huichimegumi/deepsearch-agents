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


@pytest.mark.asyncio
async def test_claim_judge_receives_only_current_batch_not_other_report_claims():
    import json
    from types import SimpleNamespace

    from evals.diagnostics.score_e8 import judge_chunk

    class Model:
        def with_structured_output(self, schema, **kwargs):
            self.schema = schema
            return self

        def bind(self, **kwargs):
            return self

        async def ainvoke(self, messages):
            payload = json.loads(messages[-1]["content"])
            assert payload["number_of_items"] == 4
            assert len(payload["items"]) == 4
            assert "claims" not in payload["candidate"]
            assert "excluded" not in json.dumps(payload)
            return {"parsed": self.schema(scores=[1] * 4), "raw": SimpleNamespace()}

    claims = [{"text": "supported", "evidence_ids": ["a"]}] * 4
    result = {
        "report": {
            "title": "Example",
            "answerability": "answered",
            "claims": claims + [{"text": "excluded", "evidence_ids": ["b"]}],
        },
        "evidence": [
            {"evidence_id": "a", "source": "web", "content": "supported"},
            {"evidence_id": "b", "source": "web", "content": "excluded"},
        ],
    }
    assert (
        await judge_chunk("claims", claims, {"question": "test", "oracle": {}}, result, Model())
    )["scores"] == [1] * 4


def test_requested_evidence_displaces_bulk_and_focuses_a_later_passage(tmp_path):
    from app.research.evidence_store import EvidenceStore

    store = EvidenceStore(tmp_path)
    original = "preface " * 1200 + "needle target passage " * 300
    store.add(
        [{"evidence_id": "read", "source": "web", "locator": "fixture:long", "content": original}],
        "s0",
    )
    initial = store.select("preface")
    focused = store.select("preface", preferred_ids=["read"], focus_query="needle")
    assert initial["evidence"][0]["excerpt"]["start"] == 0
    assert focused["evidence"][0]["excerpt"]["start"] > 0
    assert "needle" in focused["evidence"][0]["content"]
    assert store.records["read"]["content"] == original
    store.add(
        [
            {
                "evidence_id": f"bulk-{i}",
                "source": "web",
                "locator": f"fixture:{i}",
                "content": "preface " + "filler " * 300,
            }
            for i in range(10)
        ],
        "s1",
    )
    bulk = store.select("preface", max_tokens=1800)
    requested = store.select(
        "preface", max_tokens=1800, preferred_ids=["read"], focus_query="needle"
    )
    assert "read" not in {row["evidence_id"] for row in bulk["evidence"]}
    assert "read" in {row["evidence_id"] for row in requested["evidence"]}


def test_sql_to_web_direction_requires_a_new_web_query_not_a_memory_read(tmp_path):
    from evals.diagnostics.score_e8 import reference_audit

    db = tmp_path / "direction.sqlite"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE items(n INTEGER)")
        connection.execute("INSERT INTO items VALUES (1)")
    case = {
        "oracle": {
            "reference_sql": "SELECT n FROM items",
            "sql_reference": {"rows": [[1]]},
            "direction": "sql_to_search",
        }
    }
    result = {
        "operations": [
            {"id": "s0", "source": "web", "operation": "query", "record_count": 1},
            {
                "id": "s1",
                "source": "sql",
                "operation": "query",
                "query": "SELECT n FROM items",
                "record_count": 1,
            },
            {
                "id": "s2",
                "source": "web",
                "operation": "read_evidence",
                "depends_on": ["s1"],
                "record_count": 1,
            },
        ]
    }
    audit = reference_audit(case, result, db)
    assert audit["sql_result_match"]
    assert not audit["executed_direction"]
    result["operations"][2]["operation"] = "query"
    assert reference_audit(case, result, db)["executed_direction"]
