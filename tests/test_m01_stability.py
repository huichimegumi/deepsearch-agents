"""Regression tests for the M0.1 workflow stability boundaries."""

import asyncio
import json
import sqlite3
from types import SimpleNamespace

from app.agent import main_agent
from app.agent.research_workflow import RESEARCH_PHASES
from app.agent.runtime import (
    ResearchBudget,
    ResearchBudgetLimits,
    ResearchRunTrace,
    reset_research_runtime,
    set_research_runtime,
)
from app.api.context import reset_session_context, set_session_context
from app.config import AgentExecutionBudget
from app.research.evidence import web_results_to_evidence
from app.search.models import SearchResult


def make_runtime():
    budget = ResearchBudget(
        ResearchBudgetLimits(
            profile="test",
            total_seconds=100,
            max_search_queries=3,
            max_fetched_pages=2,
            max_research_rounds=2,
            max_llm_calls=8,
            writer_reserved_seconds=25,
        )
    )
    return budget, ResearchRunTrace("run", "thread", "test", budget)


async def test_structured_direct_phase_uses_exactly_one_model_call(monkeypatch):
    calls = 0

    class StructuredInvoker:
        async def ainvoke(self, messages):
            nonlocal calls
            calls += 1
            assert len(messages) == 2
            return {
                "raw": SimpleNamespace(usage_metadata={"input_tokens": 20, "output_tokens": 8}),
                "parsed": main_agent.ResearchBrief(
                    research_question="What should be researched?",
                    constraints=["Use current sources"],
                    assumptions=[],
                    source_plan=["Search official sources"],
                    subquestions=["What changed?"],
                ),
                "parsing_error": None,
            }

    class FakeModel:
        def with_structured_output(self, schema, include_raw=False):
            assert schema is main_agent.ResearchBrief
            assert include_raw is True
            return StructuredInvoker()

    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "report_research_phase", lambda *args, **kwargs: None)
    budget, trace = make_runtime()
    phase = RESEARCH_PHASES[0]

    result = await main_agent._run_direct_phase(
        model=FakeModel(),
        phase=phase,
        prompt="Build a brief",
        budget=AgentExecutionBudget(recursion_limit=1, timeout_seconds=5),
        budget_profile="test",
        research_budget=budget,
        run_trace=trace,
        schema=main_agent.ResearchBrief,
    )

    assert calls == 1
    assert result.startswith("# Research Brief")
    assert trace.llm_calls == 1
    assert trace.phases[0]["artifact_status"] == "usable"


async def test_research_phase_rejects_unconfigured_builtin_subagent(monkeypatch):
    continued_after_rejection = False

    class FakeAgent:
        async def astream(self, payload, config):
            nonlocal continued_after_rejection
            yield {
                "model": {
                    "messages": [
                        SimpleNamespace(
                            content="",
                            tool_calls=[
                                {
                                    "name": "task",
                                    "args": {
                                        "subagent_type": "general-purpose",
                                        "description": "bypass configured researchers",
                                    },
                                }
                            ],
                        )
                    ]
                }
            }
            continued_after_rejection = True

    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "report_research_phase", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "_emit", lambda *args, **kwargs: None)
    budget, trace = make_runtime()

    result = await main_agent._run_agent_phase(
        agent=FakeAgent(),
        phase=RESEARCH_PHASES[1],
        prompt="Research",
        config={},
        budget=AgentExecutionBudget(recursion_limit=2, timeout_seconds=5),
        budget_profile="test",
        research_budget=budget,
        run_trace=trace,
        allowed_subagent_names=frozenset({"network_search"}),
    )

    assert result is None
    assert continued_after_rejection is False
    assert trace.failure_reasons == ["subagent_not_allowed:general-purpose"]
    assert trace.subagent_calls == 0


