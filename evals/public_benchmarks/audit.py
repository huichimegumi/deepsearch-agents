"""Export anonymous local review packets; never claim an unperformed human review."""

from __future__ import annotations

import argparse
from pathlib import Path

from evals.public_benchmarks.score import digest, read
from evals.worker_supervisor import atomic_json


def export(runs, inputs, output):
    cases = read(inputs / "references.json")
    packets, key = [], []
    selected = set()
    for suite in sorted({case["suite"] for case in cases}):
        selected.update(
            case["id"]
            for case in sorted(
                [c for c in cases if c["suite"] == suite],
                key=lambda c: digest(["e7-independent-audit", c["id"]]),
            )[:2]
        )
    for run in runs:
        results = {row["id"]: row for row in read(run / "results.json")}
        for case in cases:
            if case["id"] not in selected:
                continue
            audit_id = digest(["e7-review", str(run.resolve()), case["id"]])[:16]
            result = results[case["id"]]
            packets.append(
                {
                    "audit_id": audit_id,
                    "question": case["question"],
                    "candidate": result["report"],
                    "evidence": result.get("evidence", []),
                    "rubric": case["oracle"]["checklist"],
                    "reviewer_grade": None,
                }
            )
            key.append(
                {
                    "audit_id": audit_id,
                    "run": str(run),
                    "case_id": case["id"],
                    "reference": case["oracle"].get("reference"),
                }
            )
    packets.sort(key=lambda row: row["audit_id"])
    if output.exists():
        raise ValueError("audit_export_already_exists")
    output.mkdir(parents=True)
    atomic_json(
        output / "packets.json",
        {"scope": "Local anonymous packets; human review NOT performed", "packets": packets},
    )
    atomic_json(output / "private_key.json", {"mapping": key})
    return {"packets": len(packets), "reviewed": 0, "output": str(output)}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, action="append", required=True)
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    print(export(args.run, args.inputs, args.output))
