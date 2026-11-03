"""Gate new validation on the frozen eight-case development results, never on optimism."""

from __future__ import annotations

import argparse
from pathlib import Path

from evals.diagnostics.e8 import LOCK, digest, read
from evals.worker_supervisor import atomic_json


def evaluate(run, score):
    lock = read(LOCK)
    rows = read(run / "results.json")
    grades = read(score / "scores.json")["rows"]
    manifest = read(score / "manifest.json")
    if manifest["cases_sha256"] != lock["references_sha256"]:
        raise ValueError("development_gate_references_changed")
    expected = [r["id"] for r in lock["cases"]]
    # Selection lock stores the same public order, not the grouping order.
    if (
        set(expected) != {r["id"] for r in rows}
        or len(rows) != 8
        or [r["id"] for r in rows] != [r["id"] for r in grades]
    ):
        raise ValueError("development_gate_case_mismatch")
    if manifest["results_sha256"] != digest(rows):
        raise ValueError("development_gate_scores_stale")
    budgets = all(
        r.get("model_reservations", {}).get("requests", 99) <= 8
        and r.get("model_reservations", {}).get("reserved_tokens", 999999) <= 180000
        and len(r.get("operations", [])) <= 5
        and r.get("elapsed_seconds", 999999) <= 330
        for r in rows
    )
    citations = not any("unknown_citation" in g["issues"] for g in grades)
    passes = sum(g["pass"] for g in grades)
    return {
        "scope": "Conditional release into NEW evaluation, not a claim of generalization",
        "scheduled": 8,
        "passes": passes,
        "required_passes": 6,
        "case_budgets_respected": budgets,
        "citation_identity_valid": citations,
        "passed": passes >= 6 and budgets and citations,
        "new_validation": "eligible_to_prepare"
        if passes >= 6 and budgets and citations
        else "NOT RUN: development gate not met",
        "source_result_sha256": digest(rows),
        "score_version": manifest["version"],
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--score", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = evaluate(args.run, args.score)
    atomic_json(args.output, result)
    print(result)
