import json
import sqlite3

import pytest

from app.research.grounded_sql import MetricRelations, grounded_context
from app.research.metrics import MetricRegistry
from app.research.query_plan import BoundValue
from app.research.sources import SourceCatalog


def fixture(tmp_path):
    db = tmp_path / "source.sqlite"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            "CREATE TABLE samples(name TEXT, region TEXT, amount REAL, loss REAL); INSERT INTO samples VALUES ('Alpha','N',10,20),('Beta','N',20,10),('Gamma','S',100,0);"
        )
    entries = [
        {
            "id": 1,
            "type": "calculation_knowledge",
            "definition": r"$\text{net} = \text{amount} * (1 - \frac{\text{loss}}{100})$",
            "children_knowledge": -1,
        }
    ]
    return db, entries


def test_metric_relations_preserve_all_rows_and_public_formula_values(tmp_path):
    db, entries = fixture(tmp_path)
    reg = MetricRegistry(db, entries)
    ids = {ref.split(".")[1]: key for key, ref in reg.columns.items()}
    relations = MetricRelations(reg, ["samples"])
    try:
        columns, rows = relations.execute(
            f"SELECT {ids['name']},m1 FROM r1 WHERE {ids['region']}=:v1 ORDER BY m1 DESC",
            {"v1": BoundValue(value="N", source_ref="observed")},
        )
        assert rows == [("Beta", 18), ("Alpha", 8)]
        assert columns == [ids["name"], "m1"] and relations.counts == {"r1": 3}
        assert set(relations.sources) == {"m1"}
        # SQL can express grouping/ranking without generating any metric formula.
        _, rows = relations.execute("SELECT m1 FROM r1 ORDER BY m1 ASC LIMIT 1", {})
        assert rows == [(8,)]
    finally:
        relations.close()
    with pytest.raises(ValueError, match="row_budget"):
        MetricRelations(reg, ["samples"], max_rows=2)


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM r1",
        "ATTACH DATABASE ':memory:' AS x",
        "SELECT * FROM samples",
        "SELECT * FROM sqlite_master",
        "SELECT randomblob(1000000) FROM r1",
    ],
)
def test_baseline_cannot_write_read_original_or_use_unapproved_functions(tmp_path, query):
    db, entries = fixture(tmp_path)
    relations = MetricRelations(MetricRegistry(db, entries), ["samples"])
    try:
        with pytest.raises(sqlite3.Error):
            relations.execute(query, {})
        assert relations.execute("SELECT COUNT(*) FROM r1", {})[1] == [(3,)]
    finally:
        relations.close()
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM samples").fetchone() == (3,)


def test_context_comes_only_from_public_catalog_and_observed_database(tmp_path):
    db, entries = fixture(tmp_path)
    cat = SourceCatalog(
        sqlite_path=db,
        allowed_sources=("sql",),
        schema_notes="\n".join(json.dumps(e) for e in entries),
    )
    reg, observed, relations, payload = grounded_context(cat, "Find the largest net value in N")
    try:
        assert payload["datasets"][0]["relation"] == "r1"
        assert "reference_sql" not in json.dumps(payload)
        assert observed.values and all(v.field_ref for v in observed.values.values())
        assert all(
            v.source_ref in {e["evidence_id"] for e in observed.evidence}
            for v in observed.values.values()
        )
        assert {f["id"] for f in payload["datasets"][0]["fields"]} == {
            f["id"] for f in reg.catalog("samples")
        }
        with pytest.raises(ValueError, match="duplicate_query_output"):
            relations.execute("SELECT 1 AS n,2 AS n FROM r1", {})
        with pytest.raises(ValueError, match="row_budget"):
            relations.execute("SELECT * FROM r1", {}, limit=2)
        with pytest.raises(sqlite3.OperationalError, match="interrupted"):
            relations.execute(
                "WITH RECURSIVE x(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM x) SELECT SUM(n) FROM x",
                {},
                seconds=0.001,
            )
    finally:
        relations.close()