async def test_research_phase_allows_configured_network_subagent(monkeypatch):
    continued_after_dispatch = False

    class FakeAgent:
        async def astream(self, payload, config):
            nonlocal continued_after_dispatch
            yield {
                "model": {
                    "messages": [
                        SimpleNamespace(
                            content="",
                            tool_calls=[
                                {
                                    "name": "task",
                                    "args": {
                                        "subagent_type": "network_search",
                                        "description": "fetch public evidence",
                                    },
                                }
                            ],
                        )
                    ]
                }
            }
            continued_after_dispatch = True
            yield {
                "model": {"messages": [SimpleNamespace(content="Research complete", tool_calls=[])]}
            }

    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "report_research_phase", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "report_assistant", lambda *args, **kwargs: None)
    budget, trace = make_runtime()

    result = await main_agent._run_agent_phase(
        agent=FakeAgent(),
        phase=RESEARCH_PHASES[1],
        prompt="Research",
        config={},
        budget=AgentExecutionBudget(recursion_limit=2, timeout_seconds=5),
        budget_profile="test",
        research_budget=budget,
        run_trace=trace,
        max_subagent_calls=1,
        allowed_subagent_names=main_agent._configured_research_subagent_names(),
    )

    assert result == "Research complete"
    assert continued_after_dispatch is True
    assert trace.failure_reasons == []
    assert trace.subagent_calls == 1
    assert trace.tool_calls_by_name == {"task": 1}


async def test_research_phase_recovers_from_provider_timeout(monkeypatch):
    class APITimeoutError(Exception):
        pass

    class FakeAgent:
        async def astream(self, payload, config):
            if False:
                yield None
            raise APITimeoutError("Request timed out")

    events = []
    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "report_research_phase", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        main_agent.monitor,
        "_emit",
        lambda event, message, data: events.append((event, message, data)),
    )
    budget, trace = make_runtime()

    result = await main_agent._run_agent_phase(
        agent=FakeAgent(),
        phase=RESEARCH_PHASES[1],
        prompt="Research",
        config={},
        budget=AgentExecutionBudget(recursion_limit=2, timeout_seconds=5),
        budget_profile="test",
        research_budget=budget,
        run_trace=trace,
    )

    assert result is None
    assert trace.upstream_timeout_recoveries == 1
    assert trace.failure_reasons == ["upstream_timeout"]
    assert trace.phases[0]["status"] == "budget_exceeded"
    assert trace.phases[0]["reason"] == "upstream_timeout"
    assert events[0][0] == "phase_budget_exceeded"
    assert "continuing with collected evidence" in events[0][1]


async def test_sql_correction_executes_one_query_without_search(tmp_path, monkeypatch):
    database_path = tmp_path / "correction.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE metrics (name TEXT, value INTEGER)")
        connection.execute("INSERT INTO metrics VALUES ('verified', 42)")

    class StructuredInvoker:
        async def ainvoke(self, messages):
            assert messages[0]["content"].startswith("You are a SQL correction planner")
            assert "Backend Evidence Ledger" in messages[-1]["content"]
            return {
                "raw": SimpleNamespace(usage_metadata={"input_tokens": 20, "output_tokens": 8}),
                "parsed": main_agent.SQLCorrectionProposal(query="SELECT name, value FROM metrics"),
                "parsing_error": None,
            }

    class FakeModel:
        def with_structured_output(self, schema, include_raw=False):
            assert schema is main_agent.SQLCorrectionProposal
            assert include_raw is True
            return StructuredInvoker()

    monkeypatch.setenv("EVIDENCE_SQLITE_PATH", str(database_path))
    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "report_research_phase", lambda *args, **kwargs: None)
    budget, trace = make_runtime()
    trace.record_sql_discovery("describe_schema")
    trace.record_evidence(
        (
            SimpleNamespace(
                evidence_id="ev1_sql_schema",
                source="sql",
                locator="sql://schema/metrics",
                content={"table_name": "metrics", "columns": ["name", "value"]},
                metadata={"evidence_kind": "database_schema"},
            ),
        )
    )
    tokens = set_research_runtime(budget, trace)
    try:
        success = await main_agent._run_sql_evidence_correction(
            model=FakeModel(),
            task_query="Return the verified metric.",
            research_brief="Read the metrics table.",
            budget=AgentExecutionBudget(recursion_limit=2, timeout_seconds=5),
            budget_profile="test",
            research_budget=budget,
            run_trace=trace,
        )
    finally:
        reset_research_runtime(tokens)

    assert success is True
    assert trace.has_analytical_sql_evidence is True
    assert trace.sql_query_attempts == 1
    assert trace.sql_correction_attempts == 1
    assert trace.sql_correction_successes == 1
    assert trace.tool_calls_by_name == {"collect_evidence": 1}
    assert budget.search_queries_used == 0
    assert budget.fetched_pages_used == 0
    assert budget.research_rounds_used == 0


