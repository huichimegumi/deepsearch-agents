"""Publish E8 metadata without questions, reference answers, SQL or raw model/source text."""

from __future__ import annotations

import argparse
import hashlib
from collections import Counter
from pathlib import Path

from evals.diagnostics.e8 import digest, read
from evals.worker_supervisor import atomic_json


def publish(run: Path, output: Path, score: Path | None = None):
    score = score or run / "score-e8"
    results = read(run / "results.json")
    scores = read(score / "scores.json")["rows"]
    manifest = read(score / "manifest.json")
    if manifest["results_sha256"] != digest(results):
        raise ValueError("publication_score_results_mismatch")
    if [r["id"] for r in results] != [g["id"] for g in scores]:
        raise ValueError("publication_case_mismatch")
    cases = []
    for result, grade in zip(results, scores, strict=True):
        operations = result.get("operations", [])
        attempt = run / hashlib.sha256(result["id"].encode()).hexdigest()[:16] / "attempt-0001"
        response_metadata = [
            read(path).get("metadata", {}) for path in (attempt / "trace").glob("*response.json")
        ]
        contexts = [read(path) for path in (attempt / "evidence").glob("context-*.json")]
        runtime_diagnostics = {
            "model_finish_reasons": dict(
                Counter(m.get("finish_reason", "unknown") for m in response_metadata)
            ),
            "format_failure_attempts": len(list(attempt.glob("writer-format-*.json"))),
            "binding_failure_attempts": len(list(attempt.glob("writer-binding-*.json"))),
            "max_evidence_view_tokens": max(
                (c["estimated_tokens"] for c in contexts), default=None
            ),
            "max_evidence_view_records": max(
                (c["selected_records"] for c in contexts), default=None
            ),
            "successful_source_queries": dict(
                Counter(
                    o["source"]
                    for o in operations
                    if o.get("operation", "query") == "query"
                    and o.get("record_count", 0) > 0
                    and "error" not in o
                )
            ),
        }
        cases.append(
            {
                "runtime_diagnostics": runtime_diagnostics,
                "id": result["id"],
                "suite": result["suite"],
                "status": result["status"],
                "answerability": result["report"]["answerability"],
                "pass": grade["pass"],
                "coverage": grade["coverage"],
                "support": grade["support"],
                "issues": sorted({x.split(":")[0] for x in grade["issues"]}),
                "judge_error_count": len(grade["judge_errors"]),
                "reference_audit": grade["reference_audit"],
                "claims": len(result["report"]["claims"]),
                "facts": len(result["report"]["facts"]),
                "evidence_records": len(result.get("evidence", [])),
                "evidence_sources": dict(Counter(r["source"] for r in result.get("evidence", []))),
                "tool_actions": len(operations),
                "tool_error_classes": dict(
                    Counter(o["error"].split(":")[0] for o in operations if o.get("error"))
                ),
                "model_reservations": result["model_reservations"],
                "elapsed_seconds": result["elapsed_seconds"],
            }
        )
    summary = {
        "scope": "Eight exposed DEVELOPMENT cases; not new validation or a generalization estimate",
        "execution_manifest": read(run / "manifest.json"),
        "scoring_manifest": manifest,
        "scoring_summary": read(score / "summary.json"),
        "grading_caveat": "Failed judge batches remain unknown and prevent task passes. The scorer summary mean_coverage fills unknown coverage with zero; it is a conservative diagnostic, not a fully observed accuracy estimate. Controlled calibration does not establish natural-report reliability.",
        "observed_coverage_cases": sum(c["coverage"] is not None for c in cases),
        "diagnosis_summary": {
            "answerability": dict(Counter(c["answerability"] for c in cases)),
            "content_threshold_only_passes": sum(
                (c["coverage"] or 0) >= 0.8 and (c["support"] or 0) >= 0.9 for c in cases
            ),
            "hybrid_sql_matches": sum(
                bool((c["reference_audit"] or {}).get("sql_result_match")) for c in cases
            ),
            "hybrid_direction_matches": sum(
                bool((c["reference_audit"] or {}).get("executed_direction")) for c in cases
            ),
            "cases_with_tool_errors": sum(bool(c["tool_error_classes"]) for c in cases),
            "cases_with_output_length_finish": sum(
                c["runtime_diagnostics"]["model_finish_reasons"].get("length", 0) > 0 for c in cases
            ),
            "content_threshold_note": "Diagnostic only; ignores delivery, completeness tags, source and SQL/direction gates. Never used for task passes.",
        },
        "cases": cases,
    }
    if (run / "gate.json").exists():
        gate = read(run / "gate.json")
        key = (
            "gate"
            if gate["score_version"] == manifest["version"]
            and gate["source_result_sha256"] == digest(results)
            else "historical_gate"
        )
        summary[key] = gate
    atomic_json(output, summary)
    print({"output": str(output), "cases": len(cases), "passes": sum(c["pass"] for c in cases)})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--score", type=Path)
    args = p.parse_args()
    publish(args.run, args.output, args.score)
