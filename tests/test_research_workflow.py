"""Tests for the backend-enforced deep research workflow."""

from app.agent.research_workflow import (
    RESEARCH_PHASES,
    build_degraded_phase_output,
    build_phase_prompt,
    format_previous_phase_outputs,
)


def test_research_phases_keep_expected_order():
    assert [phase.key for phase in RESEARCH_PHASES] == [
        "clarify_and_brief",
        "supervisor_research",
        "evidence_compression",
        "final_report",
    ]


def test_only_final_phase_allows_file_generation():
    internal_instructions = "\n\n".join(phase.instruction for phase in RESEARCH_PHASES[:-1])
    final_instruction = RESEARCH_PHASES[-1].instruction

    assert "禁止调用 generate_markdown" in internal_instructions
    assert "后端会保存并校验正文" in final_instruction


def test_phase_prompt_carries_previous_outputs():
    prompt = build_phase_prompt(
        task_query="研究AI电商应用",
        phase=RESEARCH_PHASES[1],
        phase_outputs={"clarify_and_brief": "brief text"},
        runtime_instructions="runtime rules",
    )

    assert "【用户原始问题】" in prompt
    assert "brief text" in prompt
    assert "runtime rules" in prompt
    assert "阶段 2/4" in prompt


def test_previous_outputs_are_ordered_by_workflow():
    formatted = format_previous_phase_outputs(
        {
            "evidence_compression": "compressed evidence",
            "clarify_and_brief": "brief",
        }
    )

    assert formatted.index("brief") < formatted.index("compressed evidence")


def test_final_phase_prompt_blocks_research_tools():
    prompt = build_phase_prompt(
        task_query="write final report",
        phase=RESEARCH_PHASES[-1],
        phase_outputs={"evidence_compression": "compressed evidence"},
        runtime_instructions="runtime rules",
    )

    assert "FINAL REPORT TOOL BOUNDARY" in prompt
    assert "Do not call researcher subagents" in prompt


def test_final_phase_receives_compressed_handoff_not_raw_ledger():
    prompt = build_phase_prompt(
        task_query="write final report",
        phase=RESEARCH_PHASES[-1],
        phase_outputs={
            "clarify_and_brief": "brief",
            "supervisor_research": "very large raw ledger",
            "evidence_compression": "compact evidence",
        },
        runtime_instructions="filesystem instructions",
    )

    assert "brief" in prompt
    assert "compact evidence" in prompt
    assert "very large raw ledger" not in prompt
    assert "filesystem instructions" not in prompt


def test_non_research_phase_prompt_declares_no_tool_boundary():
    prompt = build_phase_prompt(
        task_query="compress evidence",
        phase=RESEARCH_PHASES[2],
        phase_outputs={"supervisor_research": "ledger"},
        runtime_instructions="runtime rules",
    )

    assert "NO-TOOL PHASE BOUNDARY" in prompt
    assert "record it as a gap" in prompt


def test_supervisor_phase_prompt_declares_research_boundary():
    prompt = build_phase_prompt(
        task_query="research market",
        phase=RESEARCH_PHASES[1],
        phase_outputs={"clarify_and_brief": "brief"},
        runtime_instructions="runtime rules",
    )

    assert "RESEARCH PHASE BOUNDARY" in prompt
    assert "only phase where researcher subagents" in prompt


def test_degraded_phase_output_preserves_next_phase_context():
    degraded = build_degraded_phase_output(
        task_query="research topic",
        phase=RESEARCH_PHASES[1],
        phase_outputs={"clarify_and_brief": "brief"},
        reason="recursion_limit",
    )

    assert "Degraded Evidence Ledger" in degraded
    assert "recursion_limit" in degraded
    assert "clarify_and_brief" in degraded
