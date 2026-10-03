from types import SimpleNamespace

from app.agent.main_agent import (
    CompressedEvidence,
    _enforce_final_report_citations,
    _render_validated_compression,
)
from app.agent.runtime import ResearchBudget, ResearchBudgetLimits, ResearchRunTrace
from app.research.claims import (
    ClaimDraft,
    ClaimIssueCode,
    ClaimKind,
    stable_claim_id,
    validate_claims,
    validate_report_citations,
)

KNOWN_EVIDENCE_ID = f"ev1_sql_{'a' * 24}"
UNKNOWN_EVIDENCE_ID = f"ev1_sql_{'b' * 24}"


def _trace() -> ResearchRunTrace:
    budget = ResearchBudget(
        ResearchBudgetLimits(
            profile="test",
            total_seconds=60,
            max_search_queries=1,
            max_fetched_pages=1,
            max_research_rounds=1,
            max_llm_calls=4,
            writer_reserved_seconds=10,
        )
    )
    return ResearchRunTrace("run", "thread", "test", budget)


def test_claim_ids_are_stable_across_evidence_order():
    first = stable_claim_id(
        text="Revenue increased.",
        evidence_ids=["ev1_sql_b", "ev1_sql_a"],
        kind=ClaimKind.FACT,
        limitations=[],
    )
    second = stable_claim_id(
        text="Revenue increased.",
        evidence_ids=["ev1_sql_a", "ev1_sql_b"],
        kind=ClaimKind.FACT,
        limitations=[],
    )

    assert first == second
    assert first.startswith("clm1_")


def test_claim_validation_accepts_only_known_supported_claims():
    report = validate_claims(
        [
            ClaimDraft(text="Known fact", evidence_ids=[KNOWN_EVIDENCE_ID]),
            ClaimDraft(text="No evidence"),
            ClaimDraft(text="Unknown evidence", evidence_ids=[UNKNOWN_EVIDENCE_ID]),
            ClaimDraft(
                text="Unbounded inference",
                evidence_ids=[KNOWN_EVIDENCE_ID],
                kind=ClaimKind.INFERENCE,
            ),
            ClaimDraft(
                text="Bounded inference",
                evidence_ids=[KNOWN_EVIDENCE_ID],
                kind=ClaimKind.INFERENCE,
                limitations=["Only one month is available"],
            ),
        ],
        available_evidence_ids=[KNOWN_EVIDENCE_ID],
    )

    assert [claim.text for claim in report.accepted] == ["Known fact", "Bounded inference"]
    assert len(report.rejected) == 3
    issue_codes = {issue.code for rejected in report.rejected for issue in rejected.issues}
    assert issue_codes == {
        ClaimIssueCode.MISSING_EVIDENCE,
        ClaimIssueCode.UNKNOWN_EVIDENCE,
        ClaimIssueCode.MISSING_INFERENCE_LIMITATION,
    }
    assert report.unknown_evidence_ids == (UNKNOWN_EVIDENCE_ID,)
    assert report.referenced_evidence_ids == (KNOWN_EVIDENCE_ID,)


def test_report_citation_validation_rejects_unknown_and_missing_ids():
    unknown = validate_report_citations(
        f"Supported [{KNOWN_EVIDENCE_ID}] but invented [{UNKNOWN_EVIDENCE_ID}].",
        allowed_evidence_ids=[KNOWN_EVIDENCE_ID],
    )
    missing = validate_report_citations(
        "A report without evidence references.",
        allowed_evidence_ids=[KNOWN_EVIDENCE_ID],
    )

    assert unknown.valid is False
    assert unknown.unknown_evidence_ids == (UNKNOWN_EVIDENCE_ID,)
    assert missing.valid is False
    assert missing.missing_required_citations is True


def test_report_citation_validation_catches_malformed_evidence_like_tokens():
    malformed_id = "ev1_sql_not-a-stable-id"
    validation = validate_report_citations(
        f"Supported [{KNOWN_EVIDENCE_ID}], but this is invented [{malformed_id}].",
        allowed_evidence_ids=[KNOWN_EVIDENCE_ID],
    )

    assert validation.valid is False
    assert validation.unknown_evidence_ids == (malformed_id,)


def test_invalid_writer_output_falls_back_to_validated_claim_package():
    trace = _trace()
    trace.record_evidence((SimpleNamespace(evidence_id=KNOWN_EVIDENCE_ID, source="sql"),))
    claims = validate_claims(
        [ClaimDraft(text="Known fact", evidence_ids=[KNOWN_EVIDENCE_ID])],
        available_evidence_ids=trace.evidence_ids,
    )
    trace.record_claim_validation(claims)

    result, validation = _enforce_final_report_citations(
        report_markdown=f"Invented citation [{UNKNOWN_EVIDENCE_ID}]",
        compressed_fallback=(f"# Validated Claim Package\n\nKnown fact [{KNOWN_EVIDENCE_ID}]"),
        run_trace=trace,
    )

    assert validation.valid is False
    assert result.startswith("# Evidence-Validated Partial Result")
    assert f"Known fact [{KNOWN_EVIDENCE_ID}]" in result
    assert UNKNOWN_EVIDENCE_ID not in result
    assert trace.degraded is True
    assert trace.failure_reasons == ["final_report_citation_validation_failed"]


def test_valid_writer_output_is_preserved_after_citation_validation():
    trace = _trace()
    trace.record_evidence((SimpleNamespace(evidence_id=KNOWN_EVIDENCE_ID, source="sql"),))
    claims = validate_claims(
        [ClaimDraft(text="Known fact", evidence_ids=[KNOWN_EVIDENCE_ID])],
        available_evidence_ids=trace.evidence_ids,
    )
    trace.record_claim_validation(claims)
    report = f"# Final Report\n\nKnown fact [{KNOWN_EVIDENCE_ID}]."

    result, validation = _enforce_final_report_citations(
        report_markdown=report,
        compressed_fallback="# Validated Claim Package",
        run_trace=trace,
    )

    assert validation.valid is True
    assert result == report
    assert trace.report_citation_valid is True
    assert trace.report_cited_evidence_ids == [KNOWN_EVIDENCE_ID]
    assert trace.degraded is False


def test_compression_renderer_records_only_backend_validated_claims():
    trace = _trace()
    trace.record_evidence((SimpleNamespace(evidence_id=KNOWN_EVIDENCE_ID, source="sql"),))
    compressed = CompressedEvidence(
        claims=[
            ClaimDraft(text="Known fact", evidence_ids=[KNOWN_EVIDENCE_ID]),
            ClaimDraft(text="Invented fact", evidence_ids=[UNKNOWN_EVIDENCE_ID]),
        ],
        report_outline=["Summary"],
    )

    markdown = _render_validated_compression(compressed, trace)

    assert "# Validated Claim Package" in markdown
    assert "Known fact" in markdown
    assert "Invented fact" in markdown
    assert "unknown_evidence" in markdown
    assert len(trace.claim_ids) == 1
    assert trace.claim_evidence_ids == [KNOWN_EVIDENCE_ID]
    assert trace.rejected_claims == 1
    assert trace.unknown_claim_evidence_ids == [UNKNOWN_EVIDENCE_ID]
