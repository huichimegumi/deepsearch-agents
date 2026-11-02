"""Publish complete v4 runtime and scoring comparisons without copying source excerpts."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter
from pathlib import Path


def load(run: Path, cases: list[dict]) -> dict:
    manifest = json.loads((run / "manifest.json").read_text())
    results = json.loads((run / "results.json").read_text())
    original_scores = json.loads((run / "score-v4/scores.json").read_text())
    scores = list(original_scores["rows"])
    primary_passes = sum(row["pass"] for row in scores)
    retry_count = 0
    overlay = run / "score-v4/error_retries.json"
    if overlay.exists():
        from evals.scoring_v4 import digest

        recovery = json.loads(overlay.read_text())
        scoring_manifest = json.loads((run / "score-v4/manifest.json").read_text())
        if recovery["original_scores_sha256"] != digest(original_scores) or recovery[
            "original_manifest_sha256"
        ] != digest(scoring_manifest):
            raise ValueError("judge_retry_original_mismatch")
        retry_ids = {row["id"] for row in recovery["retry_scores"]}
        retry_manifest = recovery["retry_manifest"]
        if retry_manifest["cases_sha256"] != digest(
            [row for row in cases if row["id"] in retry_ids]
        ) or retry_manifest["results_sha256"] != digest(
            [row for row in results if row["id"] in retry_ids]
        ):
            raise ValueError("judge_retry_input_mismatch")
        for key in ("version", "scorer_sha256", "instruction_sha256", "replicates"):
            if retry_manifest[key] != scoring_manifest[key]:
                raise ValueError("judge_retry_configuration_mismatch")
        by_id = {row["id"]: index for index, row in enumerate(scores)}
        for row in recovery["retry_scores"]:
            old = scores[by_id[row["id"]]]
            if (
                not old["judge_errors"]
                or old["judge_responses"]
                or old["issues"] != row["issues"]
                or old["reference_checks"] != row["reference_checks"]
            ):
                raise ValueError("judge_retry_ineligible_case")
            retry_count += 1
            if not row["judge_errors"]:
                scores[by_id[row["id"]]] = {**row, "original_judge_errors": old["judge_errors"]}
    ids = [row["id"] for row in cases]
    if (
        manifest["case_ids"] != ids
        or [row["id"] for row in results] != ids
        or [row["id"] for row in scores] != ids
    ):
        raise ValueError("incomplete_or_reordered_run")
    durations = sorted(row.get("elapsed_seconds", 0) for row in results)
    categories = {case["id"]: case["category"] for case in cases}
    rows = [
        {
            "id": row["id"],
            "category": categories[row["id"]],
            "status": row.get("status"),
            "seconds": raw.get("elapsed_seconds"),
            "pass": row["pass"],
            "checklist": row.get("checklist_coverage"),
            "claim_support": row.get("claim_support"),
            "issues": row["issues"],
            "judge_errors": row["judge_errors"],
            "numeric_checks": row["reference_checks"],
        }
        for row, raw in zip(scores, results, strict=True)
    ]
    usage = [row.get("generator_usage") for row in scores]
    summary = {
        "scheduled": len(cases),
        "terminal": len(results),
        "completed": sum(row["status"] == "completed" for row in rows),
        "passes": sum(row["pass"] for row in rows),
        "primary_passes": primary_passes,
        "judge_error_retries": retry_count,
        "judge_errors_unresolved": sum(bool(row["judge_errors"]) for row in rows),
        "statuses": dict(Counter(row["status"] for row in rows)),
        "p50_seconds": round(statistics.median(durations), 2),
        "p95_seconds": durations[math.ceil(0.95 * len(durations)) - 1],
        "known_generator_tokens": sum((item or {}).get("total_tokens", 0) for item in usage),
        "generator_usage_missing": sum(item is None for item in usage),
        "reserved_tokens": sum(
            row.get("model_reservations", {}).get("reserved_tokens", 0) for row in results
        ),
        "requests": sum(row.get("model_reservations", {}).get("requests", 0) for row in results),
    }
    return {"run_id": run.name, "manifest": manifest, "summary": summary, "rows": rows}


def publish(paths: list[Path], cases_path: Path, output: Path) -> dict:
    cases = json.loads(cases_path.read_text())
    runs = [load(path, cases) for path in paths]
    if len(runs) > 1:
        for run in runs[1:]:
            for key in (
                "source_sha256",
                "public_tasks_sha256",
                "sources_sha256",
                "database_sha256",
                "case_ids",
                "deadline_seconds",
                "case_model_token_reservation_limit",
                "batch_token_reservation_limit",
                "profile",
                "web_mode",
            ):
                if run["manifest"][key] != runs[0]["manifest"][key]:
                    raise ValueError(f"comparison_configuration_mismatch:{key}")
    result = {
        "case_file": str(cases_path),
        "runs": runs,
        "limitations": "Internally authored engineering tasks over official RFC snapshots; not an official benchmark score. Snapshot retrieval excludes live web-search reliability. LLM support grades remain provisional.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    lines = [
        "# Shared application v4 evaluation",
        "",
        result["limitations"],
        "",
        "| Workflow | Completed | Pass | p50 s | p95 s | Requests | Reserved tokens | Known generator tokens | Missing usage cases |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    notes = []
    for run in runs:
        s = run["summary"]
        lines.append(
            f"| {run['manifest']['workflow']} | {s['completed']}/{s['scheduled']} | {s['passes']}/{s['scheduled']} | {s['p50_seconds']} | {s['p95_seconds']} | {s['requests']} | {s['reserved_tokens']} | {s['known_generator_tokens']} | {s['generator_usage_missing']} |"
        )
        if s["judge_error_retries"]:
            notes += [
                "",
                f"Original {run['manifest']['workflow']} passes: {s['primary_passes']}; "
                f"judge-error-only retries: {s['judge_error_retries']}; unresolved: {s['judge_errors_unresolved']}. "
                "Research was not rerun; original score artifacts are retained.",
                "",
            ]
    lines += notes
    for run in runs:
        lines += [
            "",
            f"## {run['manifest']['workflow']} ({run['run_id']})",
            "",
            "| Case | Category | Runtime | Coverage | Claim support | Pass | Mechanical issues |",
            "| --- | --- | --- | ---: | ---: | --- | --- |",
        ]
        for row in run["rows"]:
            lines.append(
                f"| {row['id']} | {row['category']} | {row['status']} | {row['checklist']} | {row['claim_support']} | {row['pass']} | {', '.join(row['issues'])} |"
            )
    output.write_text("\n".join(lines) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, action="append", required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = publish(args.run, args.cases, args.output)
    print(json.dumps([row["summary"] for row in result["runs"]], indent=2))


if __name__ == "__main__":
    main()
