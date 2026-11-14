from threading import Barrier
from types import SimpleNamespace

import pytest

from app.agent import parallel_research
from app.agent.runtime import ResearchBudget, ResearchBudgetLimits, ResearchRunTrace
from app.search.models import SearchResponse, SearchResult


def make_trace():
    budget = ResearchBudget(ResearchBudgetLimits("deep_report", 300, 12, 12, 2, 12, 75))
    return ResearchRunTrace("run", "thread", "deep_report", budget)


@pytest.mark.asyncio
async def test_workers_overlap_and_one_failure_preserves_other_evidence(monkeypatch):
    trace = make_trace()
    barrier = Barrier(3)
    observed = []

    def search(request):
        observed.append(request)
        barrier.wait(timeout=3)
        url = "https://example.org/" + request.queries[0]
        return SearchResponse(
            request.queries, "duckduckgo", [SearchResult("Source", url, raw_content="Text")]
        )

    def create_agent(*, tools, **_):
        async def stream(payload, *_args, **_kwargs):
            query = payload["messages"][0]["content"]
            await tools[0].ainvoke({"queries": [query, "b", "c", "d", "extra"]})
            if query == "two":
                raise RuntimeError("isolated failure")
            yield {"model": {"messages": [SimpleNamespace(content=query, tool_calls=[])]}}

        return SimpleNamespace(astream=stream)

    monkeypatch.setattr(parallel_research, "create_agent", create_agent)
    monkeypatch.setattr(
        parallel_research, "get_search_service", lambda: SimpleNamespace(search=search)
    )
    answer = await parallel_research.research(
        "task", ["one", "two", "three"], None, trace, 5, "phase"
    )
    assert answer == "one\n\nthree"
    assert len(observed) == trace.subagent_calls == len(trace.web_evidence_ids) == 3
    assert trace.budget.search_queries_used == 12 and trace.budget.fetched_pages_used == 3
    assert all(r.fetch_full_page and r.max_fetched_pages == 4 for r in observed)
    assert trace.parallel_research_errors == {"RuntimeError": 1}
    assert trace.degraded


def test_delivery_removes_unknown_ids_without_discarding_structure():
    trace = make_trace()
    trace.claim_eligible_evidence_ids.append("ev1_web_known")
    answer, result = parallel_research.deliver_report(
        "# Heading\n\n- Known statement [ev1_web_known]\n- Other statement [ev1_web_unknown]",
        trace,
    )
    assert "# Heading" in answer and "- Other statement" in answer
    assert "[ev1_web_unknown]" not in answer
    assert result.cited_evidence_ids == ("ev1_web_known",)
    assert trace.removed_report_citations == 1
    assert trace.degraded and not trace.report_citation_withheld
