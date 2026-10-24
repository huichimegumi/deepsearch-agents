import json
from types import SimpleNamespace

import pytest
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.agent import main_agent
from app.agent.research_workflow import RESEARCH_PHASES, build_phase_prompt
from app.agent.runtime import ResearchBudget, ResearchBudgetLimits, ResearchRunTrace
from app.config import AgentExecutionBudget
from app.tools import local_research_tool as local_tool
from evals.reports_acceptance import run as report_runner


def test_local_factory_has_only_narrow_tool_and_no_implicit_middleware(monkeypatch):
    seen = {}
    main_agent.get_indexed_local_research_agent.cache_clear()
    monkeypatch.setattr(main_agent, "get_model", lambda: "model")
    monkeypatch.setattr(main_agent, "get_short_term_checkpointer", lambda: "checkpoint")

    def construct(**kwargs):
        seen.update(kwargs)
        return object()

    monkeypatch.setattr(main_agent, "create_agent", construct)
    try:
        main_agent.get_indexed_local_research_agent()
        assert seen["tools"] == [local_tool.collect_local_evidence]
        assert "subagents" not in seen and "middleware" not in seen
        schema = local_tool.collect_local_evidence.args_schema.model_json_schema()["properties"]
        assert set(schema) == {"query", "knowledge_base"}
    finally:
        main_agent.get_indexed_local_research_agent.cache_clear()


async def test_source_is_fixed_even_when_untrusted_extra_fields_request_sql(monkeypatch):
    calls = []

    async def collect(args):
        calls.append(args)
        return "local result"

    monkeypatch.setattr(local_tool, "unified_evidence", SimpleNamespace(ainvoke=collect))
    result = await local_tool.collect_local_evidence.ainvoke(
        {"query": "question", "knowledge_base": "named", "source": "sql", "operation": "query"}
    )
    assert result == "local result"
    assert calls == [{"source": "local_document", "query": "question", "knowledge_base": "named"}]


@pytest.mark.parametrize("enabled", [False, True])
async def test_report_runner_forwards_experimental_opt_in(tmp_path, monkeypatch, enabled):
    seen = []

    async def execute(*args, **kwargs):
        seen.append(kwargs["indexed_local_research_enabled"])
        return None

    monkeypatch.setattr(report_runner, "ROOT", tmp_path)
    monkeypatch.setattr(report_runner, "run_deep_agent", execute)
    await report_runner.execute_case(
        {
            "id": "case",
            "question": "q",
            "answerable": False,
            "evidence_units": [],
            "answer_keypoints": [],
        },
        "prompt",
        "session",
        tmp_path / "case",
        10,
        indexed_local=enabled,
    )
    assert seen == [enabled]


class ScriptedModel(BaseChatModel):
    @property
    def _llm_type(self):
        return "test-local-research"

    def bind_tools(self, tools, **kwargs):
        assert [tool.name for tool in tools] == ["collect_evidence"]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if isinstance(messages[-1], ToolMessage):
            response = AIMessage(content="bounded local ledger")
        else:
            response = AIMessage(
                content="",
                tool_calls=[
                    {"id": "call", "name": "collect_evidence", "args": {"query": "question"}}
                ],
            )
        return ChatResult(generations=[ChatGeneration(message=response)])


async def test_real_create_agent_graph_runs_model_tool_model_without_deepagents(monkeypatch):
    calls = []

    async def collect(args):
        calls.append(args)
        return json.dumps({"status": "NO_EVIDENCE", "records": []})

    monkeypatch.setattr(local_tool, "unified_evidence", SimpleNamespace(ainvoke=collect))
    graph = create_agent(model=ScriptedModel(), tools=[local_tool.collect_local_evidence])
    events = [
        event
        async for event in graph.astream({"messages": [{"role": "user", "content": "question"}]})
    ]
    assert [next(iter(event)) for event in events] == ["model", "tools", "model"]
    assert calls == [{"source": "local_document", "query": "question", "knowledge_base": "all"}]


def test_restricted_prompt_replaces_delegation_and_filesystem_instructions():
    phase = next(item for item in RESEARCH_PHASES if item.key == "supervisor_research")
    local = build_phase_prompt(
        task_query="question",
        phase=phase,
        phase_outputs={},
        runtime_instructions="actual ledger",
        indexed_local_only=True,
    )
    legacy = build_phase_prompt(
        task_query="question", phase=phase, phase_outputs={}, runtime_instructions="actual ledger"
    )
    assert "INDEXED LOCAL RESEARCH BOUNDARY" in local
    assert "subagent_type=network_search" not in local
    assert "subagent_type=network_search" in legacy
    assert "actual ledger" in local


@pytest.mark.parametrize(
    "query",
    [
        "仅使用本地知识库和数据库分析，不联网",
        "仅使用SQL与本地知识库",
        "仅使用RAG + SQL",
        "仅使用本地知识库及费用引擎",
    ],
)
def test_explicit_source_combinations_do_not_lose_other_tools(query):
    assert not main_agent._requires_local_knowledge_base_only(query)


def test_negated_database_web_fee_list_does_not_disable_local_route():
    assert main_agent._requires_local_knowledge_base_only(
        "仅使用本地知识库，不要使用网络搜索、数据库或费用引擎"
    )


