"""Compare the once-only public DABStep 20-task baseline and final workflow."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from evals.dabstep.holdout20 import validate_selection


def _read(run_dir: Path) -> dict:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    results = {
        row["id"]: row
        for line in (run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
        if (row := json.loads(line))
    }
    scores = {
        row["id"]: row
        for line in (run_dir / "scores.jsonl").read_text(encoding="utf-8").splitlines()
        if (row := json.loads(line))
    }
    return {"dir": run_dir, "manifest": manifest, "results": results, "scores": scores}


def _evidence(run: dict, case_id: str) -> list[dict]:
    attempt = run["results"][case_id]["attempt"]
    result = json.loads((run["dir"] / attempt / "worker_result.json").read_text(encoding="utf-8"))
    return result["evidence"]


def compare(baseline_dir: Path, final_dir: Path) -> dict:
    baseline, final = _read(baseline_dir), _read(final_dir)
    expected = [row["id"] for row in validate_selection()["cases"]]
    for run in (baseline, final):
        if run["manifest"]["case_ids"] != expected:
            raise ValueError("holdout_selection_mismatch")
        if set(run["results"]) != set(expected) or set(run["scores"]) != set(expected):
            raise ValueError("incomplete_run")
    if baseline["manifest"]["workflow"] != "simple_sql_no_fee":
        raise ValueError("wrong_baseline_workflow")
    if final["manifest"]["workflow"] != "simple_sql":
        raise ValueError("wrong_final_workflow")
    for field in (
        "source_sha256",
        "suite_sha256",
        "preflight_input_sha256",
        "profile",
        "timeout_seconds",
        "cleanup_seconds",
        "max_batch_reserved_tokens",
    ):
        if baseline["manifest"][field] != final["manifest"][field]:
            raise ValueError(f"configuration_mismatch:{field}")
    rows = []
    selection = {row["id"]: row["type"] for row in validate_selection()["cases"]}
    for case_id in expected:
        original_evidence = _evidence(baseline, case_id)
        final_evidence = _evidence(final, case_id)
        if (
            final_evidence[: len(original_evidence)] != original_evidence
            or len(final_evidence) != len(original_evidence) + 5
        ):
            raise ValueError(f"sql_evidence_not_identical:{case_id}")
        old, new = baseline["scores"][case_id], final["scores"][case_id]
        old_result, new_result = baseline["results"][case_id], final["results"][case_id]
        rows.append(
            {
                "id": case_id,
                "type": selection[case_id],
                "baseline_status": old_result["status"],
                "final_status": new_result["status"],
                "baseline_pass": old["pass"],
                "final_pass": new["pass"],
                "baseline_coverage": old["checklist_coverage"],
                "final_coverage": new["checklist_coverage"],
                "baseline_supported": old["supported_coverage"],
                "final_supported": new["supported_coverage"],
                "baseline_citation_ids": old["citation_id_validity"],
                "final_citation_ids": new["citation_id_validity"],
                "baseline_seconds": old_result["elapsed_seconds"],
                "final_seconds": new_result["elapsed_seconds"],
            }
        )

    def summary(prefix: str) -> dict:
        return {
            "completed": sum(row[f"{prefix}_status"] == "completed" for row in rows),
            "passes": sum(row[f"{prefix}_pass"] is True for row in rows),
            "mean_checklist_coverage": round(
                statistics.mean(row[f"{prefix}_coverage"] or 0 for row in rows), 3
            ),
            "median_seconds": round(statistics.median(row[f"{prefix}_seconds"] for row in rows), 1),
            "citation_id_valid_cases": sum(row[f"{prefix}_citation_ids"] == 1.0 for row in rows),
        }

    return {
        "baseline_run": baseline_dir.name,
        "final_run": final_dir.name,
        "source_sha256": final["manifest"]["source_sha256"],
        "task_count": len(rows),
        "identical_sql_evidence_cases": len(rows),
        "baseline": summary("baseline"),
        "final": summary("final"),
        "rows": rows,
    }


def render(result: dict) -> str:
    b, f = result["baseline"], result["final"]
    lines = [
        "# Once-only 20-task public DABStep comparison",
        "",
        "All 20 tasks were unseen during workflow development, but share the DABStep source snapshot.",
        "The same DeepSeek judge graded both workflows; scores are provisional.",
        "",
        "| Workflow | Completed | Pass | Mean checklist | Median seconds | Valid citation-ID cases |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        f"| P2 simple, no fee aggregates | {b['completed']}/20 | {b['passes']}/20 | {b['mean_checklist_coverage']:.3f} | {b['median_seconds']:.1f} | {b['citation_id_valid_cases']}/20 |",
        f"| P4 bounded fee evidence | {f['completed']}/20 | {f['passes']}/20 | {f['mean_checklist_coverage']:.3f} | {f['median_seconds']:.1f} | {f['citation_id_valid_cases']}/20 |",
        "",
        "| Case | Type | P2 pass / coverage | P4 pass / coverage |",
        "| --- | --- | ---: | ---: |",
    ]
    for row in result["rows"]:
        lines.append(
            f"| {row['id']} | {row['type']} | "
            f"{'yes' if row['baseline_pass'] else 'no'} / {row['baseline_coverage']} | "
            f"{'yes' if row['final_pass'] else 'no'} / {row['final_coverage']} |"
        )
    lines += ["", "Failures and unscored cases remain in the 20-task denominator.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--final", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.baseline, args.final)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(result), encoding="utf-8")
    args.output.with_suffix(".json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
