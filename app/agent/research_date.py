"""Shared time context for research prompts."""

from datetime import date


def research_date_context(current_date: date) -> str:
    return (
        f"当前日期：{current_date.isoformat()}（Current date）\n"
        "For events newer than your model knowledge, rely on credible retrieved sources. "
        "A conflict with your memory alone is insufficient to discredit a source. "
        "Use publication and event dates to distinguish results from forecasts."
    )