async def test_sql_correction_prefetches_pinned_semantic_knowledge(tmp_path, monkeypatch):
    database_path = tmp_path / "semantic-correction.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE metrics (name TEXT, value INTEGER)")
        connection.execute("INSERT INTO metrics VALUES ('verified', 42)")
    knowledge_path = tmp_path / "semantic-knowledge.jsonl"
    knowledge_path.write_text(
        json.dumps(
            {
                "id": 1,
                "knowledge": "Verified Metric Score (VMS)",
                "description": "The approved derived score.",
                "definition": "VMS = value * 2",
                "type": "calculation_knowledge",
            }
        ),
        encoding="utf-8",
    )
    calls = []

    class StructuredInvoker:
        async def ainvoke(self, messages):
            calls.append(messages)
            return {
                "raw": SimpleNamespace(usage_metadata={}),
                "parsed": main_agent.SQLCorrectionProposal(
                    query="SELECT name, value * 2 AS vms FROM metrics"
                ),
                "parsing_error": None,
            }

    class FakeModel:
        def with_structured_output(self, schema, include_raw=False):
            return StructuredInvoker()

    monkeypatch.setenv("EVIDENCE_SQLITE_PATH", str(database_path))
    monkeypatch.setenv("EVIDENCE_SQLITE_KNOWLEDGE_PATH", str(knowledge_path))
    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "report_research_phase", lambda *args, **kwargs: None)
    budget, trace = make_runtime()
    trace.record_sql_discovery("describe_schema")
    tokens = set_research_runtime(budget, trace)
    try:
        success = await main_agent._run_sql_evidence_correction(
            model=FakeModel(),
            task_query="Calculate the Verified Metric Score (VMS).",
            research_brief="Use the approved database formula.",
            budget=AgentExecutionBudget(recursion_limit=2, timeout_seconds=5),
            budget_profile="test",
            research_budget=budget,
            run_trace=trace,
        )
    finally:
        reset_research_runtime(tokens)

    assert success is True
    assert "Verified Metric Score (VMS)" in calls[0][-1]["content"]
    assert "VMS = value * 2" in calls[0][-1]["content"]
    assert "compiled_sql_expression" in calls[0][-1]["content"]
    assert '\\"metrics\\".\\"value\\"' in calls[0][-1]["content"]
    assert trace.sql_semantic_discovery_calls == 1
    assert trace.sql_evidence_by_kind["database_semantics"] == 1
    assert trace.sql_evidence_by_kind["database_query_validation"] == 1
    assert trace.tool_calls_by_name == {"collect_evidence": 3}
    assert budget.search_queries_used == 0
    assert budget.fetched_pages_used == 0
    assert budget.research_rounds_used == 0


