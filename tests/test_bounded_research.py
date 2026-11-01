import asyncio
import json
import sqlite3
from types import SimpleNamespace

import pytest

from app.research.bounded import Gap, Plan, execute
from app.research.report import ResearchReport
from app.research.request_budget import (
    EvaluationBudgetExceeded,
    RequestBudget,
    admit_request,
    usage,
)
from app.research.sources import SourceCatalog


class Model:
    def with_structured_output(self, schema, **kwargs):
        self.schema = schema
        return self

    def bind(self, **kwargs):
        return self

    async def ainvoke(self, messages):
        data = json.loads(messages[-1]["content"])
        if self.schema is Plan:
            parsed = Plan(
                steps=[
                    {
                        "id": "s0",
                        "source": "sql",
                        "query": "SELECT COUNT(*) AS item_count FROM items",
                    },
                    {"id": "s1", "source": "web", "query": "item {{s0.item_count}} policy"},
                ]
            )
        elif self.schema is Gap:
            parsed = Gap(reason="adequate", step=None)
        else:
            row = next(row for row in data["evidence"] if row["source"] == "sql")
            parsed = ResearchReport(
                title="Item count",
                answerability="answered",
                claims=[
                    {
                        "text": "The database contains two items.",
                        "evidence_ids": [row["evidence_id"]],
                    }
                ],
                facts=[
                    {
                        "metric": "item_count",
                        "value": "2",
                        "evidence_id": row["evidence_id"],
                        "path": ["item_count"],
                    }
                ],
            )
        return {
            "parsed": parsed,
            "raw": SimpleNamespace(
                response_metadata={"finish_reason": "stop"}, usage_metadata=None
            ),
        }


@pytest.mark.asyncio
async def test_real_sql_dependency_and_one_writer_are_shared(tmp_path):
    database = tmp_path / "data.sqlite"
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE items (name TEXT)")
        conn.executemany("INSERT INTO items VALUES (?)", [("first",), ("second",)])
    catalog = SourceCatalog(
        sqlite_path=database,
        web_pages=[
            {
                "title": "Item policy",
                "locator": "https://example.org/policy",
                "text": "Policy for item 2.",
            }
        ],
        allowed_sources=("sql", "web"),
    )
    result = await execute(
        "Count items as item_count and check policy.", catalog, tmp_path / "run", model=Model()
    )
    assert result["status"] == "completed"
    assert result["report"]["facts"][0]["value"] == "2"
    assert result["operations"][1]["query"] == "item 2 policy"
    assert {row["source"] for row in result["evidence"]} == {"sql", "web"}
    assert (tmp_path / "run/report.md").is_file()
    with pytest.raises(ValueError, match="source_not_allowed"):
        catalog.collect("local_document", "private corpus")
    with pytest.raises(Exception):
        catalog.collect("sql", "DELETE FROM items")


@pytest.mark.asyncio
async def test_request_budgets_are_task_local_and_reserve_final_request(tmp_path):
    async def run(name):
        budget = RequestBudget(
            tmp_path / name, max_requests=2, max_reserved_tokens=10000, final_reserved_tokens=1000
        )
        with budget.activate():
            payload = {"messages": [{"role": "user", "content": name}], "max_tokens": 100}
            admit_request(payload)
            await asyncio.sleep(0)
            with pytest.raises(EvaluationBudgetExceeded):
                admit_request(payload)
            budget.finalizing = True
            admit_request(payload)
        return usage(budget.path)

    left, right = await asyncio.gather(run("left"), run("right"))
    assert left["requests"] == right["requests"] == 2


@pytest.mark.asyncio
async def test_cancellation_never_publishes_completed_output(tmp_path):
    class Blocked(Model):
        async def ainvoke(self, messages):
            raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await execute(
            "test",
            SourceCatalog(documents=[], allowed_sources=("local_document",)),
            tmp_path,
            model=Blocked(),
        )
    assert not (tmp_path / "research_result.json").exists()
