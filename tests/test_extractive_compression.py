import pytest

from evals.reports_acceptance.extractive import (
    ExtractiveCompression,
    SourceQuote,
    render_quotes,
    validate_quotes,
)

TEXT = "The experimental build is optionally available in the installer."
ID = "ev1_web_" + "a" * 24


def record(**overrides):
    return {
        "evidence_id": ID,
        "source": "web",
        "content": TEXT,
        "metadata": {"content_kind": "fetched_page_text"},
        **overrides,
    }


def test_exact_quotes_are_deduplicated_and_rendered_with_source():
    quote = SourceQuote(evidence_id=ID, quote=TEXT)
    result = validate_quotes(ExtractiveCompression(quotes=[quote, quote]), [record()])
    assert result == {"accepted": [quote.model_dump()], "rejected": []}
    assert f"[{ID}]\n{TEXT}" in render_quotes(result)


@pytest.mark.parametrize("text", [TEXT.upper(), TEXT.replace("optionally", "automatically")])
def test_paraphrases_and_wrong_installation_inferences_are_rejected(text):
    result = validate_quotes(
        ExtractiveCompression(quotes=[SourceQuote(evidence_id=ID, quote=text)]), [record()]
    )
    assert result["accepted"] == []
    assert result["rejected"][0]["reason"] == "not_exact_substring"


@pytest.mark.parametrize("records", [[], [record(source="sql")], [record(metadata={})]])
def test_matching_text_without_eligible_fetched_web_source_is_rejected(records):
    result = validate_quotes(
        ExtractiveCompression(quotes=[SourceQuote(evidence_id=ID, quote=TEXT)]), records
    )
    assert not result["accepted"]
    assert result["rejected"][0]["reason"] == "ineligible_evidence"
