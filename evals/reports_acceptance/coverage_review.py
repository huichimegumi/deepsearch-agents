"""Offline, explicitly provisional coverage review; never rewrites model outcomes."""

from app.research.claims import validate_report_citations
from evals.reports_acceptance.extractive import ExtractiveCompression, validate_quotes


def diagnose_review(case_input: dict, audit: dict, reviews: list[dict]) -> dict:
    """Check reviewed source spans and distinguish selection gaps from model misses.

    A reviewer, not substring matching, decides whether a passage is sufficient.
    This function verifies provenance/accounting only. No human attestation is created.
    """
    required = set(case_input["question_parts"])
    review_ids = [row["part_id"] for row in reviews]
    audit_ids = [row["part_id"] for row in audit["parts"]]
    if (
        len(review_ids) != len(required)
        or set(review_ids) != required
        or len(audit_ids) != len(required)
        or set(audit_ids) != required
    ):
        raise ValueError("review_requires_exactly_one_entry_per_part")
    proposals = {row["part_id"]: row for row in audit["parts"]}
    by_review = {row["part_id"]: row for row in reviews}
    output, handoff = [], []
    for part_id, label in case_input["question_parts"].items():
        review = by_review[part_id]
        assessment = review["assessment"]
        if assessment not in {"sufficient", "insufficient"}:
            raise ValueError("unknown_review_assessment")
        quotes = review.get("quotes", [])
        checked = validate_quotes(ExtractiveCompression(quotes=quotes), case_input["records"])
        if checked["rejected"] or (assessment == "sufficient" and not checked["accepted"]):
            raise ValueError("review_source_quote_not_verified")
        extra = [
            quote
            for quote in checked["accepted"]
            if not any(
                quote["evidence_id"] == old["evidence_id"] and quote["quote"] in old["quote"]
                for old in case_input["prior_extracts"]
            )
        ]
        if assessment == "insufficient":
            classification = "insufficient_saved_evidence"
        elif extra:
            classification = "selected_extract_gap"
        elif proposals[part_id]["status"] == "unresolved":
            classification = "selected_support_not_used"
        else:
            classification = "selected_support_candidate"
        output.append(
            {
                "part_id": part_id,
                "classification": classification,
                "model_status": proposals[part_id]["status"],
                "review_assessment": assessment,
                "note": review.get("note", ""),
                "verified_quotes": checked["accepted"],
                "additional_source_spans": len(extra),
            }
        )
        handoff.append(
            {
                "part_id": part_id,
                "label": label,
                "reviewed_evidence_state": assessment,
                "quotes": checked["accepted"] if assessment == "sufficient" else [],
            }
        )
    return {
        "reviewer": "AI provisional source review; not human adjudication",
        "diagnostics": output,
        "reviewed_source_handoff": handoff,
        "model_candidate_parts": audit["candidate_parts"],
        "model_unresolved_parts": audit["unresolved_parts"],
        "human_accuracy": None,
    }


def render_reviewed_handoff(diagnostics: dict) -> str:
    """Expose verified original text and explicit unresolved parts, not reviewed answers."""
    lines = ["# Reviewed source handoff", "", "AI 初步选段；引文已逐字核验，充分性未经人工确认。"]
    for row in diagnostics["reviewed_source_handoff"]:
        lines += ["", "## " + row["label"]]
        if row["reviewed_evidence_state"] == "insufficient":
            lines += ["待补证据：当前有限输入未确认足够支持，不能据此断言资料不存在。"]
        else:
            for quote in row["quotes"]:
                validation = validate_report_citations(
                    quote["quote"],
                    allowed_evidence_ids=[quote["evidence_id"]],
                    citations_required=False,
                )
                if not validation.valid:
                    raise ValueError("source_quote_contains_foreign_citation")
                lines += [f"[{quote['evidence_id']}]", quote["quote"]]
    return "\n".join(lines)
