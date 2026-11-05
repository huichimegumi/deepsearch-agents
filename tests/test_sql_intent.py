import json
import sqlite3

import pytest

from app.research.actions import describe, sql_query
from app.research.sources import SourceCatalog
from app.research.sql_intent import SQLIntent, execute_intent
from evals.diagnostics.e8 import digest


def database(tmp_path):
    path = tmp_path / "data.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE customers(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)")
        conn.execute(
            "CREATE TABLE charges(customer_id INTEGER REFERENCES customers(id), month TEXT, amount REAL)"
        )
        conn.execute("INSERT INTO customers VALUES (1, ?)", ("O'Reilly:client",))
        conn.executemany(
            "INSERT INTO charges VALUES (1, ?, ?)",
            [("2026-01", 5), ("2026-01", 7), ("2026-02", 11)],
        )
    return path


def intent(sql):
    return SQLIntent(
        metrics="sum amount",
        entity_scope="bound customer",
        period_scope="observed months",
        grain="one row per customer and month",
        relationships="charges.customer_id=customers.id",
        sql=sql,
    )


def test_typed_joined_aggregation_preserves_grain_and_schema_constraints(tmp_path):
    db = database(tmp_path)
    info = describe(SourceCatalog(sqlite_path=db, allowed_sources=("sql",)), "sum by month")
    assert info["sql_dialect"] == "sqlite"
    tables = {t["table"]: t for t in info["sql_tables"]}
    assert tables["charges"]["foreign_keys"][0]["target_table"] == "customers"
    assert (
        next(c for c in tables["customers"]["columns"] if c["name"] == "id")["primary_key_position"]
        == 1
    )
    records, _, parameters, observation = execute_intent(
        db,
        intent(
            "SELECT c.name AS entity, month, SUM(amount) AS total FROM customers c JOIN charges d ON d.customer_id=c.id WHERE c.name=:v1 GROUP BY c.name, month ORDER BY month"
        ),
        {"v1": "O'Reilly:client", "v2": "unused"},
    )
    assert [r["content"]["total"] for r in records] == [12, 11]
    assert parameters == {"v1": "O'Reilly:client"}
    assert observation["read_tables"] == ["charges", "customers"]
    with pytest.raises(sqlite3.Error):
        execute_intent(db, intent("DELETE FROM charges"), {})
    assert sql_query(db, "SELECT COUNT(*) AS n FROM charges", {})[0][0]["content"]["n"] == 3


def test_literals_and_comments_are_not_parameters_and_duplicate_columns_are_rejected(tmp_path):
    db = database(tmp_path)
    records, _ = sql_query(
        db, "SELECT ':literal' AS label, :value AS n /* :ignored */ -- :other\n", {"value": 7}
    )
    assert records[0]["content"] == {"label": ":literal", "n": 7}
    with pytest.raises(ValueError, match="duplicate_query_output_columns"):
        sql_query(db, "SELECT 1 AS n, 2 AS n", {})


@pytest.mark.asyncio
async def test_wrong_nonempty_sql_never_receives_reference_feedback(tmp_path, monkeypatch):
    from evals.diagnostics import sql_component_e9 as component

    db = database(tmp_path)
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    public = [
        {
            "id": "synthetic",
            "suite": "hybrid",
            "question": "Return the number 99",
            "catalog": {"allowed_sources": ["sql"], "sqlite_path": str(db)},
        }
    ]
    references = [
        {
            "id": "synthetic",
            "suite": "hybrid",
            "oracle": {"reference_sql": "SELECT 99 AS n", "direction": "parallel"},
        }
    ]
    (inputs / "public.json").write_text(json.dumps(public))
    (inputs / "references.json").write_text(json.dumps(references))
    lock = tmp_path / "lock.json"
    lock.write_text(
        json.dumps(
            {
                "public_sha256": digest(public),
                "references_sha256": digest(references),
                "component_sql": {"mode": "authored assisted control"},
            }
        )
    )
    monkeypatch.setattr(component, "INPUTS", inputs)
    monkeypatch.setattr(component, "LOCK", lock)

    class Model:
        calls = 0

        def with_structured_output(self, schema, **kwargs):
            self.schema = schema
            return self

        def bind(self, **kwargs):
            return self

        async def ainvoke(self, messages):
            self.calls += 1
            payload = json.loads(messages[-1]["content"])
            assert "reference_sql" not in json.dumps(payload)
            assert "actual_engine_feedback" not in payload
            return {"parsed": intent("SELECT 1 AS n"), "raw": None}

    model = Model()
    monkeypatch.setattr(
        component, "model_for", lambda provider: model if provider == "qwen" else None
    )
    summary = await component.run(tmp_path / "output")
    assert not summary["cases"][0]["sql_result_match"]
    assert model.calls == 1
