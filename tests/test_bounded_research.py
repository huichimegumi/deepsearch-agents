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


def test_unknown_value_is_a_refusal_not_a_numeric_fact():
    from app.research.report import ReportFact

    with pytest.raises(ValueError, match="nonnumeric_report_fact"):
        ReportFact(metric="limit", value="not specified", evidence_id="source", path=[])


@pytest.mark.asyncio
async def test_uncited_delivery_preserves_candidate_and_hides_internal_diagnostics(tmp_path):
    class Uncited(Model):
        async def ainvoke(self, messages):
            if self.schema is Plan:
                parsed = Plan(steps=[])
            else:
                parsed = ResearchReport(
                    title="Unsupported answer",
                    answerability="insufficient_evidence",
                    claims=[{"text": "No deployment limit is available.", "evidence_ids": []}],
                    facts=[],
                )
            return {"parsed": parsed, "raw": SimpleNamespace(response_metadata={})}

    result = await execute(
        "Find deployment limit",
        SourceCatalog(documents=[], allowed_sources=("local_document",)),
        tmp_path,
        workflow="simple",
        model=Uncited(),
    )
    assert result["status"] == "delivery_invalid"
    assert "uncited_claim" in result["warnings"]
    rejected = json.loads((tmp_path / "rejected_candidate.json").read_text())
    assert rejected["report"]["title"] == "Unsupported answer"
    assert result["report"]["title"] != rejected["report"]["title"]
    assert "uncited_claim" not in result["answer"]


def test_gap_diagnostic_length_is_not_a_delivery_failure():
    assert len(Gap(reason="diagnostic " * 100, step=None).reason) > 400


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_error", [False, True])
async def test_scoped_refusal_does_not_invent_citations_or_hide_tool_failure(tmp_path, tool_error):
    class Refusal(Model):
        async def ainvoke(self, messages):
            if self.schema is Plan:
                parsed = Plan(steps=[{"source": "local_document", "query": "deployment limit"}])
            elif self.schema is Gap:
                parsed = Gap(reason="Missing deployment data. " * 30, step=None)
            else:
                parsed = ResearchReport(
                    title="Insufficient deployment evidence",
                    answerability="insufficient_evidence",
                    claims=[],
                    facts=[],
                    limitations=["The searched documents did not establish a deployment limit."],
                )
            return {"parsed": parsed, "raw": SimpleNamespace(response_metadata={})}

    catalog = SourceCatalog(documents=[], allowed_sources=("local_document",))
    if tool_error:

        def fail(*args):
            raise OSError("source unavailable")

        catalog.collect = fail
    result = await execute("Find deployment limit", catalog, tmp_path, model=Refusal())
    assert result["status"] == ("source_error" if tool_error else "completed")
    assert result["report"]["claims"] == result["report"]["facts"] == []
    assert result["evidence_assessment"]["failed_lookups"] == int(tool_error)
    assert result["evidence_assessment"]["searched_sources"] == ["local_document"]


@pytest.mark.asyncio
async def test_web_entity_is_bound_before_dependent_sql_execution(tmp_path):
    from app.research.bounded import ResolvedQuery

    database = tmp_path / "data.sqlite"
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE items (name TEXT)")
        conn.execute("INSERT INTO items VALUES ('Ada')")

    class WebFirst(Model):
        async def ainvoke(self, messages):
            if self.schema is Plan:
                parsed = Plan(
                    steps=[
                        {"source": "web", "query": "selected item"},
                        {
                            "source": "sql",
                            "query": "Count items matching the entity in the Web source",
                            "depends_on": ["s0"],
                        },
                    ]
                )
            elif self.schema is ResolvedQuery:
                evidence = json.loads(messages[-1]["content"])["evidence"][0]
                parsed = ResolvedQuery(
                    query="SELECT COUNT(*) AS item_count FROM items WHERE name = 'Ada'",
                    bindings=[{"value": "Ada", "evidence_id": evidence["evidence_id"]}],
                )
            elif self.schema is ResearchReport:
                data = json.loads(messages[-1]["content"])
                record = next(r for r in data["evidence"] if r["source"] == "sql")
                parsed = ResearchReport(
                    title="Matching count",
                    answerability="answered",
                    claims=[],
                    facts=[
                        {
                            "metric": "item_count",
                            "value": "1",
                            "evidence_id": record["evidence_id"],
                            "path": ["item_count"],
                        }
                    ],
                )
            else:
                parsed = Gap(reason="adequate")
            return {"parsed": parsed, "raw": SimpleNamespace(response_metadata={})}

    result = await execute(
        "Count matching items",
        SourceCatalog(
            sqlite_path=database,
            allowed_sources=("web", "sql"),
            web_pages=[
                {
                    "title": "Selected item",
                    "locator": "fixture:selected",
                    "text": "The selected item is Ada.",
                }
            ],
        ),
        tmp_path / "run",
        model=WebFirst(),
    )
    assert result["status"] == "completed"
    assert result["operations"][1]["depends_on"] == ["s0"]
    assert result["operations"][1]["bindings"][0]["value"] == "Ada"
    assert result["report"]["facts"][0]["value"] == "1"


@pytest.mark.asyncio
async def test_one_writer_format_retry_keeps_original_candidate(tmp_path):
    class MalformedOnce(Model):
        writer_calls = 0

        async def ainvoke(self, messages):
            if self.schema is Plan:
                parsed = Plan(steps=[])
            elif self.schema is ResearchReport:
                self.writer_calls += 1
                if self.writer_calls == 1:
                    return {
                        "parsed": None,
                        "parsing_error": "malformed schema",
                        "raw": SimpleNamespace(
                            tool_calls=[{"malformed": True}],
                            content="candidate",
                            response_metadata={},
                            usage_metadata=None,
                        ),
                    }
                parsed = ResearchReport(
                    title="Scoped refusal",
                    answerability="insufficient_evidence",
                    claims=[],
                    facts=[],
                    limitations=["No supplied documents establish this value."],
                )
            else:
                parsed = Gap(reason="missing evidence")
            return {"parsed": parsed, "raw": SimpleNamespace(response_metadata={})}

    model = MalformedOnce()
    result = await execute(
        "Find deployment limit",
        SourceCatalog(documents=[], allowed_sources=("local_document",)),
        tmp_path,
        model=model,
    )
    assert model.writer_calls == 2
    assert result["status"] == "completed"
    assert (
        json.loads((tmp_path / "writer_format_failure.json").read_text())["content"] == "candidate"
    )
    assert len(result["model_responses"]) == 4
    assert not result["operations"]
