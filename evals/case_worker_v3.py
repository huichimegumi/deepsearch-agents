"""Execute one public benchmark case in an isolated, CPU-only process."""

from __future__ import annotations

import argparse
import asyncio
import os
import traceback
from pathlib import Path

from evals.worker_supervisor import atomic_json


def _configure_profile(profile: str) -> None:
    if profile == "deepseek":
        os.environ["LLM_PROVIDER"] = "deepseek"
    elif profile == "qwen":
        os.environ["LLM_PROVIDER"] = "dashscope"
        os.environ["LLM_NAME"] = "qwen-flash"
    else:
        raise ValueError("unknown_model_profile")
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    os.environ["SEARCH_BACKEND_LOCK"] = "duckduckgo"


def _dabstep_prompt(case_id: str) -> str:
    from evals.dabstep.common import default_data_dir, load_jsonl

    selected = load_jsonl(Path(__file__).parent / "dabstep" / "selected_tasks.jsonl")
    task = next((row for row in selected if row["benchmark_id"] == case_id), None)
    if task is None:
        raise ValueError("unknown_dabstep_case")
    context = default_data_dir() / "context"
    manual = (context / "manual.md").read_text(encoding="utf-8")
    readme = (context / "payments-readme.md").read_text(encoding="utf-8")
    return (
        f"{task['question']}\n\nRequired report checklist:\n{task['checklist']}\n\n"
        "The public DABStep source files have been imported into a read-only SQLite database. "
        "Use collect_evidence(source=sql, operation=describe_schema) and read-only SQL queries "
        "to inspect actual data before stating numerical findings. Do not invent a computed fee. "
        "Cite the evidence IDs for quantitative claims; label untested optimization ideas as assumptions.\n\n"
        f"Merchant guide (manual.md):\n{manual}\n\nPayments schema guide:\n{readme}"
    )


async def _execute(case_id: str, session_id: str) -> dict:
    from app.agent.main_agent import run_deep_agent
    from app.config import get_settings
    from evals.benchmark_preflight import DABSTEP_DATABASE
    from evals.hybrid.common import default_data_dir as hybrid_data_dir
    from evals.hybrid.common import load_selected_tasks
    from evals.hybrid.run_smoke import (
        _hybrid_research_limits,
        _load_trace,
        _score_task,
        _task_prompt,
    )

    hybrid = case_id.startswith(("s2sql_", "sql2s_", "parallel_"))
    if hybrid:
        task = next(
            (row for row in load_selected_tasks(hybrid_data_dir()) if row["id"] == case_id), None
        )
        if task is None:
            raise ValueError("unknown_hybrid_case")
        alien = hybrid_data_dir() / "alien"
        database = alien / "alien_template.sqlite"
        os.environ["EVIDENCE_SQLITE_COLUMN_MEANINGS_PATH"] = str(
            alien / "alien_column_meaning_base.json"
        )
        os.environ["EVIDENCE_SQLITE_KNOWLEDGE_PATH"] = str(alien / "alien_kb.jsonl")
        os.environ["REQUIRE_ANALYTICAL_SQL_EVIDENCE"] = "1"
        os.environ["INCLUDE_EXECUTED_SQL_IN_REPORT"] = "1"
        prompt = _task_prompt(task)
    else:
        database = DABSTEP_DATABASE
        prompt = _dabstep_prompt(case_id)
    os.environ["EVIDENCE_SQLITE_PATH"] = str(database)
    limits = _hybrid_research_limits(get_settings(), max_search_queries=2, max_fetched_pages=2)
    answer = await run_deep_agent(
        prompt,
        session_id=session_id,
        user_id="evals",
        monitor_thread_id=session_id,
        budget_profile_override="deep_report",
        research_limits_override=limits,
        sql_entity_recovery_enabled=hybrid,
        export_evaluation_evidence=True,
        required_evidence_sources=("sql", "web") if hybrid else ("sql",),
    )
    trace = _load_trace(session_id)
    if hybrid:
        score = _score_task(task, str(answer or ""), trace, database)
        status = "completed" if answer else "failed"
    else:
        score = {"trace_present": trace is not None, "trace_status": (trace or {}).get("status")}
        status = "completed" if answer else "failed"
    if score.get("trace_status") in {"failed", "degraded"}:
        status = str(score["trace_status"])
    return {"id": case_id, "status": status, "answer": str(answer or ""), "score": score}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--profile", choices=("deepseek", "qwen"), required=True)
    parser.add_argument("--result-path", type=Path, required=True)
    args = parser.parse_args()
    try:
        _configure_profile(args.profile)
        result = asyncio.run(_execute(args.case_id, args.session_id))
    except Exception as exc:  # preserve a terminal result even for unexpected worker failures
        result = {
            "id": args.case_id,
            "status": "error",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
    atomic_json(args.result_path, result)
    return 0 if result["status"] != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
