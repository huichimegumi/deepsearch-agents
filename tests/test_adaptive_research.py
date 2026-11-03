import json
import sqlite3
from types import SimpleNamespace

import pytest

from app.research.actions import Action, Decision, collect, sql_query
from app.research.bounded import execute
from app.research.evidence_store import EvidenceStore
from app.research.report import ResearchReport
from app.research.sources import SourceCatalog


def database(tmp_path):
    path = tmp_path / "data.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE items (name TEXT)")
        conn.execute("INSERT INTO items VALUES (?)", ("O'Reilly update",))
    return path


def test_parameter_values_are_data_and_empty_results_are_real_evidence(tmp_path):
    db = database(tmp_path)
    records, _ = sql_query(
        db, "SELECT COUNT(*) AS n FROM items WHERE name=:name", {"name": "O'Reilly update"}
    )
    assert records[0]["content"]["n"] == 1
    assert records[0]["metadata"]["parameters"]["name"] == "O'Reilly update"
    empty, _ = sql_query(db, "SELECT name FROM items WHERE name=:name", {"name": "missing"})
    assert empty[0]["content"]["row_count"] == 0
    with pytest.raises(sqlite3.Error):
        sql_query(db, "DELETE FROM items", {})
    with pytest.raises(ValueError, match="parameter_names"):
        sql_query(db, "SELECT :missing", {})


@pytest.mark.asyncio
async def test_adaptive_observes_web_then_uses_typed_sql_binding(tmp_path):
    db = database(tmp_path)

    class Model:
        decisions = 0

        def with_structured_output(self, schema, **kwargs):
            self.schema = schema
            return self

        def bind(self, **kwargs):
            return self

        async def ainvoke(self, messages):
            data = json.loads(messages[-1]["content"])
            if self.schema is Decision:
                self.decisions += 1
                if self.decisions == 1:
                    parsed = Decision(
                        reason="Find entity", action=Action(source="web", query="selected item")
                    )
                elif self.decisions == 2:
                    record = next(r for r in data["evidence"] if r["source"] == "web")
                    parsed = Decision(
                        reason="Count actual entity",
                        action=Action(
                            source="sql",
                            query="SELECT COUNT(*) AS n FROM items WHERE name=:entity",
                            parameters=[
                                {
                                    "name": "entity",
                                    "value": "O'Reilly update",
                                    "evidence_id": record["evidence_id"],
                                }
                            ],
                        ),
                    )
                else:
                    parsed = Decision(reason="Evidence sufficient")
            else:
                record = next(r for r in data["evidence"] if r["source"] == "sql")
                parsed = ResearchReport(
                    title="Count",
                    answerability="answered",
                    claims=[
                        {"text": "One matching item.", "evidence_ids": [record["evidence_id"]]}
                    ],
                    facts=[
                        {
                            "metric": "n",
                            "value": "1",
                            "evidence_id": record["evidence_id"],
                            "path": ["n"],
                        }
                    ],
                )
            return {"parsed": parsed, "raw": SimpleNamespace(response_metadata={})}

    catalog = SourceCatalog(
        sqlite_path=db,
        allowed_sources=("sql", "web"),
        web_pages=[
            {
                "title": "Selected item",
                "locator": "fixture:selected",
                "text": "The selected item is O'Reilly update.",
            }
        ],
    )
    result = await execute(
        "Count the matching item", catalog, tmp_path / "run", workflow="adaptive", model=Model()
    )
    assert result["status"] == "completed"
    assert result["operations"][1]["depends_on"] == ["s0"]
    assert result["operations"][1]["query"].endswith("name=:entity")
    assert result["report"]["facts"][0]["value"] == "1"
    assert (
        result["operations"][1]["bindings"][0]["evidence_id"]
        == result["evidence"][0]["evidence_id"]
    )


def test_binding_cannot_cite_an_unretrieved_entity(tmp_path):
    db = database(tmp_path)
    store = EvidenceStore(tmp_path / "run")
    action = Action(
        source="sql",
        query="SELECT :entity",
        parameters=[{"name": "entity", "value": "invented", "evidence_id": "missing"}],
    )
    with pytest.raises(KeyError):
        collect(SourceCatalog(sqlite_path=db, allowed_sources=("sql",)), action, store)
