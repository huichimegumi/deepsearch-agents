"""Summarize one complete frozen local baseline with explicitly provisional AI triage."""

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import median

from evals.rag.scoring import normalized
from evals.reports_acceptance.run import DEFAULT_DATASET, load_cases
from evals.reports_acceptance.scoring import audit_report
from evals.runners.common import ROOT, write_json, write_markdown
from evals.runners.experiment import build_manifest, file_sha256, new_run_id

REVIEW_SCOPE = "reference_keypoints_and_salient_errors_not_exhaustive_claim_review"
CATEGORIES = {
    "retrieval_gap",
    "evidence_misread",
    "source_misattribution",
    "unsupported_writing",
    "answer_omission",
    "citation_support_mismatch",
}


def saved_path(directory: Path, filename: str) -> Path:
    path = (directory / filename).resolve()
    if not path.is_relative_to((ROOT / "evals/results").resolve()):
        raise ValueError("Saved artifact must remain under evals/results")
    return path


def contains(quote: str, content: str) -> bool:
    return bool(normalized(quote)) and normalized(quote) in normalized(content)


def summarize(results_path: Path, review_path: Path) -> dict:
    original = json.loads(results_path.read_text(encoding="utf-8"))
    review = json.loads(review_path.read_text(encoding="utf-8"))
    _, cases = load_cases(DEFAULT_DATASET)
    known = {case["id"]: case for case in cases}
    config = original["manifest"]["configuration"]
    if (
        original.get("inputs_unchanged") is not True
        or original["manifest"]["dataset_sha256"] != file_sha256(DEFAULT_DATASET)
        or config.get("execution_enabled") is not True
        or config.get("indexed_local_research_enabled") is not False
    ):
        raise ValueError("Requires a finalized frozen default-route baseline")
    if (
        review.get("reviewer_type") != "ai_assistant_preliminary"
        or review.get("human_review") != "pending"
        or review.get("review_scope") != REVIEW_SCOPE
        or review.get("execution_results_sha256") != file_sha256(results_path)
    ):
        raise ValueError("AI triage provenance/binding mismatch")
    expected = Counter(known.keys())
    if (
        Counter(row["id"] for row in original["results"]) != expected
        or Counter(row["id"] for row in review["items"]) != expected
        or Counter(config["selected_cases"]) != expected
    ):
        raise ValueError("Requires every frozen case exactly once; failures cannot be excluded")
    reviews = {row["id"]: row for row in review["items"]}
    rows = []
    for row in original["results"]:
        case, item = known[row["id"]], reviews[row["id"]]
        directory = (ROOT / row["review_directory"]).resolve()
        paths = {
            key: saved_path(directory, name)
            for key, name in (
                ("report", "report.md"),
                ("evidence", "evidence.json"),
                ("trace", "trace.json"),
            )
        }
        for key in paths:
            digest = file_sha256(paths[key])
            if digest != item[key + "_sha256"] or (
                key != "trace" and digest != row[key + "_sha256"]
            ):
                raise ValueError("Saved artifact changed since execution/triage")
        text = paths["report"].read_text(encoding="utf-8")
        snapshot = json.loads(paths["evidence"].read_text(encoding="utf-8"))
        trace = json.loads(paths["trace"].read_text(encoding="utf-8"))
        if (
            trace.get("metrics", {}) != row["trace_metrics"]
            or trace.get("status", "missing_trace") != row["execution_status"]
            or trace.get("failure_reasons", []) != row["failure_reasons"]
        ):
            raise ValueError("Trace differs from executed row")
        if any(row["trace_metrics"].get(key, 0) for key in ("search_queries", "fetched_pages")):
            raise ValueError("Local baseline unexpectedly used network research")
        computed = audit_report(text, snapshot, case)
        if any(computed[key] != row["audit"][key] for key in computed):
            raise ValueError("Mechanical report audit changed")
        by_id = {record["evidence_id"]: record for record in snapshot["records"]}
        drafts = [
            draft["text"]
            for batch in snapshot.get("claim_validation_batches", [])
            for draft in batch["drafts"]
        ]
        if Counter(point["unit_id"] for point in item["keypoints"]) != Counter(
            unit["id"] for unit in case["evidence_units"]
        ):
            raise ValueError("Every reference unit must be assessed exactly once")
        for entry in item["keypoints"] + item["findings"]:
            quote = entry.get("report_quote", "")
            if quote and not contains(quote, text):
                raise ValueError("Invented report quote")
            for evidence in entry["evidence_quotes"]:
                if evidence["evidence_id"] not in by_id or not contains(
                    evidence["quote"], by_id[evidence["evidence_id"]]["content"]
                ):
                    raise ValueError("Invented evidence quote/ID")
            if entry.get("claim_quote") and not any(
                contains(entry["claim_quote"], draft) for draft in drafts
            ):
                raise ValueError("Invented original Claim quote")
        for point in item["keypoints"]:
            if point["coverage"] not in {"covered", "partial", "missing", "uncertain"}:
                raise ValueError("Unknown keypoint judgment")
            if point["coverage"] in {"covered", "partial"} and (
                not point.get("report_quote") or not point["evidence_quotes"]
            ):
                raise ValueError("Positive coverage needs report and source quotations")
        if any(
            finding["category"] not in CATEGORIES or not finding["reason"].strip()
            for finding in item["findings"]
        ):
            raise ValueError("Unknown/empty finding")
        if (
            item["answer_status"]
            not in {"substantive", "partial", "no_answer", "withheld", "uncertain"}
            or not item["summary"].strip()
        ):
            raise ValueError("Invalid answer assessment")
        if item["abstention"] not in (
            {"not_applicable"}
            if case["answerable"]
            else {"insufficient_evidence_notice", "unsupported_absence_assertion", "uncertain"}
        ):
            raise ValueError("Invalid abstention scope")
        if not case["answerable"] and not contains(item.get("abstention_report_quote", ""), text):
            raise ValueError("Negative-case assessment needs an actual report quote")
        metrics = row["trace_metrics"]
        source_withheld = any(
            check["withheld"] for check in trace.get("local_source_reference_checks", [])
        )
        scope_withheld = any(check["withheld"] for check in trace.get("local_scope_checks", []))
        delivery = (
            "source_notice"
            if source_withheld
            else "scope_notice"
            if scope_withheld
            else "no_evidence_notice"
            if trace.get("local_retrieval", {}).get("record_count") == 0
            else "claim_fallback"
            if "final_report_citation_validation_failed" in row["failure_reasons"]
            else "report"
        )
        rows.append(
            {
                "id": row["id"],
                "execution_status": row["execution_status"],
                "error_type": row["error_type"],
                "elapsed_seconds": row["elapsed_seconds"],
                "failure_reasons": row["failure_reasons"],
                "delivery": delivery,
                "llm_calls": metrics.get("llm_calls"),
                "tool_calls": metrics.get("tool_calls"),
                "tool_calls_by_name": metrics.get("tool_calls_by_name", {}),
                "input_tokens": metrics.get("input_tokens"),
                "output_tokens": metrics.get("output_tokens"),
                "evidence_count": computed["evidence_count"],
                "report_nonempty": computed["report_nonempty"],
                "artifact_count": len(row["artifact_paths"]),
                "all_reference_units_retrieved": computed["all_reference_units_retrieved"],
                "all_reference_units_cited": computed["all_reference_units_cited"],
                "final_citation_ids_resolve": computed["citation_ids_resolve"],
                "ai_answer_status": item["answer_status"],
                "ai_summary": item["summary"],
                "ai_keypoint_coverage": [
                    {"unit_id": point["unit_id"], "coverage": point["coverage"]}
                    for point in item["keypoints"]
                ],
                "ai_finding_categories": sorted(
                    {finding["category"] for finding in item["findings"]}
                ),
                "ai_abstention": item["abstention"],
                "artifact_sha256": {key: file_sha256(path) for key, path in paths.items()},
            }
        )
    return {
        "original_run_id": original["run_id"],
        "execution_manifest": original["manifest"],
        "execution_results_sha256": file_sha256(results_path),
        "ai_review_sha256": file_sha256(review_path),
        "corpus_sha256": original["corpus_sha256"],
        "rows": rows,
        "execution_status_counts": dict(Counter(row["execution_status"] for row in rows)),
        "delivery_counts": dict(Counter(row["delivery"] for row in rows)),
        "latency_seconds": {
            "median": median(row["elapsed_seconds"] for row in rows),
            "min": min(row["elapsed_seconds"] for row in rows),
            "max": max(row["elapsed_seconds"] for row in rows),
        },
        "ai_finding_report_counts": dict(
            Counter(category for row in rows for category in row["ai_finding_categories"])
        ),
        "human_review": "pending",
        "human_accuracy": None,
        "claim_support_rate": None,
        "note": "AI keypoint/salient-error triage is provisional and non-exhaustive. Literal quotation checks are not entailment. Final delivered citations include fallback/notice behavior. Token/call instrumentation is not total provider billing; one run per development case is not a service benchmark.",
    }


