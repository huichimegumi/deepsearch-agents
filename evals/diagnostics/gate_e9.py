"""Require BOTH reporting and assisted SQL component gates before new research."""

from __future__ import annotations

import argparse
from pathlib import Path

from evals.diagnostics.e8 import ROOT, digest, read
from evals.diagnostics.e9 import LOCK
from evals.worker_supervisor import atomic_json


def evaluate(writer, sql):
    lock = read(LOCK)
    report, report_manifest = read(writer / "summary.json"), read(writer / "manifest.json")
    queries, query_manifest = read(sql / "summary.json"), read(sql / "manifest.json")
    expected = {row["id"] for row in lock["cases"]}
    hybrid = {row["id"] for row in lock["cases"] if row["suite"] == "hybrid"}
    if {row["id"] for row in report["cases"]} != expected or len(report["cases"]) != 8:
        raise ValueError("writer_component_selection_mismatch")
    if {row["id"] for row in queries["cases"]} != hybrid or len(queries["cases"]) != 6:
        raise ValueError("sql_component_selection_mismatch")
    if report_manifest["source_results_sha256"] != digest(
        read(ROOT / "evals/results/e8-4-recheck/results.json")
    ):
        raise ValueError("writer_source_results_changed")
    if report_manifest["provider"] != "qwen" or query_manifest["provider"] != "qwen":
        raise ValueError("e9_qwen_policy_mismatch")
    writer_passes = sum(
        row["offline_pass"] and row.get("live_pass", False) for row in report["cases"]
    )
    sql_matches = sum(row["sql_result_match"] for row in queries["cases"])
    writer_ok, sql_ok = writer_passes == 8, sql_matches >= 4
    return {
        "scope": "Component readiness, never an end-to-end benchmark grade",
        "writer_passes": writer_passes,
        "writer_required": 8,
        "sql_matches": sql_matches,
        "sql_required": 4,
        "writer_passed": writer_ok,
        "sql_passed": sql_ok,
        "components_passed": writer_ok and sql_ok,
        "full_development": "ELIGIBLE FOR ONE FROZEN RUN"
        if writer_ok and sql_ok
        else "NOT RUN: component gates not met",
        "new_validation": "NOT RUN: requires independent end-to-end development gate",
        "component_results_sha256": {"writer": digest(report), "sql": digest(queries)},
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--writer", type=Path, required=True)
    p.add_argument("--sql", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = evaluate(args.writer, args.sql)
    atomic_json(args.output, result)
    print(result)
