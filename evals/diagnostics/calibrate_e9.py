"""Qwen-only authored controls for E9 fixed-field scoring."""

from __future__ import annotations

import argparse
import asyncio
import copy
from pathlib import Path

from app.research.request_budget import RequestBudget, usage
from evals.diagnostics.e8 import digest, read
from evals.diagnostics.score_e8 import mechanical
from evals.diagnostics.score_e9 import judge_chunk
from evals.public_benchmarks.calibrate import fixtures
from evals.public_benchmarks.score import model_for
from evals.worker_supervisor import atomic_json


async def run(output):
    output.mkdir(parents=True, exist_ok=True)
    cases = fixtures()
    multiple = copy.deepcopy(cases[0])
    multiple["id"] = "eight_claims_two_batches"
    multiple["result"]["report"]["claims"] *= 8
    cases.append(multiple)
    config = {
        "version": "e9-control-1",
        "provider": "qwen",
        "cases_sha256": digest(cases),
        "scorer_sha256": digest(Path(__file__).with_name("score_e9.py").read_text()),
    }
    if (output / "manifest.json").exists() and read(output / "manifest.json") != config:
        raise ValueError("calibration_resume_mismatch")
    atomic_json(output / "manifest.json", config)
    model = model_for("qwen")
    budget = RequestBudget(
        output / "requests.jsonl", max_requests=24, max_reserved_tokens=300000, finalizing=True
    )
    rows = []
    with budget.activate():
        for fixture in cases:
            grades, errors = {}, []
            for kind, items in (
                ("criteria", fixture["case"]["oracle"]["checklist"]),
                ("claims", fixture["result"]["report"]["claims"]),
            ):
                scores = []
                for start in range(0, len(items), 4):
                    path = output / f"{fixture['id']}-{kind}-{start}.json"
                    if path.exists():
                        grade = read(path)
                    else:
                        try:
                            grade = await judge_chunk(
                                kind,
                                items[start : start + 4],
                                fixture["case"],
                                fixture["result"],
                                model,
                            )
                        except Exception as exc:
                            grade = {"error": type(exc).__name__}
                        atomic_json(path, grade)
                    if grade.get("error"):
                        errors.append(grade["error"])
                    scores += grade.get("scores", [])
                grades[kind] = scores
            coverage = (
                sum(grades["criteria"]) / len(grades["criteria"]) if grades["criteria"] else 0
            )
            accepted = (
                not errors
                and not mechanical(fixture["case"], fixture["result"])
                and coverage >= 0.8
                and all(s == 1 for s in grades["claims"])
            )
            rows.append(
                {
                    "id": fixture["id"],
                    "expected_accept": fixture["expected_accept"],
                    "accepted": bool(accepted),
                    "matched": not errors and bool(accepted) == fixture["expected_accept"],
                    "judge_errors": errors,
                }
            )
    summary = {
        "provider": "qwen",
        "scheduled": len(rows),
        "matched": sum(r["matched"] for r in rows),
        "error_cases": sum(bool(r["judge_errors"]) for r in rows),
        "cases": rows,
        "reservations": usage(budget.path),
        "scope": "Authored protocol controls, not natural-report accuracy or human agreement",
    }
    atomic_json(output / "summary.json", summary)
    print(summary)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    asyncio.run(run(p.parse_args().output))