async def test_multiclue_sql_correction_requires_web_ids_and_unique_database_value(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "entity-correction.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE metrics (name TEXT, value INTEGER)")
        connection.execute("INSERT INTO metrics VALUES ('Thomasville', 42)")
    knowledge_path = tmp_path / "entity-knowledge.jsonl"
    knowledge_path.write_text(
        json.dumps(
            {
                "id": 1,
                "knowledge": "Verified Metric Score (VMS)",
                "definition": "VMS = value * 2",
            }
        ),
        encoding="utf-8",
    )
    calls = []

    class StructuredInvoker:
        def __init__(self, schema):
            self.schema = schema

        async def ainvoke(self, messages):
            calls.append((self.schema, messages))
            if self.schema is main_agent.EntityResolutionProposal:
                parsed = main_agent.EntityResolutionProposal(
                    resolved_entity="Thomasville",
                    all_clues_supported=True,
                    clues=[
                        main_agent.EntityClueAssessment(
                            clue="clue one",
                            candidate="Thomasville",
                            evidence_ids=[web_record.evidence_id],
                            supported=True,
                        ),
                        main_agent.EntityClueAssessment(
                            clue="clue two",
                            candidate="Thomasville",
                            evidence_ids=[web_record.evidence_id],
                            supported=True,
                        ),
                    ],
                    table_name="metrics",
                    column_name="name",
                )
            else:
                assert self.schema is main_agent.SQLCorrectionProposal
                parsed = main_agent.SQLCorrectionProposal(
                    query=("SELECT name, value * 2 AS vms FROM metrics WHERE name = 'Thomasville'")
                )
            return {
                "raw": SimpleNamespace(usage_metadata={}),
                "parsed": parsed,
                "parsing_error": None,
            }

    class FakeModel:
        def with_structured_output(self, schema, include_raw=False):
            assert include_raw is True
            return StructuredInvoker(schema)

    monkeypatch.setenv("EVIDENCE_SQLITE_PATH", str(database_path))
    monkeypatch.setenv("EVIDENCE_SQLITE_KNOWLEDGE_PATH", str(knowledge_path))
    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "report_research_phase", lambda *args, **kwargs: None)
    budget, trace = make_runtime()
    web_record = web_results_to_evidence(
        [
            SearchResult(
                title="Entity clues",
                url="https://example.test/entity",
                raw_content="Both clue one and clue two identify Thomasville.",
            )
        ]
    )[0]
    trace.record_evidence((web_record,))
    tokens = set_research_runtime(budget, trace)
    try:
        success = await main_agent._run_sql_evidence_correction(
            model=FakeModel(),
            task_query="Use both clues to identify the place and calculate VMS.",
            research_brief="Resolve the clues before querying the database.",
            budget=AgentExecutionBudget(recursion_limit=2, timeout_seconds=5),
            budget_profile="test",
            research_budget=budget,
            run_trace=trace,
        )
    finally:
        reset_research_runtime(tokens)

    assert success is True
    assert [schema for schema, _messages in calls] == [
        main_agent.EntityResolutionProposal,
        main_agent.SQLCorrectionProposal,
    ]
    assert trace.sql_entity_resolution_attempts == 1
    assert trace.sql_entity_resolution_successes == 1
    assert trace.sql_entity_value_match_successes == 1
    assert trace.sql_evidence_by_kind["database_value_match"] == 1
    assert trace.sql_query_attempts == 1
    assert trace.sql_correction_successes == 1
    assert trace.tool_calls_by_name == {"collect_evidence": 4}


async def test_multiclue_entity_resolution_rejects_unknown_web_evidence_id():
    class StructuredInvoker:
        async def ainvoke(self, messages):
            return {
                "raw": SimpleNamespace(usage_metadata={}),
                "parsed": main_agent.EntityResolutionProposal(
                    resolved_entity="Thomasville",
                    all_clues_supported=True,
                    clues=[
                        main_agent.EntityClueAssessment(
                            clue="clue one",
                            candidate="Thomasville",
                            evidence_ids=["ev1_web_unknown"],
                            supported=True,
                        ),
                        main_agent.EntityClueAssessment(
                            clue="clue two",
                            candidate="Thomasville",
                            evidence_ids=[web_record.evidence_id],
                            supported=True,
                        ),
                    ],
                    table_name="metrics",
                    column_name="name",
                ),
                "parsing_error": None,
            }

    class FakeModel:
        def with_structured_output(self, schema, include_raw=False):
            assert schema is main_agent.EntityResolutionProposal
            assert include_raw is True
            return StructuredInvoker()

    budget, trace = make_runtime()
    web_record = web_results_to_evidence(
        [
            SearchResult(
                title="Entity clues",
                url="https://example.test/entity",
                raw_content="The fetched page identifies Thomasville.",
            )
        ]
    )[0]
    trace.record_evidence(
        (
            web_record,
            SimpleNamespace(
                evidence_id="ev1_sql_semantics",
                source="sql",
                locator="sql://semantics/vms",
                content={"relevant_table_columns": {"metrics": ["name", "value"]}},
                metadata={"evidence_kind": "database_semantics"},
            ),
        )
    )

    success = await main_agent._ground_multiclue_entity(
        model=FakeModel(),
        task_query="Use both clues to identify the place.",
        phase_key="sql_evidence_correction",
        phase_deadline=asyncio.get_running_loop().time() + 5,
        research_budget=budget,
        run_trace=trace,
    )

    assert success is False
    assert trace.sql_entity_resolution_attempts == 1
    assert trace.sql_entity_resolution_successes == 0
    assert trace.sql_entity_value_match_successes == 0
    assert trace.tool_calls_by_name == {}
    assert "sql_entity_resolution_web_evidence_unknown" in trace.failure_reasons


