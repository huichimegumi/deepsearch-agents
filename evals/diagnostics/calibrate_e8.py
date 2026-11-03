"""Run the same authored control candidates through E8 small-batch judging."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.research.report import ResearchReport
from app.research.request_budget import RequestBudget, usage
from evals.diagnostics.e8 import digest, read
from evals.diagnostics.score_e8 import judge_chunk, mechanical
from evals.public_benchmarks.calibrate import fixtures
from evals.public_benchmarks.score import model_for
from evals.worker_supervisor import atomic_json


async def run(output):
    output.mkdir(parents=True, exist_ok=True)
    import copy

    cases = fixtures()
    multiple = copy.deepcopy(cases[0])
    multiple["id"] = "multi_batch_eight_claims"
    multiple["result"]["report"]["claims"] *= 8
    cases.append(multiple)
    config = {
        "version": "e8-control-2",
        "cases_sha256": digest(cases),
        "scorer_sha256": __import__("hashlib")
        .sha256(Path(__file__).with_name("score_e8.py").read_bytes())
        .hexdigest(),
    }
    if (output / "manifest.json").exists() and read(output / "manifest.json") != config:
        raise ValueError("calibration_resume_mismatch")
    atomic_json(output / "manifest.json", config)
    rows = []
    for provider in ("deepseek", "qwen"):
        model = model_for(provider)
        budget = RequestBudget(
            output / f"{provider}-requests.jsonl",
            max_requests=30,
            max_reserved_tokens=300000,
            finalizing=True,
        )
        with budget.activate():
            for fixture in cases:
                report = ResearchReport.model_validate(fixture["result"]["report"])
                scores = {}
                errors = []
                for kind, items in (
                    ("criteria", fixture["case"]["oracle"]["checklist"]),
                    ("claims", [c.model_dump() for c in report.claims]),
                ):
                    if not items:
                        scores[kind] = []
                        continue
                    combined = []
                    for start in range(0, len(items), 4):
                        batch = items[start : start + 4]
                        path = output / f"{provider}-{fixture['id']}-{kind}-{start}.json"
                        if path.exists():
                            grade = read(path)
                        else:
                            try:
                                grade = await judge_chunk(
                                    kind, batch, fixture["case"], fixture["result"], model
                                )
                            except Exception as exc:
                                grade = {"error": f"{type(exc).__name__}:{exc}"}
                            atomic_json(path, grade)
                        if grade.get("error"):
                            errors.append(grade["error"])
                        else:
                            combined += grade["scores"]
                    scores[kind] = combined
                coverage = (
                    sum(scores["criteria"]) / len(scores["criteria"]) if scores["criteria"] else 0
                )
                support = all(s == 1 for s in scores["claims"])
                accepted = (
                    not errors
                    and not mechanical(fixture["case"], fixture["result"])
                    and coverage >= 0.8
                    and support
                )
                rows.append(
                    {
                        "provider": provider,
                        "id": fixture["id"],
                        "expected_accept": fixture["expected_accept"],
                        "actual_accept": bool(accepted),
                        "matched": not errors and bool(accepted) == fixture["expected_accept"],
                        "judge_errors": len(errors),
                    }
                )
    summary = {
        "scope": "Controlled authored calibration, no natural-report/human accuracy claim",
        "scheduled": len(rows),
        "matched": sum(r["matched"] for r in rows),
        "judge_errors": sum(r["judge_errors"] for r in rows),
        "cases": rows,
        "reservations": {p: usage(output / f"{p}-requests.jsonl") for p in ("deepseek", "qwen")},
    }
    atomic_json(output / "summary.json", summary)
    print(summary)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    asyncio.run(run(p.parse_args().output))
