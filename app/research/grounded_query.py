"""Experimental shared SQL subtask executor; no evaluator or reference inputs."""

from __future__ import annotations

import asyncio
import sqlite3

from app.research.bounded import _structured
from app.research.grounded_sql import GROUNDED_INSTRUCTION, SQLCandidate
from app.research.request_budget import RequestBudget, usage
from app.research.storage import write_json
from app.research.trace import ResearchTrace


async def query_sql(
    payload,
    relations,
    values,
    output,
    *,
    model,
    max_requests=2,
    reserved_tokens=80000,
    output_tokens=2400,
):
    """Execute a prepared public context once, retrying only empty/engine errors.

    A new output directory is mandatory. Nonempty results receive no correctness
    feedback or retries; execution is never interpreted as task completion.
    Caller owns and closes the read-only metric relations.
    """
    if (
        not 1 <= max_requests <= 2
        or not 1 <= output_tokens <= 3000
        or not 1 <= reserved_tokens <= 80000
    ):
        raise ValueError("invalid_grounded_query_budget")
    output.mkdir(parents=True, exist_ok=False)

    def save(name, value):
        write_json(output / name, value)

    save("input.json", payload)
    budget = RequestBudget(
        output / "requests.jsonl",
        max_requests=max_requests,
        max_reserved_tokens=reserved_tokens,
        finalizing=True,
    )
    summary = {"scope": "sql_subtask_only", "status": "failed", "attempts": []}
    request = dict(payload)
    try:
        with budget.activate(), ResearchTrace(output).activate():
            async with asyncio.timeout(220):
                for index in range(1, max_requests + 1):
                    candidate, _ = await _structured(
                        SQLCandidate,
                        GROUNDED_INSTRUCTION,
                        request,
                        model=model,
                        cap=output_tokens,
                    )
                    save(f"candidate-{index}.json", candidate.model_dump())
                    try:
                        columns, rows = await asyncio.to_thread(
                            relations.execute, candidate.sql, values
                        )
                        result = {"columns": columns, "rows": rows}
                        save(f"result-{index}.json", result)
                        summary["attempts"].append({"status": "executed", "empty": not rows})
                        if rows or index == max_requests:
                            save("final-result.json", result)
                            summary.update(
                                status="executed" if rows else "empty",
                                row_count=len(rows),
                                column_count=len(columns),
                            )
                            break
                        feedback = {
                            "empty_result": True,
                            "instruction": "Verify the query against public definitions without weakening requested filters.",
                        }
                    except (ValueError, sqlite3.Error) as exc:
                        # Engine feedback is private and may contain field names.
                        save(f"error-{index}.json", {"reason": str(exc)})
                        summary["attempts"].append(
                            {"status": "engine_error", "error_class": type(exc).__name__}
                        )
                        feedback = {"error": str(exc)}
                    request["actual_engine_feedback"] = {
                        **feedback,
                        "prior_candidate": candidate.model_dump(),
                    }
    except Exception as exc:
        save("error.json", {"error_class": type(exc).__name__, "reason": str(exc)})
        summary["error_class"] = type(exc).__name__
    summary["reservations"] = usage(budget.path)
    save("summary.json", summary)
    return summary
