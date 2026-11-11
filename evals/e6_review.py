"""Verify the archived E6 pair and prepare its citation audit."""

import argparse
import json
from pathlib import Path
from statistics import mean, median

from evals.scoring_v4 import digest
from evals.worker_supervisor import atomic_json

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "evals/reports"
RESULTS = ROOT / "evals/results"
WORKFLOWS = ("simple", "bounded")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_pair():
    comparison = read(REPORTS / "e6-3-holdout-comparison.json")
    manifests, results, summaries = [], {}, {}
    for workflow, archived in zip(WORKFLOWS, comparison["runs"], strict=True):
        run = RESULTS / f"e6-3-holdout-{workflow}"
        manifest = read(run / "manifest.json")
        rows = read(run / "results.json")
        score_manifest = read(REPORTS / f"e6-3-{workflow}-score-manifest.json")
        scores = read(REPORTS / f"e6-3-{workflow}-score-scores.json")["rows"]
        if (
            digest(rows) != score_manifest["results_sha256"]
            or manifest != archived["manifest"]
            or manifest["workflow"] != workflow
            or len(rows) != 24
            or [row["id"] for row in rows] != manifest["case_ids"]
            or [row["id"] for row in scores] != manifest["case_ids"]
        ):
            raise ValueError(f"E6 archive mismatch for {workflow}")
        if workflow == "simple":
            retry = read(REPORTS / "e6-3-simple-judge-error-retry.json")
            scores = [
                retry["retry_scores"][0] if row["id"] == retry["retry_scores"][0]["id"] else row
                for row in scores
            ]
        per_case = list(zip(rows, scores, archived["rows"], strict=True))
        if any(
            (row["id"], row["status"], row["elapsed_seconds"], score["pass"])
            != (old["id"], old["status"], old["seconds"], old["pass"])
            for row, score, old in per_case
        ):
            raise ValueError(f"E6 case summary mismatch for {workflow}")
        historical = archived["summary"]
        summary = {
            "scheduled": len(rows),
            "completed": sum(row["status"] == "completed" for row in rows),
            "passes": sum(score["pass"] for score in scores),
            "median_seconds": round(median(row["elapsed_seconds"] for row in rows), 2),
            "generator_tokens": sum(
                row["response_metadata"]["usage_metadata"]["total_tokens"] for row in rows
            ),
            "claim_count": sum(len(row["report"]["claims"]) for row in rows),
            "mean_checklist_coverage": round(
                mean(score["checklist_coverage"] for score in scores), 4
            ),
            "cases": [
                {key: old[key] for key in ("id", "status", "pass", "issues")}
                for _, _, old in per_case
            ],
        }
        if (
            summary["completed"],
            summary["passes"],
            summary["median_seconds"],
            summary["generator_tokens"],
        ) != (
            historical["completed"],
            historical["passes"],
            historical["p50_seconds"],
            historical["known_generator_tokens"],
        ):
            raise ValueError(f"E6 aggregate mismatch for {workflow}")
        manifests.append({k: v for k, v in manifest.items() if k != "workflow"})
        results[workflow] = list(zip(rows, scores, strict=True))
        summaries[workflow] = summary
    if manifests[0] != manifests[1]:
        raise ValueError("E6 workflow inputs differ")
    return results, {"manifest": manifests[0], "workflows": summaries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    _, summary = load_pair()
    atomic_json(args.summary, summary)


if __name__ == "__main__":
    main()
