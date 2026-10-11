"""Tests for run-level budgets and structured research traces."""

import json
from types import SimpleNamespace
from unittest.mock import patch

from app.agent.runtime import (
    ResearchBudget,
    ResearchBudgetLimits,
    ResearchRunTrace,
    reset_research_runtime,
    set_research_runtime,
)
from app.search.models import SearchResponse
from app.tools.tavily_tool import research_search


def make_budget() -> ResearchBudget:
    return ResearchBudget(
        ResearchBudgetLimits(
            profile="test",
            total_seconds=100,
            max_search_queries=3,
            max_fetched_pages=2,
            max_research_rounds=1,
            max_llm_calls=6,
            writer_reserved_seconds=25,
        )
    )


def test_phase_timeout_uses_run_allocation_and_writer_reserve():
    budget = make_budget()

    assert budget.phase_timeout("clarify_and_brief", 999) == 10
    assert budget.phase_timeout("supervisor_research", 999) == 50
    assert budget.phase_timeout("sql_evidence_correction", 999) == 15
    assert budget.phase_timeout("evidence_compression", 999) == 15
    assert budget.phase_timeout("final_report", 999) == 25


def test_multidimensional_budget_refuses_excess_work():
    budget = make_budget()

    assert budget.take_search_queries(2) == 2
    assert budget.take_search_queries(2) == 1
    assert budget.take_search_queries(1) == 0
    assert budget.take_fetched_pages(3) == 2
    assert budget.take_research_round() is True
    assert budget.take_research_round() is False


def test_llm_budget_preserves_compression_and_writer_calls():
    budget = make_budget()

    assert budget.take_llm_call("supervisor_research") is True
    assert budget.take_llm_call("supervisor_research") is True
    assert budget.take_llm_call("supervisor_research") is True
    assert budget.take_llm_call("supervisor_research") is True
    assert budget.take_llm_call("supervisor_research") is False
    assert budget.take_llm_call("evidence_compression") is True
    assert budget.take_llm_call("final_report") is True
    assert budget.take_llm_call("final_report") is False


def test_trace_records_phase_tokens_search_and_waste():
    budget = make_budget()
    trace = ResearchRunTrace("run-1", "thread-1", "test", budget)
    trace.start_phase("supervisor_research", "Research")
    trace.record_llm_call(
        "supervisor_research",
        SimpleNamespace(usage_metadata={"input_tokens": 10, "output_tokens": 4}),
    )
    trace.record_tool_call("supervisor_research", "research_search")
    trace.record_tool_call("supervisor_research", "research_search")
    trace.record_search(
        ["alpha"],
        [
            {
                "url": "https://example.test/a",
                "matched_queries": ["alpha"],
                "raw_content": "full page",
            }
        ],
    )
    trace.record_search(
        ["alpha", "empty"],
        [
            {
                "url": "https://example.test/a",
                "matched_queries": ["alpha"],
                "raw_content": "full page",
            }
        ],
    )
    trace.finish_phase("supervisor_research", "end")

    payload = trace.finalize(status="completed", final_result="no links")

    assert payload["metrics"]["llm_calls"] == 1
    assert payload["metrics"]["tool_calls_by_name"] == {"research_search": 2}
    assert payload["metrics"]["input_tokens"] == 10
    assert payload["metrics"]["fetched_pages"] == 1
    assert payload["waste"]["duplicate_queries"] == 1
    assert payload["waste"]["duplicate_sources"] == 1
    assert payload["waste"]["queries_with_zero_new_sources"] == 2
    assert payload["waste"]["fetched_but_unused_sources"] == 1


def test_degraded_phase_is_not_reported_as_normal_completion():
    budget = make_budget()
    trace = ResearchRunTrace("run-1", "thread-1", "test", budget)
    trace.start_phase("supervisor_research", "Research")
    trace.finish_phase("supervisor_research", "budget_exceeded", "timeout")

    payload = trace.finalize(status="completed", final_result="partial")

    assert payload["status"] == "degraded"
    assert payload["failure_reason"] == "timeout"
    assert payload["failure_reasons"] == ["timeout"]
    assert payload["phases"][0]["artifact_status"] == "missing"