def test_entity_resolution_rejection_reasons_do_not_expose_candidate_content():
    proposal = main_agent.EntityResolutionProposal(
        resolved_entity="Thomasville",
        all_clues_supported=True,
        clues=[
            main_agent.EntityClueAssessment(
                clue="first",
                candidate="Thomasville",
                evidence_ids=["ev1_web_known"],
                supported=True,
            ),
            main_agent.EntityClueAssessment(
                clue="second",
                candidate="Different Place",
                evidence_ids=["ev1_web_known"],
                supported=True,
            ),
        ],
        table_name="metrics",
        column_name="name",
    )

    reason = main_agent._entity_resolution_rejection_reason(
        proposal,
        parsing_error=None,
        web_evidence_ids=frozenset({"ev1_web_known"}),
        semantic_catalog={"metrics": ("name",)},
    )

    assert reason == "candidate_conflict"
    assert "Thomasville" not in reason
    assert "Different Place" not in reason


async def test_sql_correction_preflight_repairs_unknown_metric_without_sql_attempt(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "semantic-preflight.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE metrics (name TEXT, value INTEGER)")
        connection.execute("INSERT INTO metrics VALUES ('verified', 42)")
    knowledge_path = tmp_path / "semantic-preflight.jsonl"
    knowledge_path.write_text(
        json.dumps(
            {
                "id": 1,
                "knowledge": "Verified Metric Score (VMS)",
                "definition": "VMS = value * 2",
            }
        ),
        encoding="utf-8",
    )
    proposals = iter(
        (
            "SELECT invented_metric FROM metrics",
            "SELECT name, value * 2 AS verified_score FROM metrics",
        )
    )
    calls = []

    class StructuredInvoker:
        async def ainvoke(self, messages):
            calls.append(messages)
            return {
                "raw": SimpleNamespace(usage_metadata={}),
                "parsed": main_agent.SQLCorrectionProposal(query=next(proposals)),
                "parsing_error": None,
            }

    class FakeModel:
        def with_structured_output(self, schema, include_raw=False):
            return StructuredInvoker()

    monkeypatch.setenv("EVIDENCE_SQLITE_PATH", str(database_path))
    monkeypatch.setenv("EVIDENCE_SQLITE_KNOWLEDGE_PATH", str(knowledge_path))
    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "report_research_phase", lambda *args, **kwargs: None)
    budget, trace = make_runtime()
    tokens = set_research_runtime(budget, trace)
    try:
        success = await main_agent._run_sql_evidence_correction(
            model=FakeModel(),
            task_query="Calculate the Verified Metric Score (VMS).",
            research_brief="Use the executable semantic formula.",
            budget=AgentExecutionBudget(recursion_limit=2, timeout_seconds=5),
            budget_profile="test",
            research_budget=budget,
            run_trace=trace,
        )
    finally:
        reset_research_runtime(tokens)

    assert success is True
    assert len(calls) == 2
    assert "failed the backend's read-only SQLite preflight" in calls[1][0]["content"]
    assert "no such column: invented_metric" in calls[1][1]["content"]
    assert trace.sql_query_attempts == 1
    assert trace.sql_query_failures == 0
    assert trace.sql_correction_repair_attempts == 1
    assert trace.sql_correction_repair_successes == 1
    assert trace.sql_evidence_by_kind["database_query_validation"] == 1
    assert trace.tool_calls_by_name == {"collect_evidence": 4}


