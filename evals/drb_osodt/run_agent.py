"""Run the DeepAgents multi-agent pipeline on DeepResearch Bench tasks.

Writes ``<output>/drb_<id>/attempt-0001/`` in the layout that ``prepare.py`` exports, so
these reports are scored the same way as the other workflows. Tasks run one at a time.
Failures and timeouts are kept as records with whatever report text was produced.
"""

import argparse
import asyncio
import json
import os
import shutil
import time
import uuid
from pathlib import Path

from app.agent.main_agent import run_deep_agent
from app.config import get_settings
from evals.drb_osodt.checkpoint import open_run, pending_case
from evals.drb_osodt.tasks import select
from evals.worker_supervisor import atomic_json

ROOT = Path(__file__).resolve().parents[2]


async def run_case(row, output, profile, timeout, export_evidence, delivery_repair=False):
    attempt = output / f"drb_{row['id']}" / "attempt-0001"
    attempt.mkdir(parents=True)
    session = f"drb_{row['id']}_{uuid.uuid4().hex[:8]}"
    started = time.monotonic()
    report, error = "", None
    try:
        report = str(
            await asyncio.wait_for(
                run_deep_agent(
                    row["prompt"],
                    session_id=session,
                    user_id="evals",
                    monitor_thread_id=session,
                    budget_profile_override=profile,
                    export_evaluation_evidence=export_evidence,
                    research_delivery_repair=delivery_repair,
                    required_evidence_sources=("web",) if delivery_repair else (),
                ),
                timeout=timeout,
            )
            or ""
        )
    except Exception as exc:  # noqa: BLE001 - a failed case is a result, not a crash
        error = type(exc).__name__
    seconds = round(time.monotonic() - started, 1)
    status = "completed" if report.strip() and error is None else "failed"
    record = {"case_id": f"drb:{row['id']}", "session": session, "seconds": seconds, "error": error}
    # The pipeline's own trace says whether the run ended degraded, e.g. out of research budget.
    trace = ROOT / "app/output/user_evals" / f"session_{session}" / "research_trace.json"
    if trace.is_file():
        shutil.copy2(trace, attempt / "research_trace.json")
        saved = json.loads(trace.read_bytes())
        if status == "completed":
            status = saved["status"]
        record.update(failure_reasons=saved["failure_reasons"], usage=saved["budget"]["usage"])
    evidence = trace.with_name("evaluation_evidence.json")
    if export_evidence and evidence.is_file():
        shutil.copy2(evidence, attempt / evidence.name)
    (attempt / "report.md").write_text(report, "utf-8")
    atomic_json(attempt / "research_result.json", {"status": status})
    atomic_json(attempt / "worker_result.json", record)
    print(json.dumps({**record, "status": status, "characters": len(report)}), flush=True)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--per-language", type=int, default=3)
    parser.add_argument("--ids", type=int, nargs="*", help="Subset of the selected task ids")
    parser.add_argument("--profile", default="deep_report")
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--export-evidence", action="store_true")
    parser.add_argument("--delivery-repair", action="store_true")
    args = parser.parse_args()

    rows = [r for r in select(args.per_language) if not args.ids or r["id"] in args.ids]
    settings = get_settings()
    manifest = {
        "workflow": "deepagents",
        "model": settings.llm_name,
        "profile": args.profile,
        "backend_lock": os.getenv("SEARCH_BACKEND_LOCK"),
        "timeout": args.timeout,
        "export_evidence": args.export_evidence,
        "delivery_repair": args.delivery_repair,
        "limits": settings.research_budget_limits(args.profile).__dict__,
        "tasks": [r["id"] for r in rows],
    }
    open_run(args.output, manifest)
    for row in rows:
        if not pending_case(args.output, row["id"]):
            print(f"drb:{row['id']} reused", flush=True)
            continue
        await run_case(
            row, args.output, args.profile, args.timeout, args.export_evidence, args.delivery_repair
        )


if __name__ == "__main__":
    asyncio.run(main())
