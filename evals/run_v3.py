"""Run a frozen evaluation suite with hard per-case process deadlines."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from evals.benchmark_preflight import ROOT, SUITE, preflight
from evals.runners.experiment import build_manifest, file_sha256
from evals.worker_supervisor import atomic_json, supervise

RESULTS = ROOT / "evals" / "results"


def _cases() -> list[str]:
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    result = [case_id for source in suite["source_sets"] for case_id in source["case_ids"]]
    if len(result) != len(set(result)):
        raise ValueError("duplicate_suite_case_id")
    return result


def _write_rows(run_dir: Path, rows: list[dict]) -> None:
    path = run_dir / "results.jsonl"
    temporary = path.with_name("results.jsonl.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
        )
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
    atomic_json(
        run_dir / "summary.json",
        {
            "scheduled": len(json.loads((run_dir / "manifest.json").read_text())["case_ids"]),
            "terminal": len(rows),
            "statuses": dict(Counter(row["status"] for row in rows)),
            "total_elapsed_seconds": round(sum(row["elapsed_seconds"] for row in rows), 3),
        },
    )


def run(
    *,
    case_ids: list[str] | None = None,
    profile: str = "deepseek",
    workflow: str = "agent",
    timeout_seconds: float = 330,
    cleanup_seconds: float = 5,
    resume_run: Path | None = None,
) -> Path:
    if profile not in {"deepseek", "qwen"}:
        raise ValueError("unknown_model_profile")
    if workflow not in {"agent", "simple_sql"}:
        raise ValueError("unknown_workflow")
    if timeout_seconds <= 0 or cleanup_seconds < 0:
        raise ValueError("invalid_deadline")
    available = _cases()
    selected = case_ids if case_ids is not None else available
    if not selected:
        raise ValueError("empty_case_selection")
    if len(selected) != len(set(selected)) or not set(selected) <= set(available):
        raise ValueError("invalid_case_selection")
    if workflow == "simple_sql" and any(
        not item.startswith("dabstep_research_") for item in selected
    ):
        raise ValueError("simple_sql_requires_dabstep_cases")
    ready = preflight()
    if not ready["ready"]:
        raise RuntimeError("benchmark_preflight_failed: " + ", ".join(ready["problems"]))

    if resume_run:
        run_dir = resume_run.resolve()
        if not run_dir.is_relative_to(RESULTS.resolve()):
            raise ValueError("resume_path_outside_results")
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        if (
            manifest["case_ids"] != selected
            or manifest["profile"] != profile
            or manifest.get("workflow", "agent") != workflow
            or manifest["suite_sha256"] != file_sha256(SUITE)
            or manifest["timeout_seconds"] != timeout_seconds
            or manifest["cleanup_seconds"] != cleanup_seconds
        ):
            raise ValueError("resume_manifest_mismatch")
    else:
        run_id = f"benchmark_v3_{datetime.now(UTC):%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:8]}"
        run_dir = RESULTS / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        manifest = build_manifest(
            SUITE,
            {
                "profile": profile,
                "workflow": workflow,
                "timeout_seconds": timeout_seconds,
                "cleanup_seconds": cleanup_seconds,
                "search_backend": "duckduckgo",
                "paid_search": False,
                "gpu": "cpu",
                "temperature": 0,
                "simple_writer_max_tokens": 8000 if workflow == "simple_sql" else None,
            },
        )
        manifest.update(
            {
                "case_ids": selected,
                "suite_sha256": file_sha256(SUITE),
                "profile": profile,
                "workflow": workflow,
                "timeout_seconds": timeout_seconds,
                "cleanup_seconds": cleanup_seconds,
                "preflight_input_sha256": ready["input_sha256"],
            }
        )
        atomic_json(run_dir / "manifest.json", manifest)

    rows_path = run_dir / "results.jsonl"
    rows = (
        [json.loads(line) for line in rows_path.read_text().splitlines()]
        if rows_path.exists()
        else []
    )
    done_ids = {row["id"] for row in rows}
    if len(done_ids) != len(rows) or not done_ids <= set(selected):
        raise ValueError("invalid_existing_results")
    for case_id in selected:
        if case_id in done_ids:
            continue
        case_dir = run_dir / "cases" / case_id
        attempt_number = 1
        while (case_dir / f"attempt-{attempt_number:04d}").exists():
            attempt_number += 1
        attempt = case_dir / f"attempt-{attempt_number:04d}"
        outcome = supervise(
            [
                sys.executable,
                "-m",
                "evals.case_worker_v3",
                "--case-id",
                case_id,
                "--profile",
                profile,
                "--workflow",
                workflow,
                "--session-id",
                f"{run_dir.name}_{case_id}_a{attempt_number}",
            ],
            cwd=ROOT,
            attempt_dir=attempt,
            timeout_seconds=timeout_seconds,
            cleanup_seconds=cleanup_seconds,
        )
        row = {
            "id": case_id,
            "status": outcome.status,
            "elapsed_seconds": outcome.elapsed_seconds,
            "exit_code": outcome.exit_code,
            "forced_termination": outcome.forced_termination,
            "attempt": attempt.relative_to(run_dir).as_posix(),
            "score": (outcome.result or {}).get("score"),
            "error_type": (outcome.result or {}).get("error_type"),
        }
        rows.append(row)
        _write_rows(run_dir, rows)
        print(f"{case_id}: {outcome.status} ({outcome.elapsed_seconds}s)", flush=True)
    return run_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--profile", choices=("deepseek", "qwen"), default="deepseek")
    parser.add_argument("--workflow", choices=("agent", "simple_sql"), default="agent")
    parser.add_argument("--timeout-seconds", type=float, default=330)
    parser.add_argument("--cleanup-seconds", type=float, default=5)
    parser.add_argument("--resume-run", type=Path)
    args = parser.parse_args()
    try:
        output = run(**vars(args))
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
