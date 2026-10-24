import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from app.agent import main_agent
from app.agent.runtime import ResearchBudget, ResearchBudgetLimits, ResearchRunTrace
from app.research import local_retrieval as gate
from app.research.evidence import EvidenceBatch, EvidenceBatchStatus, EvidenceRecord, EvidenceSource


def new_trace():
    limits = ResearchBudgetLimits("deep_report", 300, 0, 0, 2, 12, 75)
    trace = ResearchRunTrace("run", "thread", "deep_report", ResearchBudget(limits))
    trace.local_retrieval_required = True
    return trace


def evidence():
    return EvidenceRecord.create(
        source=EvidenceSource.LOCAL_DOCUMENT,
        locator="document://source#chunk=1",
        content="private body",
    )


@pytest.fixture(autouse=True)
def quiet_audit(monkeypatch):
    monkeypatch.setattr(gate, "write_audit_event", lambda *args, **kwargs: None)


@pytest.mark.parametrize(
    "state,status",
    [
        ("not_executed", None),
        ("error", "ERROR"),
        ("error", "TIMEOUT"),
        ("no_evidence", "NO_EVIDENCE"),
    ],
)
def test_zero_evidence_states_are_distinct_and_never_assert_absence(state, status):
    trace = new_trace()
    if status:
        trace.record_local_retrieval(status, 0)
    report = gate.local_evidence_boundary(trace)
    assert trace.local_retrieval_summary()["state"] == state
    assert f"`{state}`" in report
    assert "不代表文档不存在" in report
    assert trace.degraded is (state != "no_evidence")


def test_positive_evidence_is_not_automatic_acceptance_or_error_erasure():
    trace = new_trace()
    trace.record_local_retrieval("ERROR", 0)
    trace.record_evidence((evidence(),))
    trace.record_local_retrieval("PARTIAL", 1)
    assert trace.local_retrieval_summary()["state"] == "evidence"
    assert trace.local_retrieval_summary()["had_error"]
    assert gate.local_evidence_boundary(trace) is None
    assert "private body" not in json.dumps(trace.local_retrieval_summary())


def test_nonlocal_task_is_unaffected():
    trace = new_trace()
    trace.local_retrieval_required = False
    assert gate.local_evidence_boundary(trace) is None
    assert not trace.degraded


async def test_mandatory_lookup_uses_named_bases_and_original_query(monkeypatch):
    trace = new_trace()
    query = "仅使用本地知识库（金融行业、电商行业）回答原问题"
    monkeypatch.setattr(
        gate,
        "_resolve_knowledge_bases",
        lambda _: [SimpleNamespace(name=name) for name in ["金融行业", "电商行业", "rag-test"]],
    )
    requests = []

    def collect(request):
        requests.append(request)
        return EvidenceBatch(EvidenceSource.LOCAL_DOCUMENT, EvidenceBatchStatus.OK, (evidence(),))

    monkeypatch.setattr(gate, "collect_evidence_request", collect)
    await gate.require_local_retrieval(query, trace, 1)
    assert [request.knowledge_base for request in requests] == ["金融行业", "电商行业"]
    assert all(request.query == query for request in requests)
    assert trace.local_retrieval_summary()["record_count"] == 1
    assert len(trace.local_retrieval_attempts) == 2
    assert trace.tool_calls_by_name["collect_evidence_request"] == 2


async def test_zero_budget_never_starts_lookup(monkeypatch):
    def forbidden(*args):
        raise AssertionError("must not start")

    monkeypatch.setattr(gate, "_resolve_knowledge_bases", forbidden)
    trace = new_trace()
    await gate.require_local_retrieval("question", trace, 0)
    assert trace.local_retrieval_summary()["state"] == "not_executed"


async def test_errors_are_not_no_evidence_and_provider_text_not_in_trace(monkeypatch):
    monkeypatch.setattr(gate, "_resolve_knowledge_bases", lambda _: [])
    monkeypatch.setattr(
        gate,
        "collect_evidence_request",
        lambda _: EvidenceBatch(
            EvidenceSource.LOCAL_DOCUMENT,
            EvidenceBatchStatus.ERROR,
            warnings=("private provider message",),
        ),
    )
    trace = new_trace()
    await gate.require_local_retrieval("question", trace, 1)
    assert trace.local_retrieval_summary()["state"] == "error"
    assert trace.degraded
    assert "private provider message" not in json.dumps(
        trace.finalize(status="completed", final_result="")
    )


async def test_timed_out_thread_cannot_register_late_evidence(monkeypatch):
    monkeypatch.setattr(gate, "_resolve_knowledge_bases", lambda _: [])

    def slow(_):
        time.sleep(0.08)
        return EvidenceBatch(EvidenceSource.LOCAL_DOCUMENT, EvidenceBatchStatus.OK, (evidence(),))

    monkeypatch.setattr(gate, "collect_evidence_request", slow)
    trace = new_trace()
    await gate.require_local_retrieval("question", trace, 0.02)
    await asyncio.sleep(0.1)
    assert trace.local_retrieval_summary()["state"] == "error"
    assert trace.local_retrieval_attempts[-1]["status"] == "TIMEOUT"
    assert not trace.evidence_ids