@pytest.mark.parametrize("batch_sizes,advanced_count", [([1, 1, 1], 2), ([3], 0), ([2, 1], 1)])
async def test_local_supplemental_budget_stops_whole_over_limit_batches(
    monkeypatch, batch_sizes, advanced_count
):
    advanced = []

    async def stream(*args):
        for index, size in enumerate(batch_sizes):
            yield {
                "model": {
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "id": f"{index}_{i}",
                                    "name": "collect_evidence",
                                    "args": {"query": "q"},
                                }
                                for i in range(size)
                            ],
                        )
                    ]
                }
            }
            advanced.append(True)

    monkeypatch.setattr(main_agent, "_astream_with_runtime_limit", stream)
    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "_emit", lambda *args, **kwargs: None)
    budget = ResearchBudget(ResearchBudgetLimits("test", 60, 0, 0, 2, 8, 10))
    trace = ResearchRunTrace("run", "thread", "test", budget)
    phase = next(item for item in RESEARCH_PHASES if item.key == "supervisor_research")
    await main_agent._run_agent_phase(
        agent=object(),
        phase=phase,
        prompt="local",
        config={},
        budget=AgentExecutionBudget(recursion_limit=10, timeout_seconds=10),
        budget_profile="test",
        research_budget=budget,
        run_trace=trace,
        allowed_direct_tool_names=frozenset({"collect_evidence"}),
        max_direct_tool_calls=2,
    )
    assert len(advanced) == advanced_count
    assert "local_research_query_limit" in trace.failure_reasons
    assert trace.tool_calls_by_name.get("collect_evidence", 0) <= 2


@pytest.mark.parametrize(
    "tool_name",
    [
        "ls",
        "glob",
        "read_file",
        "write_file",
        "write_todos",
        "task",
        "execute_sql_query",
        "remember_user_memory",
    ],
)
async def test_unavailable_tool_requests_stop_before_stream_advances(monkeypatch, tool_name):
    advanced = []

    async def stream(*args):
        yield {
            "model": {
                "messages": [
                    AIMessage(content="", tool_calls=[{"id": "bad", "name": tool_name, "args": {}}])
                ]
            }
        }
        advanced.append(True)

    monkeypatch.setattr(main_agent, "_astream_with_runtime_limit", stream)
    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "_emit", lambda *args, **kwargs: None)
    limits = ResearchBudgetLimits("test", 60, 0, 0, 2, 8, 10)
    budget = ResearchBudget(limits)
    trace = ResearchRunTrace("run", "thread", "test", budget)
    phase = next(item for item in RESEARCH_PHASES if item.key == "supervisor_research")
    await main_agent._run_agent_phase(
        agent=object(),
        phase=phase,
        prompt="local",
        config={},
        budget=AgentExecutionBudget(recursion_limit=10, timeout_seconds=10),
        budget_profile="test",
        research_budget=budget,
        run_trace=trace,
        allowed_direct_tool_names=frozenset({"collect_evidence"}),
    )
    assert not advanced
    assert trace.blocked_research_tool_calls == 1
    assert trace.failure_reasons == ["research_tool_not_allowed"]


@pytest.mark.parametrize(
    "local,attachment,enabled,expected",
    [
        (True, False, True, "indexed_local_only"),
        (True, False, False, "deepagents_default"),
        (True, True, True, "deepagents_default"),
        (False, False, True, "deepagents_default"),
    ],
)
async def test_workflow_selects_indexed_mode_only_without_real_uploads(
    tmp_path, monkeypatch, local, attachment, enabled, expected
):
    selected = []

    def researcher(name):
        selected.append(name)
        return object()

    async def phase(**kwargs):
        current = kwargs["run_trace"]
        key = kwargs["phase"].key
        current.start_phase(key, key)
        current.finish_phase(key, "end")
        return "phase result"

    async def lookup(*args):
        return None

    monkeypatch.setattr(main_agent, "project_root_path", tmp_path)
    monkeypatch.setattr(main_agent, "get_planner_agent", lambda: object())
    monkeypatch.setattr(main_agent, "get_writer_agent", lambda: object())
    monkeypatch.setattr(main_agent, "get_research_agent", lambda: researcher("deepagents_default"))
    monkeypatch.setattr(
        main_agent, "get_indexed_local_research_agent", lambda: researcher("indexed_local_only")
    )
    monkeypatch.setattr(main_agent, "require_local_retrieval", lookup)
    if local and not attachment and enabled:
        monkeypatch.setenv("REQUIRE_ANALYTICAL_SQL_EVIDENCE", "1")

        async def forbidden_sql(**kwargs):
            raise AssertionError("indexed-local mode cannot prefetch SQL")

        def forbidden_sql_gate(*args):
            raise AssertionError("indexed-local mode cannot enforce SQL evidence")

        monkeypatch.setattr(main_agent, "_prefetch_sql_semantic_context", forbidden_sql)
        monkeypatch.setattr(
            main_agent, "_should_attempt_sql_evidence_correction", forbidden_sql_gate
        )
        monkeypatch.setattr(
            main_agent, "_enforce_research_evidence_requirements", forbidden_sql_gate
        )
    monkeypatch.setattr(main_agent, "_run_agent_phase", phase)
    monkeypatch.setattr(main_agent, "_run_direct_phase", phase)
    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "_emit", lambda *args, **kwargs: None)
    if attachment:
        uploads = tmp_path / "updated/session_route"
        uploads.mkdir(parents=True)
        (uploads / "upload.txt").write_text("actual upload", encoding="utf-8")
    query = "仅使用本地知识库回答问题" if local else "研究公开信息"
    await main_agent.run_deep_agent(query, "route", indexed_local_research_enabled=enabled)
    assert selected == [expected]
    trace = json.loads(
        (tmp_path / "output/session_route/research_trace.json").read_text(encoding="utf-8")
    )
    assert trace["research_tool_mode"] == expected
