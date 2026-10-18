"""Regression checks for evaluation admission, provenance, and independent runs."""

import asyncio
from types import SimpleNamespace

import pytest

from app.agent import main_agent
from app.agent.research_workflow import RESEARCH_PHASES
from app.agent.runtime import ResearchBudgetLimits, ResearchRunTrace
from app.config import AgentExecutionBudget
from app.rag import embeddings
from evals.runners.experiment import build_manifest, new_run_id


@pytest.mark.parametrize("seconds", [0, -1])
async def test_zero_phase_time_never_starts_stream(seconds):
    class Agent:
        async def astream(self, *args, **kwargs):
            pytest.fail("Exhausted phase started an agent")
            yield {}

    with pytest.raises(main_agent.PhaseBudgetExceeded, match="phase_time_exhausted"):
        async for _ in main_agent._astream_with_runtime_limit(Agent(), {}, {}, seconds):
            pytest.fail("Exhausted phase emitted output")


async def test_zero_direct_phase_time_does_not_consume_model_capacity(monkeypatch):
    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "report_research_phase", lambda *args, **kwargs: None)
    limits = ResearchBudgetLimits("quick", 60, 3, 4, 1, 6, 15)
    budget = main_agent._create_research_budget(
        "question", limits, sql_entity_recovery_enabled=False
    )
    trace = ResearchRunTrace("run", "thread", "quick", budget)
    result = await main_agent._run_direct_phase(
        model=object(),
        phase=RESEARCH_PHASES[0],
        prompt="question",
        budget=AgentExecutionBudget(1, 0),
        budget_profile="quick",
        research_budget=budget,
        run_trace=trace,
    )
    assert result is None
    assert budget.llm_calls_used == trace.llm_calls == 0
    assert trace.failure_reasons == ["phase_time_exhausted"]


def test_web_clues_keep_capacity_and_sql_opt_in_reserves_only_entity_tasks():
    limits = ResearchBudgetLimits("quick", 60, 3, 4, 1, 6, 15)
    for query, enabled, expected in [
        ("Use these clues to identify a place", False, (3, 4)),
        ("Use these clues to identify a place", True, (1, 2)),
        ("Summarize this document", True, (3, 4)),
    ]:
        budget = main_agent._create_research_budget(
            query, limits, sql_entity_recovery_enabled=enabled
        )
        assert (budget.available_search_queries, budget.available_fetched_pages) == expected


@pytest.mark.parametrize("scores", [[0.7], [float("nan"), 0.2]])
def test_invalid_reranker_results_are_explicit_fallback(monkeypatch, scores):
    monkeypatch.setattr(
        embeddings, "_get_reranker", lambda: SimpleNamespace(rerank=lambda *args: scores)
    )
    result = embeddings.rerank_with_status("query", ["first", "second"])
    assert result.applied is False
    assert result.error_type == "ValueError"
    assert result.scores == [2.0, 1.0]


def test_reranker_unavailable_does_not_claim_model_inference(monkeypatch):
    def unavailable():
        raise RuntimeError("a private model path that must not be logged")

    monkeypatch.setattr(embeddings, "_get_reranker", unavailable)
    result = embeddings.rerank_with_status("query", ["first"])
    assert not result.applied
    assert result.error_type == "RuntimeError"
    assert "private" not in str(result)


def test_manifest_tracks_data_changes_and_independent_runs(tmp_path):
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text("{}\n", encoding="utf-8")
    before = build_manifest(dataset, {"top_k": 5})
    dataset.write_text('{"id":"changed"}\n', encoding="utf-8")
    after = build_manifest(dataset, {"top_k": 5})
    assert before["dataset_sha256"] != after["dataset_sha256"]
    assert before["git_commit"]
    assert new_run_id("report") != new_run_id("report")


async def test_report_execution_retains_earlier_run_artifacts(tmp_path, monkeypatch):
    from evals.runners import run_report_eval as runner

    monkeypatch.setattr(runner, "project_root_path", tmp_path)
    old = tmp_path / "output/user_evals/session_eval_case/report.md"
    old.parent.mkdir(parents=True)
    old.write_text("previous report", encoding="utf-8")
    sessions = []

    async def fake_run(*args, session_id, **kwargs):
        sessions.append(session_id)
        folder = tmp_path / "output/user_evals" / f"session_{session_id}"
        folder.mkdir(parents=True)
        (folder / "report.md").write_text("current report", encoding="utf-8")
        await asyncio.sleep(0)
        return "current report"

    monkeypatch.setattr(runner, "run_deep_agent", fake_run)
    sample = {"id": "case", "task": "write report", "artifact_expectation": "markdown"}
    first = await runner._execute_report_sample(sample, 2, 2, "run1_case")
    second = await runner._execute_report_sample(sample, 2, 2, "run2_case")
    assert old.read_text(encoding="utf-8") == "previous report"
    assert first["artifacts"] != second["artifacts"]
    assert sessions == ["run1_case", "run2_case"]