def test_trace_records_unique_evidence_ids_by_source():
    trace = ResearchRunTrace("run-1", "thread-1", "test", make_budget())
    record = SimpleNamespace(evidence_id="ev1_sql_abc", source="sql")

    trace.record_evidence((record, record))
    payload = trace.finalize(status="completed", final_result="[ev1_sql_abc]")

    assert payload["metrics"]["evidence_records"] == 1
    assert payload["metrics"]["evidence_by_source"] == {"sql": 1}
    assert payload["metrics"]["claim_eligible_evidence_records"] == 1
    assert payload["metrics"]["sql_evidence_by_kind"] == {"query_result": 1}
    assert payload["waste"]["evidence_never_used_in_claims"] == 1


def test_trace_keeps_sql_discovery_evidence_out_of_claim_gate():
    trace = ResearchRunTrace("run-1", "thread-1", "test", make_budget())
    schema = SimpleNamespace(
        evidence_id="ev1_sql_schema",
        source="sql",
        metadata={"evidence_kind": "database_schema"},
    )
    sample = SimpleNamespace(
        evidence_id="ev1_sql_sample",
        source="sql",
        metadata={"evidence_kind": "database_sample"},
    )

    trace.record_evidence((schema, sample))
    payload = trace.finalize(status="completed", final_result="gap")

    assert trace.claim_eligible_evidence_ids == []
    assert trace.has_analytical_sql_evidence is False
    assert payload["metrics"]["sql_evidence_by_kind"] == {
        "database_schema": 1,
        "database_sample": 1,
    }
    assert payload["waste"]["evidence_never_used_in_claims"] == 0


def test_trace_allows_one_sql_correction_after_discovery():
    trace = ResearchRunTrace("run-1", "thread-1", "test", make_budget())

    assert trace.can_attempt_sql_correction is False
    trace.record_sql_discovery("describe_schema")
    trace.record_evidence(
        (
            SimpleNamespace(
                evidence_id="ev1_sql_schema",
                source="sql",
                metadata={"evidence_kind": "database_schema"},
            ),
        )
    )
    assert trace.can_attempt_sql_correction is True

    trace.record_sql_correction(success=False)
    payload = trace.finalize(status="completed", final_result="gap")

    assert payload["metrics"]["sql_correction_attempts"] == 1
    assert payload["metrics"]["sql_correction_successes"] == 0


def test_trace_renders_bounded_backend_ledger_without_serializing_content():
    trace = ResearchRunTrace("run-1", "thread-1", "test", make_budget())
    record = SimpleNamespace(
        evidence_id="ev1_sql_abc",
        source="sql",
        locator="sql://test/row",
        content={"secret": "internal fact"},
    )

    trace.record_evidence((record,))
    ledger = trace.render_evidence_ledger()
    payload = trace.finalize(status="completed", final_result="done")

    assert "[ev1_sql_abc]" in ledger
    assert "internal fact" in ledger
    assert "internal fact" not in json.dumps(payload)


def test_trace_records_validated_claim_usage_and_report_citations():
    trace = ResearchRunTrace("run-1", "thread-1", "test", make_budget())
    claim = SimpleNamespace(
        claim_id="clm1_abc",
        kind="fact",
        evidence_ids=("ev1_sql_abc",),
    )
    report = SimpleNamespace(
        accepted=(claim,),
        rejected=(SimpleNamespace(),),
        unknown_evidence_ids=("ev1_sql_unknown",),
    )
    citation_validation = SimpleNamespace(
        valid=True,
        cited_evidence_ids=("ev1_sql_abc",),
    )

    trace.record_evidence((SimpleNamespace(evidence_id="ev1_sql_abc", source="sql"),))
    trace.record_claim_validation(report)
    trace.record_report_citation_validation(citation_validation)
    payload = trace.finalize(status="completed", final_result="[ev1_sql_abc]")

    assert payload["metrics"]["validated_claims"] == 1
    assert payload["metrics"]["rejected_claims"] == 1
    assert payload["metrics"]["claims_by_kind"] == {"fact": 1}
    assert payload["metrics"]["claim_evidence_records"] == 1
    assert payload["metrics"]["unknown_claim_evidence_ids"] == 1
    assert payload["metrics"]["report_citation_valid"] is True
    assert payload["waste"]["evidence_never_used_in_claims"] == 0