def render(summary: dict) -> str:
    lines = [
        "# Six-task local baseline",
        "",
        "AI preliminary triage; human review pending. No answer-accuracy or claim-support rate.",
        "",
        "| Task | Execution | Delivery | Seconds | LLM calls | Evidence | Reference retrieved/cited | AI answer |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for row in summary["rows"]:
        lines.append(
            f"| {row['id']} | {row['execution_status']} | {row['delivery']} | {row['elapsed_seconds']} | {row['llm_calls']} | {row['evidence_count']} | {row['all_reference_units_retrieved']}/{row['all_reference_units_cited']} | {row['ai_answer_status']} |"
        )
    lines += ["", "## Per-task initial findings", ""]
    for row in summary["rows"]:
        lines.append(
            f"- {row['id']}: {row['ai_summary']} Failure codes: {', '.join(row['failure_reasons']) or 'none'}."
        )
    lines += ["", summary["note"], ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-results", type=Path, required=True)
    parser.add_argument("--ai-review", type=Path, required=True)
    args = parser.parse_args()
    before = (file_sha256(args.report_results), file_sha256(args.ai_review))
    summary = summarize(args.report_results, args.ai_review)
    summary["summary_manifest"] = build_manifest(
        args.report_results,
        {"mode": "offline_ai_preliminary_baseline_summary", "ai_review_sha256": before[1]},
    )
    if before != (file_sha256(args.report_results), file_sha256(args.ai_review)):
        raise ValueError("Inputs changed during summary")
    directory = ROOT / "evals/results" / new_run_id("local_baseline_summary")
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory / "results.json", summary)
    write_markdown(directory / "SUMMARY.md", render(summary))
    print(directory / "results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
