"""Mechanical checks only: citation existence is not claim entailment."""

import re

from app.research.claims import validate_report_citations
from evals.rag.scoring import matches


def audit_report(report: str, snapshot: dict | None, case: dict) -> dict:
    records = (snapshot or {}).get("records", [])
    by_id = {record["evidence_id"]: record for record in records}
    citations = validate_report_citations(
        report,
        allowed_evidence_ids=by_id,
        citations_required=case["answerable"],
    )
    cited_ids = set(citations.cited_evidence_ids)
    coverage = []
    for unit in case["evidence_units"]:
        found, cited = [], []
        for evidence_id, record in by_id.items():
            if record["source"] != "local_document":
                continue
            match = re.match(r"document://sha256/([a-f0-9]{64})#", record["locator"])
            hit = {
                "document_sha256": match.group(1) if match else "",
                "content": str(record["content"]),
            }
            if matches(unit, hit):
                found.append(evidence_id)
                if evidence_id in cited_ids:
                    cited.append(evidence_id)
        coverage.append({"unit_id": unit["id"], "retrieved_ids": found, "cited_ids": cited})
    return {
        "report_nonempty": bool(report.strip()),
        "evidence_snapshot_present": snapshot is not None,
        "evidence_count": len(records),
        "observed_sources": sorted({record["source"] for record in records}),
        "cited_ids": list(citations.cited_evidence_ids),
        "unknown_cited_ids": list(citations.unknown_evidence_ids),
        "missing_required_citations": citations.missing_required_citations,
        "citation_ids_resolve": citations.valid if snapshot is not None else None,
        "reference_evidence_coverage": coverage,
        "all_reference_units_retrieved": all(row["retrieved_ids"] for row in coverage)
        if case["answerable"]
        else None,
        "all_reference_units_cited": all(row["cited_ids"] for row in coverage)
        if case["answerable"]
        else None,
        "keypoint_correctness": "pending_human_review",
        "claim_entailment": "pending_human_review",
        "appropriate_abstention": None if case["answerable"] else "pending_human_review",
        "acceptance": "pending_human_review",
    }


def review_worksheet(case: dict, audit: dict) -> str:
    lines = [
        f"# Review: {case['id']}",
        "",
        "Status: pending_human_review. Do not infer acceptance from mechanical checks.",
        "Open report.md and evidence.json next to this worksheet.",
        "",
        f"Question: {case['question']}",
        "",
        "## Required keypoints",
        "",
    ]
    for point in case["answer_keypoints"]:
        lines.append(f"- [ ] Correctly answered, with supporting cited passage: {point}")
    if not case["answerable"]:
        lines.append("- [ ] Explicitly states insufficient local evidence; invents no answer.")
    lines.extend(
        [
            "",
            "## Claim audit",
            "",
            "For every material claim, record the report quote, evidence_id, passage quote,",
            "supported/unsupported/contradicted verdict, and reason. ID existence is insufficient.",
            "Check numbers, dates, source scope, limitations, and unsupported recommendations.",
            "",
            f"Unknown citation IDs: {audit['unknown_cited_ids']}",
            "",
            "Reviewer: pending",
            "Verdict (pass/partial/fail): pending",
            "Notes:",
        ]
    )
    return "\n".join(lines) + "\n"
