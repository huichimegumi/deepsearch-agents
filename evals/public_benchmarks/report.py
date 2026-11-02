"""Publish metadata-only paired reports without redistributing benchmark task text."""

from __future__ import annotations

import argparse
import statistics
from collections import Counter
from pathlib import Path

from evals.public_benchmarks.score import read
from evals.worker_supervisor import atomic_json


def mean(values):
    return sum(values) / len(values) if values else None


def summarize(run):
    manifest = read(run / "manifest.json")
    results = read(run / "results.json")
    grades = read(run / "score-deepseek/scores.json")["rows"]
    if [r["id"] for r in results] != manifest["case_ids"] or [r["id"] for r in grades] != manifest[
        "case_ids"
    ]:
        raise ValueError("incomplete_results_or_grades")
    rows = []
    suites = {}
    independent_path = run / "score-qwen/scores.json"
    independent = (
        {r["id"]: r for r in read(independent_path)["rows"]} if independent_path.exists() else {}
    )
    for result, grade in zip(results, grades, strict=True):
        secondary = independent.get(result["id"])
        rows.append(
            {
                "id": result["id"],
                "suite": result["suite"],
                "status": result["status"],
                "pass": grade["pass"],
                "coverage": grade.get("checklist_coverage"),
                "support": grade.get("claim_support"),
                "published_weighted_coverage": grade.get("published_weighted_coverage"),
                "issue_codes": sorted({i.split(":", 1)[0] for i in grade.get("issues", [])}),
                "judge_error": bool(grade.get("error")),
                "reference_audit": grade.get("reference_audit"),
                "independent_coverage": secondary.get("checklist_coverage") if secondary else None,
                "independent_support": secondary.get("claim_support") if secondary else None,
                "independent_judge_error": bool(secondary.get("error")) if secondary else None,
            }
        )
    for suite in sorted({r["suite"] for r in rows}):
        group = [r for r in rows if r["suite"] == suite]
        coverage = [r["coverage"] for r in group if r["coverage"] is not None]
        support = [r["support"] for r in group if r["support"] is not None]
        weighted = [
            r["published_weighted_coverage"]
            for r in group
            if r["published_weighted_coverage"] is not None
        ]
        audits = [r["reference_audit"] for r in group if r["reference_audit"] is not None]
        suites[suite] = {
            "scheduled": len(group),
            "completed": sum(r["status"] == "completed" for r in group),
            "passes": sum(r["pass"] is True for r in group) if suite != "drb" else None,
            "judged": len(coverage),
            "mean_coverage_valid_judgements": mean(coverage),
            "mean_coverage_all_scheduled_missing_as_zero": sum(coverage) / len(group),
            "mean_support_valid_claim_sets": mean(support),
            "claim_sets_graded": len(support),
            "mean_published_weighted_coverage": mean(weighted),
            "published_weighted_coverage_all_scheduled_missing_as_zero": sum(weighted) / len(group)
            if suite == "drb"
            else None,
            "sql_audit_available": sum(a.get("available", False) for a in audits)
            if audits
            else None,
            "sql_result_matches": sum(a.get("sql_result_match", False) for a in audits)
            if audits
            else None,
            "executed_direction_matches": sum(a.get("executed_direction", False) for a in audits)
            if audits
            else None,
        }
    elapsed = sorted(r.get("elapsed_seconds", 0) for r in results)
    usage = [(r.get("response_metadata") or {}).get("usage_metadata") for r in results]
    comparison = [
        (r, independent[r["id"]])
        for r in grades
        if r["id"] in independent and not r.get("error") and not independent[r["id"]].get("error")
    ]
    return {
        "workflow": manifest["workflow"],
        "scheduled": len(results),
        "terminal": len(results),
        "statuses": dict(Counter(r["status"] for r in results)),
        "generator_requests": sum(r["model_reservations"]["requests"] for r in results),
        "reserved_tokens": sum(r["model_reservations"]["reserved_tokens"] for r in results),
        "known_generator_tokens": sum(r.get("total_tokens", 0) for r in usage if r is not None),
        "generator_usage_missing": sum(r is None for r in usage),
        "p50_seconds": statistics.median(elapsed) if elapsed else None,
        "p95_seconds": elapsed[min(len(elapsed) - 1, int(len(elapsed) * 0.95))]
        if elapsed
        else None,
        "web_lookup_attempts": sum(
            o["source"] == "web" for r in results for o in r.get("operations", [])
        ),
        "judge": read(run / "score-deepseek/summary.json"),
        "independent_audit": {
            "scheduled": len(independent),
            "valid_paired_grades": len(comparison),
            "judge_errors": sum(bool(r.get("error")) for r in independent.values()),
            "mean_absolute_coverage_difference": mean(
                [abs(a["checklist_coverage"] - b["checklist_coverage"]) for a, b in comparison]
            ),
        },
        "suites": suites,
        "cases": rows,
    }


