from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import re
import shutil
import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterator

from app.agent.main_agent import project_root_path, run_deep_agent
from app.config import get_settings
from app.tools.evidence_tool import _validate_read_only_sql
from evals.hybrid.common import (
    SELECTION_PATH,
    default_data_dir,
    load_json,
    load_selected_tasks,
    verify_files,
)
from evals.runners.common import RESULTS_DIR, now_utc, status_counts, write_json

DEFAULT_OUTPUT = RESULTS_DIR / "hybrid_smoke_eval.json"
PAID_OR_MIXED_BACKENDS = frozenset({"auto", "advanced", "tavily", "perplexity"})
SQL_FENCE_PATTERN = re.compile(r"```sql\s*(.*?)```", re.IGNORECASE | re.DOTALL)
EVIDENCE_CITATION_PATTERN = re.compile(r"\[ev1_[a-z0-9_-]+\]", re.IGNORECASE)


@contextlib.contextmanager
def _temporary_environment(values: dict[str, str]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _load_trace(session_id: str) -> dict[str, Any] | None:
    path = (
        project_root_path
        / "output"
        / "user_evals"
        / f"session_{session_id}"
        / "research_trace.json"
    )
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _reset_session(session_id: str) -> None:
    log_path = project_root_path / "logs" / f"session_{session_id}.jsonl"
    if log_path.is_file():
        log_path.unlink()
    output_dir = project_root_path / "output" / "user_evals" / f"session_{session_id}"
    expected_parent = project_root_path / "output" / "user_evals"
    if output_dir.exists() and output_dir.parent == expected_parent:
        shutil.rmtree(output_dir)


def _task_prompt(task: dict[str, Any]) -> str:
    hint = str(task.get("hint") or "").strip()
    return f"""{task["final_question"]}

Benchmark hint: {hint or "None"}
Database: {task["db"]}

Evaluation constraints:
- The database is mounted read-only. Before writing SQL, use
  collect_evidence(source=sql, operation=describe_schema). Use operation=sample_table with an
  exact table_name only when a bounded three-row value preview is needed.
- Use the network researcher for the public-web leg and require fetched Web Evidence; a search
  snippet or CANDIDATE_ONLY result is not evidence.
- Keep the answer concise and cite exact SQL and Web evidence IDs.
- If the requested output is a SQL result, include the final read-only query in one ```sql``` block.
- Return the answer directly in chat without creating file artifacts.
""".strip()


def _normalize_text(value: Any) -> str:
    text = (
        json.dumps(value, ensure_ascii=False, sort_keys=True)
        if not isinstance(value, str)
        else value
    )
    text = EVIDENCE_CITATION_PATTERN.sub("", text)
    return " ".join(text.casefold().split()).strip(" .,:;\n\t")


def _strict_text_match(answer: str, gold: Any) -> bool:
    normalized_answer = _normalize_text(answer)
    normalized_gold = _normalize_text(gold)
    return bool(normalized_gold and normalized_gold in normalized_answer)


def _query_rows(database_path: Path, query: str) -> tuple[tuple[str, ...], list[tuple[Any, ...]]]:
    cleaned = _validate_read_only_sql(query)
    with sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only = ON")
        cursor = connection.execute(cleaned)
        columns = tuple(item[0].casefold() for item in cursor.description or ())
        rows = cursor.fetchall()
    return columns, rows


def _canonical_rows(columns: tuple[str, ...], rows: list[tuple[Any, ...]]) -> list[str]:
    return sorted(
        json.dumps(
            dict(zip(columns, row, strict=True)), ensure_ascii=False, sort_keys=True, default=str
        )
        for row in rows
    )


def _sql_result_match(answer: str, gold_sql: str, database_path: Path) -> bool:
    match = SQL_FENCE_PATTERN.search(answer)
    if not match:
        return False
    try:
        predicted_columns, predicted_rows = _query_rows(database_path, match.group(1))
        gold_columns, gold_rows = _query_rows(database_path, gold_sql)
    except (sqlite3.Error, ValueError):
        return False
    return set(predicted_columns) == set(gold_columns) and _canonical_rows(
        predicted_columns, predicted_rows
    ) == _canonical_rows(gold_columns, gold_rows)


def _score_task(
    task: dict[str, Any],
    answer: str,
    trace: dict[str, Any] | None,
    database_path: Path,
) -> dict[str, Any]:
    metrics = (trace or {}).get("metrics") or {}
    evidence_by_source = metrics.get("evidence_by_source") or {}
    if task["hybrid_type"] == "search_to_sql":
        strict_correct = _sql_result_match(answer, task["sql"], database_path)
        strict_metric = "sqlite_execution_match"
    else:
        strict_correct = _strict_text_match(answer, task["final_answer"])
        strict_metric = "normalized_gold_containment"
    return {
        "strict_correct": strict_correct,
        "strict_metric": strict_metric,
        "trace_present": trace is not None,
        "trace_status": (trace or {}).get("status"),
        "citation_valid": metrics.get("report_citation_valid"),
        "sql_evidence_records": int(evidence_by_source.get("sql", 0)),
        "web_evidence_records": int(evidence_by_source.get("web", 0)),
        "cross_source_evidence": bool(
            evidence_by_source.get("sql", 0) and evidence_by_source.get("web", 0)
        ),
        "search_queries": int(metrics.get("search_queries", 0)),
        "fetched_pages": int(metrics.get("fetched_pages", 0)),
        "validated_claims": int(metrics.get("validated_claims", 0)),
        "rejected_claims": int(metrics.get("rejected_claims", 0)),
        "elapsed_ms": (trace or {}).get("elapsed_ms"),
    }


async def _execute_task(
    task: dict[str, Any],
    *,
    database_path: Path,
    search_backend: str,
    max_search_queries: int,
    max_fetched_pages: int,
) -> dict[str, Any]:
    session_id = f"hybrid_smoke_{task['id']}"
    _reset_session(session_id)
    settings = get_settings()
    limits = replace(
        settings.research_budget_limits("standard"),
        max_search_queries=max_search_queries,
        max_fetched_pages=max_fetched_pages,
        max_research_rounds=1,
        max_llm_calls=16,
    )
    with _temporary_environment(
        {
            "EVIDENCE_SQLITE_PATH": str(database_path.resolve()),
            "SEARCH_BACKEND_LOCK": search_backend,
        }
    ):
        answer = await run_deep_agent(
            _task_prompt(task),
            session_id=session_id,
            user_id="evals",
            monitor_thread_id=session_id,
            budget_profile_override="standard",
            research_limits_override=limits,
        )
    trace = _load_trace(session_id)
    scored = _score_task(task, str(answer or ""), trace, database_path)
    status = "passed" if scored["strict_correct"] else "completed_incorrect"
    if not answer:
        status = "failed"
    elif scored["trace_status"] in {"failed", "degraded"}:
        status = str(scored["trace_status"])
    return {
        "id": task["id"],
        "hybrid_type": task["hybrid_type"],
        "status": status,
        **scored,
    }


def _validate_paid_search(search_backend: str, allow_paid_search: bool) -> None:
    if search_backend in PAID_OR_MIXED_BACKENDS and not allow_paid_search:
        raise ValueError(
            f"search backend '{search_backend}' may consume paid credits; "
            "pass --allow-paid-search explicitly"
        )


def run(
    *,
    data_dir: Path,
    execute: bool,
    limit: int,
    search_backend: str,
    allow_paid_search: bool,
) -> dict[str, Any]:
    errors = verify_files(data_dir)
    if errors:
        raise RuntimeError("; ".join(errors))
    _validate_paid_search(search_backend, allow_paid_search)
    selection = load_json(SELECTION_PATH)
    tasks = load_selected_tasks(data_dir)[: max(0, min(limit, len(selection["tasks"])))]
    max_search_queries = int(selection["max_search_queries_per_task"])
    max_fetched_pages = int(selection["max_fetched_pages_per_task"])
    database_path = data_dir / "alien" / "alien_template.sqlite"

    results: list[dict[str, Any]] = []
    if execute:
        for task in tasks:
            try:
                results.append(
                    asyncio.run(
                        _execute_task(
                            task,
                            database_path=database_path,
                            search_backend=search_backend,
                            max_search_queries=max_search_queries,
                            max_fetched_pages=max_fetched_pages,
                        )
                    )
                )
            except Exception as exc:  # noqa: BLE001 - retain failures without leaking task text
                results.append(
                    {
                        "id": task["id"],
                        "hybrid_type": task["hybrid_type"],
                        "status": "failed",
                        "reason": f"{exc.__class__.__name__}: {exc}",
                    }
                )

    total_search_queries = sum(int(row.get("search_queries", 0)) for row in results)
    total_fetched_pages = sum(int(row.get("fetched_pages", 0)) for row in results)
    return {
        "name": selection["name"],
        "generated_at": now_utc(),
        "execution_enabled": execute,
        "statistical_claim": selection["statistical_claim"],
        "selected_task_ids": [task["id"] for task in tasks],
        "selected_modes": [task["hybrid_type"] for task in tasks],
        "database": "alien",
        "search_budget": {
            "backend": search_backend,
            "paid_search_authorized": allow_paid_search,
            "max_queries_per_task": max_search_queries,
            "max_fetched_pages_per_task": max_fetched_pages,
            "max_queries_this_run": len(tasks) * max_search_queries,
            "max_fetched_pages_this_run": len(tasks) * max_fetched_pages,
        },
        "status_counts": status_counts(results),
        "strict_correct": sum(bool(row.get("strict_correct")) for row in results),
        "cross_source_evidence": sum(bool(row.get("cross_source_evidence")) for row in results),
        "citation_valid": sum(row.get("citation_valid") is True for row in results),
        "total_search_queries": total_search_queries,
        "total_fetched_pages": total_fetched_pages,
        "search_budget_compliant": bool(
            total_search_queries <= len(tasks) * max_search_queries
            and total_fetched_pages <= len(tasks) * max_fetched_pages
            and all(
                int(row.get("search_queries", 0)) <= max_search_queries
                and int(row.get("fetched_pages", 0)) <= max_fetched_pages
                for row in results
            )
        ),
        "results": results,
        "privacy_note": "Questions, gold answers, SQL, and model outputs are decrypted in memory only.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the 3-task HybridDeepResearch smoke subset.")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--limit", type=int, choices=range(1, 4), default=3)
    parser.add_argument(
        "--search-backend",
        choices=("duckduckgo", "searxng", "tavily", "perplexity", "auto", "advanced"),
        default="duckduckgo",
    )
    parser.add_argument("--allow-paid-search", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        report = run(
            data_dir=args.data_dir,
            execute=args.execute,
            limit=args.limit,
            search_backend=args.search_backend,
            allow_paid_search=args.allow_paid_search,
        )
    except (RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    write_json(args.output, report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Selected tasks: {len(report['selected_task_ids'])}")
        print(f"Modes: {', '.join(report['selected_modes'])}")
        print(f"Search budget: {report['search_budget']}")
        print(f"Status counts: {report['status_counts']}")
        print(f"Strict correct: {report['strict_correct']}")
        print(f"Wrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
