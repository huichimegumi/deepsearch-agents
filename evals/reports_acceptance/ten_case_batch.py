"""Freeze and summarize the existing six local and four extended report tasks."""

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import median

from evals.reports_acceptance import extended
from evals.reports_acceptance.run import DEFAULT_DATASET, load_cases
from evals.runners.common import ROOT, write_json
from evals.runners.experiment import file_sha256, new_run_id


def private_path(value: str | Path) -> Path:
    path = (Path(value) if Path(value).is_absolute() else ROOT / value).resolve()
    if not path.is_relative_to((ROOT / "evals/results").resolve()):
        raise ValueError("Result path must be under evals/results")
    return path


def plan(lock_path: Path) -> dict:
    local_suite, local_cases = load_cases(DEFAULT_DATASET)
    other_suite = extended.load_suite()
    lock_path = private_path(lock_path)
    lock, _ = extended.validate_lock(lock_path)
    ids = [case["id"] for case in local_cases + other_suite["cases"]]
    if len(ids) != 10 or len(set(ids)) != 10:
        raise ValueError("Expected ten distinct frozen tasks")
    return {
        "schema_version": 1,
        "local_suite": local_suite["version"],
        "local_dataset_sha256": file_sha256(DEFAULT_DATASET),
        "extended_suite": other_suite["version"],
        "extended_dataset_sha256": file_sha256(extended.DATASET),
        "lock_path": lock_path.relative_to(ROOT).as_posix(),
        "lock_sha256": file_sha256(lock_path),
        "corpus_sha256": lock["corpus_sha256"],
        "case_ids": ids,
        "scheduled_search_query_ceiling": sum(c["search_queries"] for c in other_suite["cases"]),
        "acceptance": "pending_human_review",
        "generative_answer_accuracy": None,
    }


def summarize(plan_path: Path, local_path: Path, other_path: Path) -> dict:
    frozen = json.loads(private_path(plan_path).read_text(encoding="utf-8"))
    current = plan(private_path(frozen["lock_path"]))
    if current != frozen:
        raise ValueError("Frozen ten-case plan changed")
    paths = (private_path(local_path), private_path(other_path))
    runs = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    local, other = runs
    if any(run.get("inputs_unchanged") is not True for run in runs):
        raise ValueError("One or both runs have changed inputs")
    if local.get("corpus_sha256") != frozen["corpus_sha256"]:
        raise ValueError("Local corpus differs from extended lock")
    for run, dataset_hash, expected in (
        (local, frozen["local_dataset_sha256"], frozen["case_ids"][:6]),
        (other, frozen["extended_dataset_sha256"], frozen["case_ids"][6:]),
    ):
        if run["manifest"]["dataset_sha256"] != dataset_hash:
            raise ValueError("Run dataset differs from frozen plan")
        if run["manifest"]["configuration"].get("execution_enabled") is not True:
            raise ValueError("Plan-only run cannot be summarized")
        if [row["id"] for row in run["results"]] != expected:
            raise ValueError("Incomplete or reordered ten-case batch")
        if run["manifest"]["configuration"].get("selected_cases") != expected:
            raise ValueError("Selected task manifest differs")
    if (
        local["manifest"]["source_sha256"] != other["manifest"]["source_sha256"]
        or local["manifest"]["configuration"]["model"]
        != other["manifest"]["configuration"]["model"]
        or local["manifest"]["configuration"].get("indexed_local_research_enabled") is not False
        or other["manifest"]["configuration"].get("default_researcher") is not True
        or other["manifest"]["configuration"].get("lock_sha256") != frozen["lock_sha256"]
    ):
        raise ValueError("Run configuration or source version differs")
    rows = []
    for run, path in zip(runs, paths, strict=True):
        for row in run["results"]:
            folder = private_path(row["review_directory"])
            if (
                file_sha256(folder / "report.md") != row["report_sha256"]
                or file_sha256(folder / "evidence.json") != row["evidence_sha256"]
            ):
                raise ValueError("Saved report or Evidence changed")
            rows.append(
                {
                    "id": row["id"],
                    "execution_status": row["execution_status"],
                    "error_type": row["error_type"],
                    "failure_reasons": row["failure_reasons"],
                    "elapsed_seconds": row["elapsed_seconds"],
                    "report_nonempty": row["audit"]["report_nonempty"],
                    "evidence_count": row["audit"]["evidence_count"],
                    "citation_ids_resolve": row["audit"]["citation_ids_resolve"],
                    "all_reference_units_retrieved": row["audit"]["all_reference_units_retrieved"],
                    "all_reference_units_cited": row["audit"]["all_reference_units_cited"],
                    "required_sources_collected": row["audit"].get("required_sources_collected"),
                    "required_sources_cited": row["audit"].get("required_sources_cited"),
                    "llm_calls_instrumented": row["trace_metrics"].get("llm_calls"),
                    "result_path": path.relative_to(ROOT).as_posix(),
                }
            )
    if other["reported_admitted_search_queries"] > frozen["scheduled_search_query_ceiling"]:
        raise ValueError("Reported search admission exceeds frozen ceiling")
    return {
        "schema_version": 1,
        "plan_sha256": file_sha256(private_path(plan_path)),
        "run_sha256": {path.relative_to(ROOT).as_posix(): file_sha256(path) for path in paths},
        "source_sha256": local["manifest"]["source_sha256"],
        "model": local["manifest"]["configuration"]["model"],
        "rows": rows,
        "execution_counts": dict(Counter(row["execution_status"] for row in rows)),
        "median_elapsed_seconds": median(row["elapsed_seconds"] for row in rows),
        "reported_admitted_search_queries": other["reported_admitted_search_queries"],
        "scheduled_search_query_ceiling": frozen["scheduled_search_query_ceiling"],
        "generative_answer_accuracy": None,
        "acceptance": "pending_human_review",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--local-results", type=Path)
    parser.add_argument("--extended-results", type=Path)
    args = parser.parse_args()
    if args.lock and not any((args.plan, args.local_results, args.extended_results)):
        output = ROOT / "evals/results" / new_run_id("ten_case_plan") / "plan.json"
        output.parent.mkdir(parents=True, exist_ok=False)
        write_json(output, plan(args.lock))
    elif args.plan and args.local_results and args.extended_results and not args.lock:
        output = ROOT / "evals/results" / new_run_id("ten_case_summary") / "summary.json"
        output.parent.mkdir(parents=True, exist_ok=False)
        write_json(output, summarize(args.plan, args.local_results, args.extended_results))
    else:
        parser.error("Pass --lock for a plan, or --plan and both completed result paths")
    print(output)


if __name__ == "__main__":
    main()
