"""Tests for run-level budgets and structured research traces."""

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
