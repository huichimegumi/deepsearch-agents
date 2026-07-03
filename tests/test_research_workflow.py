"""Tests for the backend-enforced deep research workflow."""

from app.agent.research_workflow import (
    RESEARCH_PHASES,
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
    assert "才可以调用 generate_markdown" in final_instruction


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
