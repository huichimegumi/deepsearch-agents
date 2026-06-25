"""Run all first-phase evals and write a summary report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.runners.common import RESULTS_DIR, now_utc, write_json, write_markdown
from evals.runners.run_db_eval import run as run_db
from evals.runners.run_report_eval import run as run_report
from evals.runners.run_rag_local_eval import run as run_rag_local
from evals.runners.run_routing_eval import DEFAULT_DATASET as ROUTING_DATASET
from evals.runners.run_routing_eval import run as run_routing
from evals.runners.run_web_eval import run as run_web


def _routing_as_report() -> dict[str, Any]:
    report = run_routing(ROUTING_DATASET)
    failures = report["failures"]
    return {
        "name": "routing_boundary_zh",
        "dataset": report["dataset"],
        "generated_at": now_utc(),
        "total": report["total"],
        "status_counts": {
            "passed": report["passed"],
            "failed": len(failures),
        },
        "pass_rate": report["route_accuracy"],
        "disallowed_route_violations": report["disallowed_route_violations"],
        "results": [
            {"id": item["id"], "status": "failed", **item} for item in failures
        ],
    }


def _summary_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# First-Phase Eval Results",
        "",
        f"Generated at: `{report['generated_at']}`",
        "",
        "| Eval | Total | Status Counts | Rate |",
        "| --- | ---: | --- | ---: |",
    ]
    for name, item in report["evals"].items():
        rate = item.get("pass_rate", item.get("ready_rate", 0.0))
        if "average_score" in item:
            rate_text = f"{item['average_score']:.1f}/100"
        else:
            rate_text = f"{rate:.1%}"
        lines.append(
            f"| {name} | {item['total']} | `{json.dumps(item['status_counts'], ensure_ascii=False)}` | {rate_text} |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- `web_research_zh` is scored as a live search smoke eval: a sample passes when the search service returns at least one result.",
            "- `db_query_zh` executes gold SQL directly against configured MySQL; blocked means the database was not reachable.",
            "- `routing_boundary_zh` uses the deterministic routing baseline in `run_routing_eval.py`.",
            "- `end_to_end_report_zh` records dependency readiness by default; with `--execute-reports`, ready samples are executed through `run_deep_agent`.",
        ]
    )
    return "\n".join(lines) + "\n"


def run_all(
    *,
    include_web: bool = True,
    include_rag: bool = True,
    execute_reports: bool = False,
) -> dict[str, Any]:
    evals: dict[str, Any] = {
        "routing_boundary_zh": _routing_as_report(),
        "db_query_zh": run_db(),
        "end_to_end_report_zh": run_report(execute_ready=execute_reports),
    }
    if include_rag:
        evals["rag_local_zh"] = run_rag_local()
    else:
        evals["rag_local_zh"] = {
            "name": "rag_local_zh",
            "generated_at": now_utc(),
            "total": 20,
            "status_counts": {"skipped": 20},
            "pass_rate": 0.0,
            "results": [],
        }
    if include_web:
        evals["web_research_zh"] = run_web()
    else:
        evals["web_research_zh"] = {
            "name": "web_research_zh",
            "generated_at": now_utc(),
            "total": 20,
            "status_counts": {"skipped": 20},
            "pass_rate": 0.0,
            "results": [],
        }
    return {"generated_at": now_utc(), "evals": evals}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all first-phase evals.")
    parser.add_argument("--skip-web", action="store_true")
    parser.add_argument("--skip-rag", action="store_true")
    parser.add_argument("--execute-reports", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    args = parser.parse_args()

    report = run_all(
        include_web=not args.skip_web,
        include_rag=not args.skip_rag,
        execute_reports=args.execute_reports,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "first_phase_eval_results.json", report)
    write_markdown(args.output_dir / "first_phase_eval_results.md", _summary_markdown(report))
    print(f"Wrote: {args.output_dir / 'first_phase_eval_results.json'}")
    print(f"Wrote: {args.output_dir / 'first_phase_eval_results.md'}")
    for name, item in report["evals"].items():
        rate = item.get("pass_rate", item.get("ready_rate", 0.0))
        print(f"{name}: total={item['total']} counts={item['status_counts']} rate={rate:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