async def test_supervisor_prefetch_exposes_pinned_formula_without_web_budget(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "supervisor-semantic.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE metrics (value INTEGER)")
    knowledge_path = tmp_path / "supervisor-semantic.jsonl"
    knowledge_path.write_text(
        json.dumps(
            {
                "id": 4,
                "knowledge": "Verified Metric Score (VMS)",
                "description": "Approved formula.",
                "definition": "VMS = value * 2",
                "type": "calculation_knowledge",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EVIDENCE_SQLITE_PATH", str(database_path))
    monkeypatch.setenv("EVIDENCE_SQLITE_KNOWLEDGE_PATH", str(knowledge_path))
    budget, trace = make_runtime()
    tokens = set_research_runtime(budget, trace)
    try:
        context = await main_agent._prefetch_sql_semantic_context(
            task_query="Calculate Verified Metric Score (VMS).",
            run_trace=trace,
            timeout_seconds=5,
        )
    finally:
        reset_research_runtime(tokens)

    assert "Verified Metric Score (VMS)" in context
    assert "VMS = value * 2" in context
    assert trace.sql_semantic_discovery_calls == 1
    assert trace.claim_eligible_evidence_ids == []
    assert trace.tool_calls_by_name == {"collect_evidence": 1}
    assert budget.search_queries_used == 0
    assert budget.fetched_pages_used == 0
    assert budget.research_rounds_used == 0


async def test_sql_correction_repairs_one_database_error_within_same_budget(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "correction-repair.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE metrics (name TEXT, value INTEGER)")
        connection.execute("INSERT INTO metrics VALUES ('verified', 42)")

    proposals = iter(
        (
            "SELECT invented_metric FROM metrics",
            "SELECT name, value * 2 AS derived_value FROM metrics",
        )
    )
    calls = []

    class StructuredInvoker:
        async def ainvoke(self, messages):
            calls.append(messages)
            return {
                "raw": SimpleNamespace(usage_metadata={"input_tokens": 20, "output_tokens": 8}),
                "parsed": main_agent.SQLCorrectionProposal(query=next(proposals)),
                "parsing_error": None,
            }

    class FakeModel:
        def with_structured_output(self, schema, include_raw=False):
            return StructuredInvoker()

    monkeypatch.setenv("EVIDENCE_SQLITE_PATH", str(database_path))
    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "report_research_phase", lambda *args, **kwargs: None)
    budget, trace = make_runtime()
    trace.record_evidence(
        (
            SimpleNamespace(
                evidence_id="ev1_sql_schema",
                source="sql",
                locator="sql://schema/metrics",
                content={"table_name": "metrics", "columns": ["name", "value"]},
                metadata={"evidence_kind": "database_schema"},
            ),
        )
    )
    tokens = set_research_runtime(budget, trace)
    try:
        success = await main_agent._run_sql_evidence_correction(
            model=FakeModel(),
            task_query="Return a derived metric.",
            research_brief="Use the metrics table.",
            budget=AgentExecutionBudget(recursion_limit=2, timeout_seconds=5),
            budget_profile="test",
            research_budget=budget,
            run_trace=trace,
        )
    finally:
        reset_research_runtime(tokens)

    assert success is True
    assert len(calls) == 2
    assert "previous SQL proposal was rejected" in calls[1][0]["content"]
    assert "invented_metric" in calls[1][1]["content"]
    assert trace.sql_query_attempts == 2
    assert trace.sql_query_failures == 1
    assert trace.sql_correction_attempts == 1
    assert trace.sql_correction_successes == 1
    assert trace.sql_correction_repair_attempts == 1
    assert trace.sql_correction_repair_successes == 1
    assert trace.tool_calls_by_name == {"collect_evidence": 2}
    payload = trace.finalize(status="completed", final_result="verified")
    assert payload["metrics"]["sql_correction_repair_attempts"] == 1
    assert payload["metrics"]["sql_correction_repair_successes"] == 1
    assert budget.search_queries_used == 0
    assert budget.fetched_pages_used == 0
    assert budget.research_rounds_used == 0


async def test_sql_correction_repairs_one_empty_result_within_same_budget(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "correction-empty.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE metrics (name TEXT, value INTEGER)")
        connection.execute("INSERT INTO metrics VALUES ('verified', 42)")

    proposals = iter(
        (
            "SELECT name, value FROM metrics WHERE name = 'unsupported'",
            "SELECT name, value FROM metrics",
        )
    )
    calls = []

    class StructuredInvoker:
        async def ainvoke(self, messages):
            calls.append(messages)
            return {
                "raw": SimpleNamespace(usage_metadata={}),
                "parsed": main_agent.SQLCorrectionProposal(query=next(proposals)),
                "parsing_error": None,
            }

    class FakeModel:
        def with_structured_output(self, schema, include_raw=False):
            return StructuredInvoker()

    monkeypatch.setenv("EVIDENCE_SQLITE_PATH", str(database_path))
    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "report_research_phase", lambda *args, **kwargs: None)
    budget, trace = make_runtime()
    trace.record_sql_discovery("describe_schema")
    tokens = set_research_runtime(budget, trace)
    try:
        success = await main_agent._run_sql_evidence_correction(
            model=FakeModel(),
            task_query="Return metrics.",
            research_brief="Use the metrics table.",
            budget=AgentExecutionBudget(recursion_limit=2, timeout_seconds=5),
            budget_profile="test",
            research_budget=budget,
            run_trace=trace,
        )
    finally:
        reset_research_runtime(tokens)

    assert success is True
    assert len(calls) == 2
    assert "returned zero rows" in calls[1][0]["content"]
    assert "unsupported" in calls[1][1]["content"]
    assert trace.sql_query_attempts == 2
    assert trace.sql_query_successes == 2
    assert trace.sql_query_failures == 0
    assert trace.sql_correction_repair_attempts == 1
    assert trace.sql_correction_repair_successes == 1
    assert trace.sql_correction_empty_result_repair_attempts == 1
    assert trace.sql_correction_empty_result_repair_successes == 1
    assert trace.tool_calls_by_name == {"collect_evidence": 2}
    payload = trace.finalize(status="completed", final_result="verified")
    assert payload["metrics"]["sql_correction_empty_result_repair_attempts"] == 1
    assert payload["metrics"]["sql_correction_empty_result_repair_successes"] == 1
    assert budget.search_queries_used == 0
    assert budget.fetched_pages_used == 0
    assert budget.research_rounds_used == 0


async def test_sql_correction_stops_after_second_empty_result(tmp_path, monkeypatch):
    database_path = tmp_path / "correction-still-empty.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE metrics (name TEXT, value INTEGER)")

    proposals = iter(
        (
            "SELECT name, value FROM metrics WHERE name = 'first'",
            "SELECT name, value FROM metrics WHERE name = 'second'",
        )
    )
    calls = 0

    class StructuredInvoker:
        async def ainvoke(self, messages):
            nonlocal calls
            calls += 1
            return {
                "raw": SimpleNamespace(usage_metadata={}),
                "parsed": main_agent.SQLCorrectionProposal(query=next(proposals)),
                "parsing_error": None,
            }

    class FakeModel:
        def with_structured_output(self, schema, include_raw=False):
            return StructuredInvoker()

    monkeypatch.setenv("EVIDENCE_SQLITE_PATH", str(database_path))
    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "report_research_phase", lambda *args, **kwargs: None)
    budget, trace = make_runtime()
    trace.record_sql_discovery("describe_schema")
    tokens = set_research_runtime(budget, trace)
    try:
        success = await main_agent._run_sql_evidence_correction(
            model=FakeModel(),
            task_query="Return metrics.",
            research_brief="Use the metrics table.",
            budget=AgentExecutionBudget(recursion_limit=2, timeout_seconds=5),
            budget_profile="test",
            research_budget=budget,
            run_trace=trace,
        )
    finally:
        reset_research_runtime(tokens)

    assert success is False
    assert calls == 2
    assert trace.sql_query_attempts == 2
    assert trace.sql_correction_repair_attempts == 1
    assert trace.sql_correction_repair_successes == 0
    assert trace.sql_correction_empty_result_repair_attempts == 1
    assert trace.sql_correction_empty_result_repair_successes == 0
    assert "sql_correction_no_analytical_evidence" in trace.failure_reasons


