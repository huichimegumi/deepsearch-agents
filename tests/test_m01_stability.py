"""Regression tests for the M0.1 workflow stability boundaries."""

from types import SimpleNamespace

from app.agent import main_agent
from app.agent.research_workflow import RESEARCH_PHASES
from app.agent.runtime import ResearchBudget, ResearchBudgetLimits, ResearchRunTrace
from app.api.context import reset_session_context, set_session_context
from app.config import AgentExecutionBudget


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
                "raw": SimpleNamespace(
                    usage_metadata={"input_tokens": 20, "output_tokens": 8}
                ),
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
        allowed_subagent_names=frozenset({"网络搜索助手"}),
    )

    assert result is None
    assert continued_after_rejection is False
    assert trace.failure_reasons == ["subagent_not_allowed:general-purpose"]
    assert trace.subagent_calls == 0


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
