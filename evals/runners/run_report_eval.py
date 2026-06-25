"""Evaluate end-to-end report samples at the dependency/readiness layer.

Full report execution requires LLM calls and, depending on the sample, live web
search or MySQL. This runner records which samples are executable in the
current environment and which are blocked by dependencies.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from mysql.connector import connect

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.agent.main_agent import project_root_path, run_deep_agent
from app.tools.db_tools import get_db_config
from evals.runners.common import DATASET_DIR, RESULTS_DIR, load_jsonl, now_utc, status_counts, write_json


DEFAULT_DATASET = DATASET_DIR / "end_to_end_report_zh.jsonl"


def _llm_available() -> tuple[bool, str]:
    try:
        settings = get_settings()
        settings.validate_llm()
        return True, ""
    except Exception as exc:  # noqa: BLE001 - record dependency failures
        return False, repr(exc)


def _db_available() -> tuple[bool, str]:
    try:
        with connect(**get_db_config()) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, repr(exc)


def _score_report_row(row: dict[str, Any]) -> dict[str, Any]:
    expected_routes = set(row.get("expected_route", []))
    required_sections = row.get("required_sections", [])
    artifact_expectation = row.get("artifact_expectation")
    artifacts = row.get("artifacts", [])

    components = {
        "dependency_readiness": 15 if not row.get("blockers") else 0,
        "route_and_source_plan": 20
        if "report_generation" in expected_routes
        and bool(expected_routes & {"network_search", "database_query", "knowledge_base", "file_read"})
        else 0,
        "required_section_spec": 15 if len(required_sections) >= 4 else 0,
        "execution_completed": 25 if row.get("final_result_present") else 0,
        "artifact_created": 25 if artifacts else 0,
    }
    total = sum(components.values())
    scored_status = "passed" if total >= 80 else "partial" if total >= 50 else "failed"
    return {
        "score": total,
        "score_components": components,
        "scored_status": scored_status,
        "artifact_expectation_present": bool(artifact_expectation),
    }


async def _execute_report_sample(sample: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    session_id = f"eval_{sample['id']}"
    result = await asyncio.wait_for(
        run_deep_agent(
            sample["task"],
            session_id=session_id,
            user_id="evals",
            monitor_thread_id=session_id,
        ),
        timeout=timeout_seconds,
    )
    output_dir = project_root_path / "output" / "user_evals" / f"session_{session_id}"
    artifacts = []
    if output_dir.exists():
        artifacts = [
            str(path.relative_to(project_root_path)).replace("\\", "/")
            for path in output_dir.iterdir()
            if path.is_file()
        ]
    return {
        "final_result_present": bool(result),
        "final_result_preview": str(result)[:500] if result else "",
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }


def run(
    dataset: Path = DEFAULT_DATASET,
    *,
    execute_ready: bool = False,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    samples = load_jsonl(dataset)
    llm_ok, llm_reason = _llm_available()
    db_ok, db_reason = _db_available()
    results: list[dict[str, Any]] = []

    for sample in samples:
        blockers: list[str] = []
        routes = set(sample["expected_route"])
        if not llm_ok:
            blockers.append(f"LLM unavailable: {llm_reason}")
        if "database_query" in routes and not db_ok:
            blockers.append(f"MySQL unavailable: {db_reason}")

        row = {
            "id": sample["id"],
            "status": "ready" if not blockers else "blocked",
            "expected_route": sample["expected_route"],
            "artifact_expectation": sample.get("artifact_expectation"),
            "required_sections": sample.get("required_sections", []),
            "blockers": blockers,
        }
        if execute_ready and not blockers:
            try:
                execution = asyncio.run(_execute_report_sample(sample, timeout_seconds))
                row.update(execution)
                row["status"] = "passed" if execution["final_result_present"] else "failed"
            except Exception as exc:  # noqa: BLE001 - report eval should record failures
                row["status"] = "failed"
                row["reason"] = repr(exc)
        row.update(_score_report_row(row))
        results.append(row)

    counts = status_counts(results)
    score_values = [row["score"] for row in results]
    scored_counts = status_counts(
        [{"status": row["scored_status"]} for row in results]
    )
    return {
        "name": "end_to_end_report_zh",
        "dataset": str(dataset),
        "generated_at": now_utc(),
        "total": len(samples),
        "status_counts": counts,
        "scored_status_counts": scored_counts,
        "average_score": sum(score_values) / len(score_values) if score_values else 0.0,
        "ready_rate": counts.get("ready", 0) / len(samples) if samples else 0.0,
        "pass_rate": counts.get("passed", 0) / len(samples) if samples else 0.0,
        "results": results,
        "note": (
            "Without --execute-ready this runner records execution readiness. "
            "With --execute-ready it runs samples whose dependencies are available."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run report eval readiness checks.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=RESULTS_DIR / "report_eval.json")
    parser.add_argument("--execute-ready", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run(
        args.dataset,
        execute_ready=args.execute_ready,
        timeout_seconds=args.timeout_seconds,
    )
    write_json(args.output, report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Dataset: {report['dataset']}")
        print(f"Total: {report['total']}")
        print(f"Status counts: {report['status_counts']}")
        print(f"Ready rate: {report['ready_rate']:.1%}")
        print(f"Wrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
