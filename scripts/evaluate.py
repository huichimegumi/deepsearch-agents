"""Portable entry point for prepare, execute/resume, judge and publish operations."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OFFLINE_TESTS = [
    "tests/test_scoring_v4.py",
    "tests/test_research_trace.py",
    "tests/test_evidence_store.py",
    "tests/test_adaptive_research.py",
    "tests/test_e8_protocol.py",
    "tests/test_e9_protocol.py",
    "tests/test_compact_report.py",
    "tests/test_sql_intent.py",
    "tests/test_query_plan.py",
    "tests/test_e10_attribution.py",
    "tests/test_e10_canary.py",
    "tests/test_metric_selection.py",
    "tests/test_source_report.py",
    "tests/test_bounded_research.py",
    "tests/test_standards_suite.py",
    "tests/test_eval_worker_supervisor.py",
    "tests/test_eval_request_budget.py",
    "tests/test_llm.py",
    "tests/test_eval_v4_recovery.py",
    "tests/test_report_v4.py",
    "tests/test_public_suite.py",
    "tests/test_public_scoring.py",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser(
        "check", help="Run portable offline checks; no model, dataset download or GPU needed"
    )
    check.add_argument("--junit", type=Path)
    commands.add_parser("public-preflight", help="Verify locked E7 public tasks; no model calls")
    public_prepare = commands.add_parser(
        "public-prepare", help="Materialize separate generator/reference files"
    )
    public_prepare.add_argument("--development", action="store_true")
    public_run = commands.add_parser(
        "public-run", help="Supervised shared application execution on public tasks"
    )
    public_run.add_argument("--inputs", type=Path, required=True)
    public_run.add_argument("--output", type=Path, required=True)
    public_run.add_argument("--provider", choices=("qwen", "deepseek"), default="qwen")
    public_run.add_argument(
        "--workflow", choices=("simple", "bounded", "adaptive"), default="bounded"
    )
    public_score = commands.add_parser(
        "public-score", help="Score saved E7 research; invokes model judge"
    )
    public_score.add_argument("--run", type=Path, required=True)
    public_score.add_argument("--inputs", type=Path, required=True)
    public_score.add_argument("--output", type=Path, required=True)
    public_score.add_argument("--provider", choices=("deepseek", "qwen"), default="qwen")
    public_score.add_argument("--audit-subset", action="store_true")
    e8_score = commands.add_parser(
        "e8-score", help="Score E8 saved research with small-batch judging"
    )
    for option in ("run", "inputs", "output"):
        e8_score.add_argument("--" + option, type=Path, required=True)
    commands.add_parser(
        "e9-diagnose", help="Read-only E8 failure attribution and E9 protocol freeze"
    )
    e8_gate = commands.add_parser("e8-gate", help="Check the frozen eight-task development gate")
    for option in ("run", "score", "output"):
        e8_gate.add_argument("--" + option, type=Path, required=True)
    public_report = commands.add_parser("public-report", help="Publish metadata-only E7 report")
    public_report.add_argument("--run", type=Path, action="append", required=True)
    public_report.add_argument("--output", type=Path, required=True)
    commands.add_parser(
        "prepare", help="Download/verify locked sources and rebuild both SQLite snapshots"
    )
    run = commands.add_parser("run", help="Execute or resume; invokes the configured model API")
    run.add_argument("--split", choices=("dev", "holdout"), required=True)
    run.add_argument("--workflow", choices=("simple", "bounded", "adaptive"), default="bounded")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--score", action="store_true")
    for name in ("score", "audit"):
        item = commands.add_parser(
            name,
            help="Judge saved research via model API"
            if name == "score"
            else "Mechanical audit only, no model requests",
        )
        item.add_argument("--run", type=Path, required=True)
    report = commands.add_parser("report")
    report.add_argument("--run", type=Path, action="append", required=True)
    report.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    if args.command == "e9-diagnose":
        return subprocess.call(
            [
                sys.executable,
                "-m",
                "evals.diagnostics.e9",
                "--output",
                "evals/reports/e9-0-attribution.json",
            ],
            cwd=ROOT,
        )
    if args.command in ("e8-score", "e8-gate"):
        module = "score_e8" if args.command == "e8-score" else "gate_e8"
        command = [sys.executable, "-m", "evals.diagnostics." + module]
        for option in (
            ("run", "inputs", "output")
            if args.command == "e8-score"
            else ("run", "score", "output")
        ):
            command += ["--" + option, str(getattr(args, option))]
        return subprocess.call(command, cwd=ROOT)
    if args.command == "public-preflight":
        return subprocess.call([sys.executable, "-m", "evals.public_benchmarks.prepare"], cwd=ROOT)
    if args.command == "public-prepare":
        return subprocess.call(
            [
                sys.executable,
                "-m",
                "evals.public_benchmarks.materialize",
                *(["--development"] if args.development else []),
            ],
            cwd=ROOT,
        )
    if args.command == "public-run":
        return subprocess.call(
            [
                sys.executable,
                "-m",
                "evals.public_benchmarks.run",
                "--inputs",
                str(args.inputs),
                "--output",
                str(args.output),
                "--workflow",
                args.workflow,
                "--provider",
                args.provider,
            ],
            cwd=ROOT,
        )
    if args.command == "public-score":
        return subprocess.call(
            [
                sys.executable,
                "-m",
                "evals.public_benchmarks.score",
                "--run",
                str(args.run),
                "--inputs",
                str(args.inputs),
                "--output",
                str(args.output),
                "--provider",
                args.provider,
                *(["--audit-subset"] if args.audit_subset else []),
            ],
            cwd=ROOT,
        )
    if args.command == "public-report":
        command = [
            sys.executable,
            "-m",
            "evals.public_benchmarks.report",
            "--output",
            str(args.output),
        ]
        for path in args.run:
            command += ["--run", str(path)]
        return subprocess.call(command, cwd=ROOT)
    if args.command == "check":
        command = [sys.executable, "-m", "pytest", *OFFLINE_TESTS, "-q"]
        if args.junit:
            command += ["--junitxml", str(args.junit)]
        return subprocess.call(command, cwd=ROOT)
    if args.command == "prepare":
        return subprocess.call([sys.executable, "-m", "evals.standards.prepare"], cwd=ROOT)
    if args.command == "run":
        command = [
            sys.executable,
            "-m",
            "evals.run_v4",
            "--split",
            args.split,
            "--workflow",
            args.workflow,
            "--output",
            str(args.output),
        ]
        if args.score:
            command.append("--score")
        return subprocess.call(command, cwd=ROOT)
    paths = args.run if isinstance(args.run, list) else [args.run]
    manifest = json.loads((paths[0] / "manifest.json").read_text())
    cases_file = ROOT / "evals/standards" / f"{manifest['split']}.json"
    if args.command == "report":
        from scripts.report_v4 import publish

        publish(paths, cases_file, args.output)
    else:
        cases = json.loads(cases_file.read_text())
        results = json.loads((paths[0] / "results.json").read_text())
        if args.command == "score":
            import asyncio

            from evals.scoring_v4 import score

            print(asyncio.run(score(cases, results, paths[0] / "score-v4")))
        else:
            from evals.scoring_v4 import mechanical

            if [row["id"] for row in cases] != [row["id"] for row in results]:
                raise ValueError("incomplete_or_reordered_results")
            rows = [
                {"id": case["id"], **mechanical(case, result)}
                for case, result in zip(cases, results, strict=True)
            ]
            print(
                json.dumps(
                    {
                        "scheduled": len(cases),
                        "mechanically_clean": sum(not row["issues"] for row in rows),
                        "task_passes": None,
                        "rows": rows,
                    },
                    indent=2,
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