def publish(runs, output):
    configs = [read(r / "manifest.json") for r in runs]
    if len(runs) == 2:
        for field in (
            "inputs_sha256",
            "source_sha256",
            "lock_sha256",
            "dependency_lock_sha256",
            "databases",
            "case_ids",
            "budget",
            "generator",
            "web_mode",
            "device",
        ):
            if configs[0][field] != configs[1][field]:
                raise ValueError(f"paired_configuration_mismatch:{field}")
    reports = [summarize(r) for r in runs]
    payload = {
        "scope": "Once-only small public-task validation; custom model judge, not official benchmark leaderboard or human accuracy",
        "source_sha256": configs[0]["source_sha256"],
        "reports": reports,
        "limitations": [
            "DABStep shares source data with prior work; checklist judgements are not independently verified numeric correctness",
            "Hybrid is alien-only and public task selection is not an external blind evaluation",
            "Live Web responses can differ across sequential workflow runs",
            "DRB six-task subset uses custom judges and limited retrieval budget; not official RACE/FACT",
            "Independent Qwen judge is a small audit; failed judge calls are not valid agreement",
            "Human review packets exported locally; human review not performed",
        ],
    }
    atomic_json(output.with_suffix(".json"), payload)
    lines = [
        "# E7 public-task validation",
        "",
        "CPU; live free Web; all scheduled failures retained. Custom provisional judges.",
        "",
        "| Workflow | Suite | Completed | Task passes | Coverage¹ | Citation support² | Judged |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]

    def fmt(value):
        return f"{value:.3f}" if value is not None else "N/A"

    for report in reports:
        for suite, s in report["suites"].items():
            passes = (
                f"{s['passes']}/{s['scheduled']}" if s["passes"] is not None else "continuous score"
            )
            lines.append(
                f"| {report['workflow']} | {suite} | {s['completed']}/{s['scheduled']} | {passes} | {fmt(s['mean_coverage_all_scheduled_missing_as_zero'])} | {fmt(s['mean_support_valid_claim_sets'])} | {s['judged']}/{s['scheduled']} |"
            )
    lines += [
        "",
        "¹ Uniform checklist mean across all scheduled cases, missing grades count zero; published weighted DRB rubric scores are separately recorded in JSON.",
        "² Mean across valid graded claim sets; scoped empty refusals have no claim support score. Read with coverage, runtime and pass gates.",
        "",
        "| Workflow | Requests | Reserved tokens | Known generator tokens | Missing usage cases | p50 / p95 seconds |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in reports:
        lines.append(
            f"| {r['workflow']} | {r['generator_requests']} | {r['reserved_tokens']} | {r['known_generator_tokens']} | {r['generator_usage_missing']} | {r['p50_seconds']} / {r['p95_seconds']} |"
        )
    lines += ["", "## Limits", "", *["- " + s for s in payload["limitations"]]]
    for r in reports:
        lines += [
            "",
            f"## {r['workflow']} per-case results",
            "",
            "| Case ID | Suite | Runtime | Pass | Coverage | Support | Issues |",
            "| --- | --- | --- | --- | ---: | ---: | --- |",
        ]
        for c in r["cases"]:
            lines.append(
                f"| {c['id']} | {c['suite']} | {c['status']} | {c['pass']} | {fmt(c['coverage'])} | {fmt(c['support'])} | {', '.join(c['issue_codes'])} |"
            )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, action="append", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    publish(args.run, args.output)
