"""Evaluate end-to-end report samples at the dependency/readiness layer.

Full report execution requires LLM calls and, depending on the sample, live web
search or MySQL. This runner records which samples are executable in the
current environment and which are blocked by dependencies.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import shutil
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

ROUTE_TOOL_HINTS = {
    "network_search": "网络搜索助手 / research_search",
    "database_query": "数据库查询助手 / list_sql_tables / get_table_data / execute_sql_query",
    "knowledge_base": "本地知识库助手 / get_assistant_list / ask_knowledge_base",
    "file_read": "附件读取工具 / read_file_content",
    "memory": "记忆工具",
    "report_generation": "报告生成工具 / generate_markdown / convert_md_to_pdf",
}


class DbErrorCircuitOpen(RuntimeError):
    """Raised when a report eval sample keeps failing database tool calls."""


def _collect_artifacts(session_id: str) -> list[str]:
    output_dir = project_root_path / "output" / "user_evals" / f"session_{session_id}"
    if not output_dir.exists():
        return []

    return [
        str(path.relative_to(project_root_path)).replace("\\", "/")
        for path in sorted(output_dir.rglob("*"))
        if path.is_file() and path.suffix.lower() in {".md", ".pdf"}
    ]


def _artifact_matches_expectation(artifacts: list[str], expectation: str | None) -> bool:
    suffixes = {Path(path).suffix.lower() for path in artifacts}
    if expectation == "pdf_via_markdown":
        return ".pdf" in suffixes
    if expectation == "markdown":
        return ".md" in suffixes and ".pdf" not in suffixes
    return bool(artifacts)


def _reset_eval_session(session_id: str) -> None:
    """Remove stale eval logs and artifacts for a deterministic rerun."""
    log_path = project_root_path / "logs" / f"session_{session_id}.jsonl"
    if log_path.exists():
        log_path.unlink()

    output_dir = project_root_path / "output" / "user_evals" / f"session_{session_id}"
    expected_parent = project_root_path / "output" / "user_evals"
    if output_dir.exists() and output_dir.parent == expected_parent:
        shutil.rmtree(output_dir)


def _db_tool_error_count(session_id: str) -> int:
    log_path = project_root_path / "logs" / f"session_{session_id}.jsonl"
    if not log_path.exists():
        return 0

    count = 0
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        data = event.get("data") or {}
        if event.get("event") != "tool_error":
            continue
        message = str(data.get("message") or "")
        tool_name = str((data.get("data") or {}).get("tool_name") or "")
        if "execute_sql_query" in message or "execute_sql_query" in tool_name:
            count += 1
    return count


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
    artifact_ok = _artifact_matches_expectation(artifacts, artifact_expectation)

    components = {
        "dependency_readiness": 15 if not row.get("blockers") else 0,
        "route_and_source_plan": 20
        if "report_generation" in expected_routes
        and bool(expected_routes & {"network_search", "database_query", "knowledge_base", "file_read"})
        else 0,
        "required_section_spec": 15 if len(required_sections) >= 4 else 0,
        "execution_completed": 25 if row.get("final_result_present") else 0,
        "artifact_created": 25 if artifact_ok else 0,
    }
    total = sum(components.values())
    scored_status = "passed" if total >= 80 else "partial" if total >= 50 else "failed"
    return {
        "score": total,
        "score_components": components,
        "scored_status": scored_status,
        "artifact_expectation_present": bool(artifact_expectation),
        "artifact_expectation_met": artifact_ok,
    }


async def _execute_report_sample(
    sample: dict[str, Any],
    timeout_seconds: int,
    max_db_errors: int,
) -> dict[str, Any]:
    session_id = f"eval_{sample['id']}"
    _reset_eval_session(session_id)
    constrained_task = _task_with_eval_constraints(sample)
    task = asyncio.create_task(
        run_deep_agent(
            constrained_task,
            session_id=session_id,
            user_id="evals",
            monitor_thread_id=session_id,
        ),
    )
    result = None
    try:
        for _ in range(max(1, timeout_seconds)):
            done, _ = await asyncio.wait({task}, timeout=1)
            if done:
                result = task.result()
                break
            if "database_query" in sample.get("expected_route", []):
                db_error_count = _db_tool_error_count(session_id)
                if db_error_count >= max_db_errors:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
                    raise DbErrorCircuitOpen(
                        f"DB tool error circuit opened after {db_error_count} execute_sql_query failures"
                    )
        else:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            raise TimeoutError()
    except Exception:
        if not task.done():
            task.cancel()
        raise

    artifacts = _collect_artifacts(session_id)
    return {
        "final_result_present": bool(result),
        "final_result_preview": str(result)[:500] if result else "",
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "db_error_count": _db_tool_error_count(session_id),
    }


def _task_with_eval_constraints(sample: dict[str, Any]) -> str:
    expected = sample.get("expected_route", [])
    disallowed = sample.get("disallowed_routes", [])
    required_sections = sample.get("required_sections", [])
    artifact = sample.get("artifact_expectation", "")

    expected_text = "、".join(ROUTE_TOOL_HINTS.get(route, route) for route in expected)
    disallowed_text = "、".join(ROUTE_TOOL_HINTS.get(route, route) for route in disallowed)
    section_text = "、".join(required_sections)

    lines = [
        sample["task"],
        "",
        "【评测执行约束】",
        f"本样本期望使用的路线：{expected_text or '无'}。",
    ]
    if disallowed_text:
        lines.append(f"本样本严禁使用以下路线或工具：{disallowed_text}。")
    if "knowledge_base" in disallowed:
        lines.append(
            "不要调用本地知识库助手，不要调用 get_assistant_list，也不要调用 ask_knowledge_base；"
            "如果公开资料或数据库已足够，请直接基于允许的信息源完成。"
        )
    if "network_search" in disallowed:
        lines.append("不要调用网络搜索助手或 research_search。")
    if "database_query" in disallowed:
        lines.append("不要调用数据库查询助手或任何 SQL 工具。")
    if "network_search" in expected:
        lines.append("网络检索请控制在 2 轮以内，每轮最多 5 个查询；优先官方文档、监管机构、云厂商或项目官网来源。")
    if "database_query" in expected:
        lines.append(
            "数据库查询请先确认表结构，再使用不超过 4 条聚合 SQL；涉及日期字段时使用 "
            "NULLIF(CAST(date_col AS CHAR), '0000-00-00') 或 "
            "STR_TO_DATE(NULLIF(CAST(date_col AS CHAR), '0000-00-00'), '%Y-%m-%d') "
            "规避无效日期；不要直接写 date_col != '0000-00-00'。"
        )
    if section_text:
        lines.append(f"最终报告必须包含这些章节：{section_text}。")
    if artifact == "pdf_via_markdown":
        lines.append("最终产物要求：先生成 Markdown，再转换为 PDF。")
    elif artifact == "markdown":
        lines.append("最终产物要求：只生成 Markdown，不要转换 PDF。")
    lines.append("如果因为约束导致无法完成，请明确说明缺失的信息源，不要改用被禁止的工具。")
    return "\n".join(lines)


def run(
    dataset: Path = DEFAULT_DATASET,
    *,
    execute_ready: bool = False,
    timeout_seconds: int = 300,
    max_db_errors: int = 2,
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
                execution = asyncio.run(
                    _execute_report_sample(sample, timeout_seconds, max_db_errors)
                )
                row.update(execution)
                row["status"] = (
                    "passed"
                    if execution["final_result_present"]
                    and _artifact_matches_expectation(
                        execution["artifacts"],
                        sample.get("artifact_expectation"),
                    )
                    else "failed"
                )
            except Exception as exc:  # noqa: BLE001 - report eval should record failures
                row["status"] = "failed"
                row["reason"] = repr(exc)
                db_error_count = _db_tool_error_count(f"eval_{sample['id']}")
                artifacts = _collect_artifacts(f"eval_{sample['id']}")
                row.update(
                    {
                        "final_result_present": False,
                        "final_result_preview": "",
                        "artifact_count": len(artifacts),
                        "artifacts": artifacts,
                        "db_error_count": db_error_count,
                    }
                )
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
    parser.add_argument("--max-db-errors", type=int, default=2)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run(
        args.dataset,
        execute_ready=args.execute_ready,
        timeout_seconds=args.timeout_seconds,
        max_db_errors=args.max_db_errors,
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
