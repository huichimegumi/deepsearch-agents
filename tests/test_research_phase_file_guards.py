"""File generation is only allowed in the final research phase."""

from app.api.context import reset_research_phase_context, set_research_phase_context
from app.tools.markdown_tools import generate_markdown
from app.tools.pdf_tools import convert_md_to_pdf


def test_markdown_generation_is_blocked_before_final_report():
    token = set_research_phase_context("supervisor_research")
    try:
        result = generate_markdown.invoke({"content": "# draft", "filename": "draft"})
    finally:
        reset_research_phase_context(token)

    assert "禁止生成Markdown文件" in result


def test_pdf_generation_is_blocked_before_final_report():
    token = set_research_phase_context("evidence_compression")
    try:
        result = convert_md_to_pdf.invoke({"md_filename": "draft.md"})
    finally:
        reset_research_phase_context(token)

    assert "禁止生成PDF文件" in result