@pytest.mark.parametrize("status", ["ERROR", "NO_EVIDENCE", None])
async def test_workflow_withholds_model_absence_claims_without_evidence(
    tmp_path, monkeypatch, status
):
    calls = []

    async def lookup(query, trace, timeout):
        if status:
            trace.record_local_retrieval(status, 0)

    async def phase(**kwargs):
        current = kwargs["phase"]
        calls.append(current.key)
        trace = kwargs["run_trace"]
        trace.start_phase(current.key, current.title)
        trace.finish_phase(current.key, "end")
        return "ASSERTION THAT DOCUMENT IS ABSENT"

    monkeypatch.setattr(main_agent, "project_root_path", tmp_path)
    for name in (
        "get_planner_agent",
        "get_research_agent",
        "get_indexed_local_research_agent",
        "get_writer_agent",
    ):
        monkeypatch.setattr(main_agent, name, lambda: object())
    monkeypatch.setattr(main_agent, "require_local_retrieval", lookup)
    monkeypatch.setattr(main_agent, "_run_agent_phase", phase)
    monkeypatch.setattr(main_agent, "_run_direct_phase", phase)
    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "_emit", lambda *args, **kwargs: None)
    result = await main_agent.run_deep_agent(
        "仅使用本地知识库回答问题，生成 Markdown", "local-gate"
    )
    assert "ASSERTION THAT DOCUMENT IS ABSENT" not in result
    assert "不代表文档不存在" in result
    assert calls == ["clarify_and_brief", "supervisor_research"]
    directory = tmp_path / "output/session_local-gate"
    assert (directory / "report.md").read_text(encoding="utf-8") == result
    saved = json.loads((directory / "research_trace.json").read_text(encoding="utf-8"))
    assert saved["local_retrieval"]["required"] is True


async def test_positive_workflow_looks_up_before_agent_and_charges_phase_time(
    tmp_path, monkeypatch
):
    calls = []
    evidence_id = evidence().evidence_id

    async def lookup(query, trace, timeout):
        calls.append("lookup")
        trace.record_evidence((evidence(),))
        trace.record_local_retrieval("OK", 1)
        await asyncio.sleep(0.02)

    async def phase(**kwargs):
        key = kwargs["phase"].key
        calls.append(key)
        trace = kwargs["run_trace"]
        trace.start_phase(key, key)
        trace.finish_phase(key, "end")
        if key == "supervisor_research":
            assert trace.evidence_ids == [evidence_id]
            assert kwargs["budget"].timeout_seconds < 149.99
            assert evidence_id in kwargs["prompt"]
        if key == "evidence_compression":
            trace.claim_evidence_ids.append(evidence_id)
        return f"report [{evidence_id}]"

    monkeypatch.setattr(main_agent, "project_root_path", tmp_path)
    for name in (
        "get_planner_agent",
        "get_research_agent",
        "get_indexed_local_research_agent",
        "get_writer_agent",
    ):
        monkeypatch.setattr(main_agent, name, lambda: object())
    monkeypatch.setattr(main_agent, "require_local_retrieval", lookup)
    monkeypatch.setattr(main_agent, "_run_agent_phase", phase)
    monkeypatch.setattr(main_agent, "_run_direct_phase", phase)
    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "_emit", lambda *args, **kwargs: None)
    result = await main_agent.run_deep_agent("仅使用本地知识库回答问题", "positive-gate")
    assert calls == [
        "clarify_and_brief",
        "lookup",
        "supervisor_research",
        "evidence_compression",
        "final_report",
    ]
    assert result == f"report [{evidence_id}]"


async def test_exhausted_run_uses_unexecuted_boundary_without_starting_models(
    tmp_path, monkeypatch
):
    async def forbidden(**kwargs):
        raise AssertionError("exhausted run must not start a phase")

    monkeypatch.setattr(main_agent, "project_root_path", tmp_path)
    for name in (
        "get_planner_agent",
        "get_research_agent",
        "get_indexed_local_research_agent",
        "get_writer_agent",
    ):
        monkeypatch.setattr(main_agent, name, lambda: object())
    monkeypatch.setattr(main_agent, "_run_agent_phase", forbidden)
    monkeypatch.setattr(main_agent, "_run_direct_phase", forbidden)
    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "_emit", lambda *args, **kwargs: None)
    limits = ResearchBudgetLimits("deep_report", 0, 0, 0, 2, 12, 0)
    result = await main_agent.run_deep_agent(
        "仅使用本地知识库回答问题，生成 Markdown",
        "no-time",
        research_limits_override=limits,
    )
    assert "`not_executed`" in result
    assert "不代表文档不存在" in result
    saved = json.loads(
        (tmp_path / "output/session_no-time/research_trace.json").read_text(encoding="utf-8")
    )
    assert saved["status"] == "degraded"
    assert saved["local_retrieval"]["attempts"] == []


def test_other_source_records_cannot_satisfy_local_gate():
    trace = new_trace()
    trace.record_evidence(
        (
            EvidenceRecord.create(
                source=EvidenceSource.SQL, locator="sql://query", content={"count": 4}
            ),
        )
    )
    assert gate.local_evidence_boundary(trace) is not None
    assert trace.local_retrieval_summary()["record_count"] == 0