def test_trace_preserves_all_unique_failure_reasons():
    budget = make_budget()
    trace = ResearchRunTrace("run-1", "thread-1", "test", budget)
    trace.start_phase("clarify_and_brief", "Clarify")
    trace.finish_phase("clarify_and_brief", "budget_exceeded", "timeout")
    trace.start_phase("final_report", "Writer")
    trace.finish_phase("final_report", "error", "artifact_missing")

    payload = trace.finalize(
        status="completed", final_result="partial", failure_reason="llm_call_limit"
    )

    assert payload["failure_reason"] == "timeout"
    assert payload["failure_reasons"] == ["timeout", "artifact_missing", "llm_call_limit"]


def test_trace_bounds_sql_repair_and_keeps_query_text_private():
    trace = ResearchRunTrace("run-1", "thread-1", "test", make_budget())
    original = "SELECT secret_name FROM observatories"
    repaired = "SELECT observatory_name FROM observatories"

    admitted, _first = trace.admit_sql_query(original)
    assert admitted is True
    trace.record_sql_query_result(
        original,
        status="ERROR",
        warnings=("OperationalError: no such column: secret_name",),
    )
    admitted, duplicate = trace.admit_sql_query(original)
    assert admitted is False
    assert duplicate["reason"] == "duplicate_failed_query"
    admitted, _second = trace.admit_sql_query(repaired)
    assert admitted is True
    trace.record_sql_query_result(
        repaired,
        status="ERROR",
        warnings=("OperationalError: no such column: observatory_name",),
    )
    admitted, limited = trace.admit_sql_query("SELECT name FROM observatories")
    assert admitted is False
    assert limited["reason"] == "consecutive_failure_limit"

    payload = trace.finalize(status="completed", final_result="gap")
    serialized = json.dumps(payload)
    assert payload["schema_version"] == 5
    assert payload["metrics"]["sql_query_attempts"] == 2
    assert payload["metrics"]["sql_query_failures"] == 2
    assert payload["metrics"]["sql_query_blocked"] == 2
    assert payload["metrics"]["sql_error_categories"] == {"unknown_column": 2}
    assert "secret_name" not in serialized
    assert "observatory_name" not in serialized


def test_successful_sql_repair_resets_consecutive_failure_limit():
    trace = ResearchRunTrace("run-1", "thread-1", "test", make_budget())
    admitted, _ = trace.admit_sql_query("SELECT missing FROM metrics")
    assert admitted is True
    trace.record_sql_query_result(
        "SELECT missing FROM metrics",
        status="ERROR",
        warnings=("no such column: missing",),
    )
    admitted, _ = trace.admit_sql_query("SELECT value FROM metrics")
    assert admitted is True
    trace.record_sql_query_result("SELECT value FROM metrics", status="OK")
    admitted, _ = trace.admit_sql_query("SELECT another_missing FROM metrics")

    assert admitted is True


def test_search_tool_enforces_query_budget_and_records_zero_result_waste():
    budget = make_budget()
    trace = ResearchRunTrace("run-1", "thread-1", "test", budget)
    service = SimpleNamespace(
        search=lambda request: SearchResponse(
            queries=request.queries,
            backend=request.backend,
            results=[],
        )
    )
    tokens = set_research_runtime(budget, trace)
    try:
        with patch("app.tools.tavily_tool.get_search_service", return_value=service):
            first = research_search.invoke({"queries": ["a", "b", "c", "d"]})
            second = research_search.invoke({"queries": ["e"]})
    finally:
        reset_research_runtime(tokens)

    assert first["queries"] == ["a", "b", "c"]
    assert second["results"] == []
    assert "搜索查询预算" in second["notices"][0]
    assert budget.search_queries_used == 3
    assert trace.queries_with_zero_new_sources == 3
