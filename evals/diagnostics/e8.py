"""Freeze exposed E7 development tasks; no new validation is read by development."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from evals.worker_supervisor import atomic_json

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
LOCK = HERE / "e8-dev.lock.json"
INPUTS = ROOT / "evals/results/e8-inputs/development"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def freeze():
    old = ROOT / "evals/results/e7-inputs/validation"
    public = read(old / "public.json")
    references = read(old / "references.json")
    selected = []
    for suite, direction, count in (
        ("dabstep", None, 2),
        ("hybrid", "search_to_sql", 2),
        ("hybrid", "sql_to_search", 2),
        ("hybrid", "parallel", 2),
    ):
        eligible = [
            r
            for r in references
            if r["suite"] == suite
            and (direction is None or r["oracle"].get("direction") == direction)
        ]
        ranked = sorted(eligible, key=lambda r: digest(["e8-development-2026-11-03", r["id"]]))
        selected += ranked[:count]
    ids = {r["id"] for r in selected}
    pub = [r for r in public if r["id"] in ids]
    refs = [next(c for c in selected if c["id"] == r["id"]) for r in pub]
    manifest = {
        "version": "e8-dev-1",
        "origin": "Previously exposed E7 cases, DEVELOPMENT ONLY",
        "cases": [
            {
                "id": r["id"],
                "suite": r["suite"],
                "direction": r["oracle"].get("direction"),
                "reference_sha256": digest(r),
            }
            for r in refs
        ],
        "public_sha256": digest(pub),
        "references_sha256": digest(refs),
        "budget": {
            "model_requests": 8,
            "reserved_tokens": 180000,
            "tool_lookups": 5,
            "seconds": 300,
            "worker_seconds": 330,
        },
        "gate": {
            "required_passes": 6,
            "scheduled": 8,
            "citation_identity": 1.0,
            "repair_rounds": 1,
        },
        "rules": [
            "No oracle in generator inputs",
            "E7 grades unchanged",
            "One concentrated repair and one rerun",
            "New validation runs only after the development gate passes",
            "No paid search or GPU",
        ],
    }
    if LOCK.exists() and read(LOCK) != manifest:
        raise ValueError("frozen_development_inputs_changed")
    atomic_json(LOCK, manifest)
    INPUTS.mkdir(parents=True, exist_ok=True)
    atomic_json(INPUTS / "public.json", pub)
    atomic_json(INPUTS / "references.json", refs)
    print(
        json.dumps(
            {"cases": len(pub), "public_sha256": digest(pub), "references_sha256": digest(refs)}
        )
    )


def audit():
    lock = read(LOCK)
    ids = {c["id"] for c in lock["cases"]}
    groups = []
    for flow in ("simple", "bounded"):
        run = ROOT / f"evals/results/e7-4-validation-{flow}"
        results = [r for r in read(run / "results.json") if r["id"] in ids]
        grades = {r["id"]: r for r in read(run / "score-deepseek/scores.json")["rows"]}
        rows = []
        for r in results:
            expected = sum(o.get("record_count", 0) for o in r.get("operations", []))
            rows.append(
                {
                    "id": r["id"],
                    "status": r["status"],
                    "retrieved_record_events": expected,
                    "delivered_unique_records": len(r.get("evidence", [])),
                    "context_limit": any(
                        "evidence_context_limit" in w for w in r.get("warnings", [])
                    ),
                    "tool_error_count": sum("error" in o for o in r.get("operations", [])),
                    "grade_issue_codes": sorted(
                        {s.split(":")[0] for s in grades[r["id"]].get("issues", [])}
                    ),
                }
            )
        groups.append({"workflow": flow, "cases": rows})
    return {
        "scope": "Read-only diagnosis; retrieval event count may include duplicates; missing dropped records cannot be reconstructed from E7 traces",
        "runs": groups,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--freeze", action="store_true")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if args.freeze:
        freeze()
    if args.output:
        atomic_json(args.output, audit())
