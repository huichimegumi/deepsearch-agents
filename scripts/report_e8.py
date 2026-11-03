"""Publish E8 metadata without questions, reference answers, SQL or raw model/source text."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from evals.diagnostics.e8 import digest, read
from evals.worker_supervisor import atomic_json


def publish(run: Path, output: Path):
    results = read(run / "results.json")
    scores = read(run / "score-e8/scores.json")["rows"]
    manifest = read(run / "score-e8/manifest.json")
    if manifest["results_sha256"] != digest(results):
        raise ValueError("publication_score_results_mismatch")
    if [r["id"] for r in results] != [g["id"] for g in scores]:
        raise ValueError("publication_case_mismatch")
    cases = []
    for result, grade in zip(results, scores, strict=True):
        operations = result.get("operations", [])
        cases.append(
            {
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
        "scoring_summary": read(run / "score-e8/summary.json"),
        "cases": cases,
    }
    if (run / "gate.json").exists():
        summary["gate"] = read(run / "gate.json")
    atomic_json(output, summary)
    print({"output": str(output), "cases": len(cases), "passes": sum(c["pass"] for c in cases)})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    publish(args.run, args.output)
