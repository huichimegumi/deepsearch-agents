"""Compare a frozen six-case, two-model, two-workflow evaluation matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path


def _load(run_dir: Path) -> dict:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    results = {
        row["id"]: row
        for line in (run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
        if (row := json.loads(line))
    }
    scores_path = run_dir / "scores.jsonl"
    if not scores_path.is_file():
        raise ValueError(f"missing_scores: {run_dir}")
    scores = {
        row["id"]: row
        for line in scores_path.read_text(encoding="utf-8").splitlines()
        if (row := json.loads(line))
    }
    ids = manifest["case_ids"]
    if set(results) != set(ids) or set(scores) != set(ids):
        raise ValueError(f"incomplete_run: {run_dir}")
    return {"dir": run_dir, "manifest": manifest, "results": results, "scores": scores}


def _evidence_hash(run: dict, case_id: str) -> str | None:
    row = run["results"][case_id]
    path = run["dir"] / row["attempt"] / "worker_result.json"
    result = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    evidence = result.get("evidence")
    if not isinstance(evidence, list):
        return None
    serialized = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


def compare(paths: list[Path]) -> dict:
    if len(paths) != 4:
        raise ValueError("expected_four_runs")
    runs = {
        (item["manifest"]["profile"], item["manifest"]["workflow"]): item
        for path in paths
        if (item := _load(path.resolve()))
    }
    expected = {
        ("deepseek", "simple_sql"),
        ("qwen", "simple_sql"),
        ("deepseek", "agent"),
        ("qwen", "agent"),
    }
    if set(runs) != expected:
        raise ValueError("matrix_profiles_missing_or_duplicate")
    first = runs["deepseek", "simple_sql"]["manifest"]
    ids = first["case_ids"]
    for run in runs.values():
        manifest = run["manifest"]
        for field in (
            "case_ids",
            "suite_sha256",
            "preflight_input_sha256",
            "timeout_seconds",
            "cleanup_seconds",
            "max_batch_reserved_tokens",
        ):
            if manifest[field] != first[field]:
                raise ValueError(f"matrix_config_mismatch:{field}")
    evidence_matches = {}
    for case_id in ids:
        left = _evidence_hash(runs["deepseek", "simple_sql"], case_id)
        right = _evidence_hash(runs["qwen", "simple_sql"], case_id)
        evidence_matches[case_id] = bool(left and left == right)
    if not all(evidence_matches.values()):
        raise ValueError("fixed_evidence_mismatch")
    matrix = {}
    for profile, workflow in sorted(expected):
        run = runs[profile, workflow]
        cases = []
        for case_id in ids:
            raw = run["results"][case_id]
            scored = run["scores"][case_id]
            cases.append(
                {
                    "id": case_id,
                    "status": raw["status"],
                    "elapsed_seconds": raw["elapsed_seconds"],
                    "model_request_count": raw.get("model_request_count"),
                    "model_reserved_tokens": raw.get("model_reserved_tokens"),
                    "checklist_coverage": scored.get("checklist_coverage"),
                    "supported_coverage": scored.get("supported_coverage"),
                    "citation_id_validity": scored.get("citation_id_validity"),
                    "pass": scored.get("pass"),
                }
            )
        matrix[f"{profile}_{workflow}"] = {
            "run_id": run["dir"].name,
            "source_sha256": run["manifest"]["source_sha256"],
            "terminal": len(cases),
            "completed": sum(row["status"] == "completed" for row in cases),
            "passes": sum(row["pass"] is True for row in cases),
            "median_elapsed_seconds": statistics.median(row["elapsed_seconds"] for row in cases),
            "reserved_tokens": sum(row["model_reserved_tokens"] or 0 for row in cases),
            "cases": cases,
        }
    return {
        "case_ids": ids,
        "fixed_evidence_identical": evidence_matches,
        "runs": matrix,
        "comparator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "caveat": "Six exposed DABStep SQL cases; model judge scores are provisional, not independent generalization.",
    }


def render(result: dict) -> str:
    lines = [
        "# Six-case paired model and workflow comparison",
        "",
        "All six simple-flow cases received byte-identical SQL Evidence across models.",
        "The cases are public SQL tasks already exposed during development, not a new holdout.",
        "",
        "| Profile | Workflow | Terminal | Completed | Pass | Median seconds | Reserved tokens |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, run in result["runs"].items():
        profile, workflow = name.split("_", 1)
        lines.append(
            f"| {profile} | {workflow} | {run['terminal']} | {run['completed']} | "
            f"{run['passes']} | {run['median_elapsed_seconds']:.1f} | {run['reserved_tokens']} |"
        )
    lines += [
        "",
        "| Case | DeepSeek simple | Qwen simple | DeepSeek agent | Qwen agent |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for index, case_id in enumerate(result["case_ids"]):
        values = []
        for name in ("deepseek_simple_sql", "qwen_simple_sql", "deepseek_agent", "qwen_agent"):
            row = result["runs"][name]["cases"][index]
            score = row["checklist_coverage"]
            values.append(f"{row['status']} / {score:.2f}" if score is not None else row["status"])
        lines.append(f"| {case_id} | " + " | ".join(values) + " |")
    lines += [
        "",
        "Pass requires completed execution as well as checklist and citation thresholds. "
        "A missing checklist score means no scorable answer; it is never removed from the denominator.",
        "The same DeepSeek model judged both generators, so judge preference and variance remain limitations.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.run)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(result), encoding="utf-8")
    args.output.with_suffix(".json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
