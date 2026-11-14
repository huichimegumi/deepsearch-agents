"""Integration checks for trace persistence around the existing workflow shell."""

import json
from types import SimpleNamespace

import pytest

from app.agent import main_agent


@pytest.mark.parametrize("export_evidence", [False, True])
async def test_run_deep_agent_writes_completed_trace(tmp_path, monkeypatch, export_evidence):
    async def fake_phase(**kwargs):
        phase = kwargs["phase"]
        trace = kwargs["run_trace"]
        trace.start_phase(phase.key, phase.title)
        trace.finish_phase(phase.key, "end")
        return "final report" if phase.key == "final_report" else f"{phase.key} output"

    async def fake_direct_phase(**kwargs):
        return await fake_phase(**kwargs)

    monkeypatch.setattr(main_agent, "project_root_path", tmp_path)
    monkeypatch.setattr(main_agent, "get_planner_agent", lambda: object())
    monkeypatch.setattr(main_agent, "get_research_agent", lambda: object())
    monkeypatch.setattr(main_agent, "get_writer_agent", lambda: object())
    monkeypatch.setattr(main_agent, "_run_agent_phase", fake_phase)
    monkeypatch.setattr(main_agent, "_run_direct_phase", fake_direct_phase)
    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "_emit", lambda *args, **kwargs: None)

    result = await main_agent.run_deep_agent(
        "生成完整研究报告", "trace-test", export_evaluation_evidence=export_evidence
    )

    trace_path = tmp_path / "output" / "session_trace-test" / "research_trace.json"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert result == "final report"
    assert trace["status"] == "completed"
    assert trace["budget_profile"] == "deep_report"
    assert trace["budget"]["limits"]["total_seconds"] == 300
    assert [phase["status"] for phase in trace["phases"]] == ["end"] * 4
    assert trace["schema_version"] == 12
    snapshot_path = trace_path.with_name("evaluation_evidence.json")
    assert snapshot_path.exists() is export_evidence
    if export_evidence:
        assert json.loads(snapshot_path.read_text(encoding="utf-8"))["records"] == []


@pytest.mark.parametrize("accepted_claim", [False, True])
async def test_parallel_writer_failure_does_not_deliver_prior_artifacts(
    tmp_path, monkeypatch, accepted_claim
):
    from app.research.claims import ClaimDraft, validate_claims

    async def fake_direct_phase(**kwargs):
        phase = kwargs["phase"]
        trace = kwargs["run_trace"]
        trace.start_phase(phase.key, phase.title)
        if phase.key == "final_report":
            trace.finish_phase(phase.key, "error", "provider_rejected")
            return None
        if phase.key == "evidence_compression" and accepted_claim:
            trace.claim_eligible_evidence_ids.append("ev1_web_known")
            draft = ClaimDraft(
                text="Accepted release date.",
                evidence_ids=["ev1_web_known"],
            )
            trace.record_claim_validation(
                validate_claims([draft], available_evidence_ids=["ev1_web_known"])
            )
        trace.finish_phase(phase.key, "end")
        return "Raw private intermediate artifact"

    async def fake_research(*_args, **_kwargs):
        return "Raw fetched page text"

    monkeypatch.setattr(main_agent, "project_root_path", tmp_path)
    monkeypatch.setattr(main_agent, "get_planner_agent", lambda: object())
    monkeypatch.setattr(
        main_agent, "get_writer_agent", lambda: SimpleNamespace(bind=lambda **_: object())
    )
    monkeypatch.setattr(main_agent, "_run_direct_phase", fake_direct_phase)
    monkeypatch.setattr(main_agent.parallel_research, "research", fake_research)
    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "_emit", lambda *args, **kwargs: None)

    result = await main_agent.run_deep_agent(
        "Research four public web sources",
        "writer-failure",
        research_mode="parallel_web",
        required_evidence_sources=("web",),
    )

    assert "Report generation did not complete" in result
    assert ("Accepted release date." in result) is accepted_claim
    assert ("[ev1_web_known]" in result) is accepted_claim
    assert "Raw" not in result
    path = tmp_path / "output/session_writer-failure/research_trace.json"
    trace = json.loads(path.read_text())
    assert trace["status"] == "degraded"
    assert "parallel_writer_no_report" in trace["failure_reasons"]
    assert trace["phases"][-1]["artifact_status"] == (
        "validated_fallback" if accepted_claim else "fallback"
    )
