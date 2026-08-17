"""Integration checks for trace persistence around the existing workflow shell."""

import json

from app.agent import main_agent


async def test_run_deep_agent_writes_completed_trace(tmp_path, monkeypatch):
    async def fake_phase(**kwargs):
        phase = kwargs["phase"]
        trace = kwargs["run_trace"]
        trace.start_phase(phase.key, phase.title)
        trace.finish_phase(phase.key, "end")
        return "final report" if phase.key == "final_report" else f"{phase.key} output"

    monkeypatch.setattr(main_agent, "project_root_path", tmp_path)
    monkeypatch.setattr(main_agent, "get_planner_agent", lambda: object())
    monkeypatch.setattr(main_agent, "get_research_agent", lambda: object())
    monkeypatch.setattr(main_agent, "get_writer_agent", lambda: object())
    monkeypatch.setattr(main_agent, "_run_agent_phase", fake_phase)
    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "_emit", lambda *args, **kwargs: None)

    result = await main_agent.run_deep_agent("生成完整研究报告", "trace-test")

    trace_path = tmp_path / "output" / "session_trace-test" / "research_trace.json"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert result == "final report"
    assert trace["status"] == "completed"
    assert trace["budget_profile"] == "deep_report"
    assert trace["budget"]["limits"]["total_seconds"] == 300
    assert [phase["status"] for phase in trace["phases"]] == ["end"] * 4
