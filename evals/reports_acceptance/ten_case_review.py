"""Build private source-grounded review worksheets for one frozen ten-case run."""

import argparse
import json
from collections import Counter
from pathlib import Path

from evals.reports_acceptance.support_review import segment_report
from evals.reports_acceptance.ten_case_batch import private_path, summarize
from evals.runners.common import ROOT, write_json, write_markdown
from evals.runners.experiment import file_sha256, new_run_id


def review(plan_path: Path, local_path: Path, extended_path: Path) -> Path:
    summary = summarize(plan_path, local_path, extended_path)
    output = ROOT / "evals/results" / new_run_id("ten_case_review")
    output.mkdir(parents=True, exist_ok=False)
    runs = [
        json.loads(private_path(path).read_text(encoding="utf-8"))
        for path in (local_path, extended_path)
    ]
    rows = []
    for run in runs:
        for row in run["results"]:
            case_id = row["id"]
            source = private_path(row["review_directory"])
            report_path, evidence_path, trace_path = (
                source / "report.md",
                source / "evidence.json",
                source / "trace.json",
            )
            report = report_path.read_text(encoding="utf-8")
            snapshot = json.loads(evidence_path.read_text(encoding="utf-8"))
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            reference_path = source / "reference.json"
            reference = json.loads(reference_path.read_text(encoding="utf-8"))
            if (
                file_sha256(report_path) != row["report_sha256"]
                or file_sha256(evidence_path) != row["evidence_sha256"]
                or trace.get("status", "missing_trace") != row["execution_status"]
                or trace.get("metrics", {}) != row["trace_metrics"]
                or reference["id"] != case_id
            ):
                raise ValueError("Saved review material differs from the executed row")
            if row.get("trace_sha256") and file_sha256(trace_path) != row["trace_sha256"]:
                raise ValueError("Extended trace hash changed")
            segments = segment_report(
                report,
                exclude_rejected_drafts=(
                    "final_report_citation_validation_failed" in row["failure_reasons"]
                    and report.startswith("# Evidence-Validated Partial Result")
                ),
            )
            by_id = {record["evidence_id"]: record for record in snapshot["records"]}
            cited = list(dict.fromkeys(eid for seg in segments for eid in seg["cited_ids"]))
            unknown = sorted(set(cited) - by_id.keys())
            if row["audit"]["evidence_count"] != len(snapshot["records"]):
                raise ValueError("Saved Evidence count differs from execution audit")
            folder = output / case_id
            folder.mkdir()
            payload = {
                "case_id": case_id,
                "question": reference["question"],
                "answer_keypoints": reference["answer_keypoints"],
                "reference_status": run.get(
                    "annotation_review", run.get("asset_lock", {}).get("reference_status")
                ),
                "execution_status": row["execution_status"],
                "failure_reasons": row["failure_reasons"],
                "segments": segments,
                "actual_cited_evidence": {eid: by_id[eid] for eid in cited if eid in by_id},
                "unknown_cited_ids": unknown,
                "reference_evidence_coverage": row["audit"]["reference_evidence_coverage"],
                "required_sources_collected": row["audit"].get("required_sources_collected"),
                "required_sources_cited": row["audit"].get("required_sources_cited"),
                "source_report_sha256": file_sha256(report_path),
                "source_evidence_sha256": file_sha256(evidence_path),
                "source_trace_sha256": file_sha256(trace_path),
                "source_reference_sha256": file_sha256(reference_path),
                "semantic_verdict": "pending_review",
            }
            write_json(folder / "input.json", payload)
            lines = [
                f"# Review {case_id}",
                "",
                "Execution: " + row["execution_status"],
                "Semantic verdict: pending. Check each factual claim against its actual cited passage.",
                "",
                "## Question",
                "",
                reference["question"],
                "",
                "## Required keypoints",
                "",
            ]
            lines += [f"- [ ] {point}" for point in reference["answer_keypoints"]]
            lines += ["", "## Report segments and actual citations", ""]
            for segment in segments:
                lines += [
                    f"### {segment['id']}",
                    "",
                    segment["text"],
                    "",
                    "Cited IDs: " + (", ".join(segment["cited_ids"]) or "none"),
                    "- [ ] supported / partial / unsupported / contradicted / uncertain",
                    "- Evidence quote and reason: pending",
                    "",
                ]
                for eid in segment["cited_ids"]:
                    if eid in by_id:
                        lines += [f"#### Actual {eid}", "", str(by_id[eid]["content"]), ""]
            lines += [
                "## Checks",
                "",
                "Unknown cited IDs: " + str(unknown),
                "Reference evidence coverage: "
                + json.dumps(payload["reference_evidence_coverage"], ensure_ascii=False),
                "A retrieved anchor or valid ID does not establish answer correctness.",
                "Reviewer, corrections and final decision: pending.",
                "",
            ]
            write_markdown(folder / "REVIEW.md", "\n".join(lines))
            signals = []
            if row["execution_status"] != "completed":
                signals.append("execution_degraded")
            if row["audit"]["all_reference_units_retrieved"] is False:
                signals.append("finite_reference_retrieval_gap")
            if row["audit"]["all_reference_units_cited"] is False:
                signals.append("finite_reference_citation_gap")
            if row["audit"]["citation_ids_resolve"] is False:
                signals.append("citation_id_validation_failure")
            if unknown and row["audit"]["citation_ids_resolve"] is True:
                signals.append("historically_missed_unknown_citation")
            if row["audit"].get("required_sources_collected") is False:
                signals.append("required_source_missing")
            rows.append(
                {
                    "id": case_id,
                    "signals": signals,
                    "review_input_sha256": file_sha256(folder / "input.json"),
                    "semantic_verdict": None,
                }
            )
    result = {
        "schema_version": 1,
        "plan_sha256": summary["plan_sha256"],
        "source_run_sha256": summary["run_sha256"],
        "rows": rows,
        "signal_counts": dict(Counter(signal for row in rows for signal in row["signals"])),
        "human_accuracy": None,
    }
    write_json(output / "results.json", result)
    return output / "results.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--local-results", required=True, type=Path)
    parser.add_argument("--extended-results", required=True, type=Path)
    args = parser.parse_args()
    print(review(args.plan, args.local_results, args.extended_results))


if __name__ == "__main__":
    main()