async def test_sql_correction_rejects_duplicate_repair_proposal(monkeypatch):
    calls = 0

    class StructuredInvoker:
        async def ainvoke(self, messages):
            nonlocal calls
            calls += 1
            return {
                "raw": SimpleNamespace(usage_metadata={}),
                "parsed": main_agent.SQLCorrectionProposal(query="SELECT missing FROM metrics"),
                "parsing_error": None,
            }

    class FakeModel:
        def with_structured_output(self, schema, include_raw=False):
            return StructuredInvoker()

    class FakeEvidenceTool:
        name = "collect_evidence"

        async def ainvoke(self, args):
            return '{"status":"ERROR","records":[],"warnings":[]}'

    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "report_research_phase", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent, "collect_evidence", FakeEvidenceTool())
    budget, trace = make_runtime()
    trace.record_sql_discovery("describe_schema")

    success = await main_agent._run_sql_evidence_correction(
        model=FakeModel(),
        task_query="Return metrics.",
        research_brief="Use the metrics table.",
        budget=AgentExecutionBudget(recursion_limit=2, timeout_seconds=5),
        budget_profile="test",
        research_budget=budget,
        run_trace=trace,
    )

    assert success is False
    assert calls == 2
    assert trace.tool_calls_by_name == {"collect_evidence": 1}
    assert trace.sql_correction_repair_attempts == 1
    assert "sql_correction_duplicate_proposal" in trace.failure_reasons


