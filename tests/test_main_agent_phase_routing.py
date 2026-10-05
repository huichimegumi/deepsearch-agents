"""Tests for backend-enforced phase capability routing."""

from app.agent.main_agent import (
    _max_subagent_calls_for_profile,
    _phase_agent_for,
    _research_tools,
)
from app.agent.prompts import sub_agents_content
from app.agent.research_workflow import RESEARCH_PHASES


def test_phase_agent_routing_enforces_capability_boundaries():
    planner_agent = object()
    research_agent = object()
    writer_agent = object()

    routed = {
        phase.key: _phase_agent_for(
            phase=phase,
            planner_agent=planner_agent,
            research_agent=research_agent,
            writer_agent=writer_agent,
        )
        for phase in RESEARCH_PHASES
    }

    assert routed["clarify_and_brief"] is planner_agent
    assert routed["supervisor_research"] is research_agent
    assert routed["evidence_compression"] is planner_agent
    assert routed["final_report"] is writer_agent


def test_subagent_call_limits_scale_by_budget_profile():
    assert _max_subagent_calls_for_profile("quick") == 2
    assert _max_subagent_calls_for_profile("standard") == 4
    assert _max_subagent_calls_for_profile("deep_report") == 8


def test_research_phase_exposes_unified_evidence_tool():
    assert "collect_evidence" in {item.name for item in _research_tools()}


def test_network_researcher_requires_fetched_web_evidence():
    prompt = sub_agents_content["search"]["system_prompt"]

    assert "fetch_full_page=true" in prompt
    assert "evidence_status=FETCHED" in prompt
    assert "CANDIDATE_ONLY" in prompt
    assert "ev1_web_..." in prompt
