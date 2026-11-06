import json
import sqlite3

import pytest

from app.research.grounded_query import query_sql
from app.research.grounded_sql import MetricRelations, SQLCandidate, grounded_context
from app.research.metrics import MetricRegistry
from app.research.sources import SourceCatalog


class Model:
    def __init__(self, queries):
        self.queries = iter(queries)
        self.payloads = []

    def with_structured_output(self, schema, **kwargs):
        assert schema is SQLCandidate
        return self

    def bind(self, **kwargs):
        return self

    async def ainvoke(self, messages):
        self.payloads.append(json.loads(messages[-1]["content"]))
        return {"parsed": SQLCandidate(sql=next(self.queries)), "raw": None}


def fixture(tmp_path):
    db = tmp_path / "db.sqlite"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            "CREATE TABLE observations(id INTEGER PRIMARY KEY,name TEXT,region TEXT,score REAL); INSERT INTO observations VALUES(1,'Alpha Site','N',1),(2,'Beta Site','N',2),(3,'Excluded Site','N',0),(4,'Other Site','S',0),(5,'Beta Site','N',2),(6,'Gamma Site','N',3);"
        )
    catalog = SourceCatalog(sqlite_path=db, allowed_sources=("sql",))
    _, values, relations, payload = grounded_context(
        catalog,
        "Return one N name, excluding Excluded Site; minimize score with id as tie breaker. Remove spaces.",
        complete_definitions=True,
    )
    return values.values, relations, payload


@pytest.mark.asyncio
async def test_shared_sql_path_executes_projection_filters_ties_and_keeps_subtask_scope(tmp_path):
    values, relations, payload = fixture(tmp_path)
    query = "SELECT REPLACE(name,' ','') AS answer FROM r1 WHERE region='N' AND name<>'Excluded Site' AND score>=2 ORDER BY score ASC,id ASC LIMIT 1"
    model = Model([query])
    try:
        result = await query_sql(payload, relations, values, tmp_path / "run", model=model)
        actual = json.loads((tmp_path / "run/final-result.json").read_text())
        assert actual == {"columns": ["answer"], "rows": [["BetaSite"]]}
        assert result["status"] == "executed" and result["scope"] == "sql_subtask_only"
        assert len(model.payloads) == 1 and model.payloads[0] == payload
        assert "sql_result_match" not in result and "answerability" not in result
        with pytest.raises(FileExistsError):
            await query_sql(payload, relations, values, tmp_path / "run", model=model)
    finally:
        relations.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("first", ["SELECT absent FROM r1", "SELECT name FROM r1 WHERE score<0"])
async def test_only_actual_empty_or_engine_feedback_can_trigger_second_request(tmp_path, first):
    # A wrong nonempty answer receives no reference feedback or another retry.
    values, relations, payload = fixture(tmp_path)
    model = Model([first, "SELECT name FROM r1 WHERE region='S'"])
    try:
        summary = await query_sql(payload, relations, values, tmp_path / "run", model=model)
        assert len(model.payloads) == 2 and summary["status"] == "executed"
        feedback = model.payloads[1]["actual_engine_feedback"]
        assert feedback["prior_candidate"]["sql"] == first
        assert ("error" in feedback) if "absent" in first else feedback["empty_result"]
        assert "actual_engine_feedback" not in payload
    finally:
        relations.close()


@pytest.mark.asyncio
async def test_empty_sql_is_never_reported_as_answered(tmp_path):
    db = tmp_path / "empty.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE observations(name TEXT)")
    relations = MetricRelations(MetricRegistry(db, []), ["observations"])
    try:
        result = await query_sql(
            {"question": "Find a name"},
            relations,
            {},
            tmp_path / "run",
            model=Model(["SELECT name FROM r1"] * 2),
        )
        assert result["status"] == "empty" and result["row_count"] == 0
        assert len(result["attempts"]) == 2
    finally:
        relations.close()