async def test_sql_correction_maps_proposal_to_fixed_sql_tool_arguments(monkeypatch):
    invoked_args = None

    class StructuredInvoker:
        async def ainvoke(self, messages):
            return {
                "raw": SimpleNamespace(usage_metadata={}),
                "parsed": main_agent.SQLCorrectionProposal(query="SELECT 1 AS verified"),
                "parsing_error": None,
            }

    class FakeModel:
        def with_structured_output(self, schema, include_raw=False):
            return StructuredInvoker()

    class FakeEvidenceTool:
        name = "collect_evidence"

        async def ainvoke(self, args):
            nonlocal invoked_args
            invoked_args = args

    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "report_research_phase", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent, "collect_evidence", FakeEvidenceTool())
    budget, trace = make_runtime()
    trace.record_sql_discovery("describe_schema")

    success = await main_agent._run_sql_evidence_correction(
        model=FakeModel(),
        task_query="Research task",
        research_brief="Use SQL.",
        budget=AgentExecutionBudget(recursion_limit=2, timeout_seconds=5),
        budget_profile="test",
        research_budget=budget,
        run_trace=trace,
    )

    assert success is False
    assert invoked_args == {
        "source": "sql",
        "operation": "query",
        "query": "SELECT 1 AS verified",
    }
    assert trace.tool_calls_by_name == {"collect_evidence": 1}
    assert trace.sql_correction_attempts == 1
    assert "sql_correction_no_analytical_evidence" in trace.failure_reasons


def test_required_sql_output_uses_claim_linked_executed_query(monkeypatch):
    _budget, trace = make_runtime()
    supported = SimpleNamespace(evidence_id="ev1_sql_supported", source="sql")
    latest = SimpleNamespace(evidence_id="ev1_sql_latest", source="sql")
    trace.record_sql_query_evidence("SELECT supported_value FROM metrics", (supported,))
    trace.record_sql_query_evidence("SELECT unrelated_value FROM metrics", (latest,))
    trace.record_claim_validation(
        SimpleNamespace(
            accepted=(
                SimpleNamespace(
                    claim_id="clm1_supported",
                    kind="fact",
                    evidence_ids=("ev1_sql_supported",),
                ),
            ),
            rejected=(),
            unknown_evidence_ids=(),
        )
    )
    original_report = "Report\n\n```sql\nSELECT invented FROM nowhere\n```"

    assert main_agent._attach_required_executed_sql(original_report, trace) == original_report
    monkeypatch.setenv("INCLUDE_EXECUTED_SQL_IN_REPORT", "1")

    result = main_agent._attach_required_executed_sql(
        original_report,
        trace,
    )

    assert result.count("```sql") == 1
    assert "SELECT supported_value FROM metrics" in result
    assert "invented" not in result
    assert "unrelated_value" not in result
    assert trace.report_sql_query_attached is True
    payload = trace.finalize(status="completed", final_result=result)
    assert payload["metrics"]["report_sql_query_attached"] is True


def test_backend_persists_requested_markdown_and_records_tool(tmp_path, monkeypatch):
    monkeypatch.setattr(main_agent.monitor, "report_file_created", lambda *args, **kwargs: None)
    budget, trace = make_runtime()
    trace.start_phase("final_report", "Writer")
    token = set_session_context(str(tmp_path))
    try:
        artifacts = main_agent._persist_requested_artifacts(
            task_query="生成 Markdown 报告",
            report_markdown="# Verified report\n\nContent",
            run_trace=trace,
        )
    finally:
        reset_session_context(token)

    report_path = tmp_path / "report.md"
    assert artifacts == [str(report_path)]
    assert report_path.read_text(encoding="utf-8").startswith("# Verified report")
    assert trace.tool_calls_by_name == {"write_markdown_artifact": 1}
