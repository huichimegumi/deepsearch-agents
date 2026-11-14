"""Run the query-budget control or held-out closed-book control without rerunning A/P."""

import argparse
import asyncio
import fcntl
import os
from datetime import date
from pathlib import Path

from evals.drb_osodt.checkpoint import open_run, pending_case
from evals.drb_osodt.run_baseline import run_case
from evals.public_benchmarks.run import read
from evals.retrieval_necessity.run import (
    JUDGE_MODEL,
    attempt_path,
    content_hash,
    limit_searches,
    load_review,
    score,
)
from evals.worker_supervisor import atomic_json


async def generate(rows, output, arm, prompt_date):
    os.environ.update(
        LLM_PROVIDER="dashscope",
        LLM_NAME="qwen-flash",
        OPENAI_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1",
        EVAL_TEMPERATURE="0",
    )
    count = limit_searches(output, 8 * len(rows)) if arm == "A8" else lambda: 0
    for row in rows:
        case = row["id"]
        if not pending_case(output / arm, case):
            continue
        before = count()
        await run_case(
            row,
            output / arm,
            "tavily" if arm == "A8" else None,
            8000,
            current_date=prompt_date,
            include_search_snippets=True,
            query_limit=8,
        )
        atomic_json(
            attempt_path(output, arm, case) / "provider_attempts.json",
            {"attempts": count() - before},
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("generate", "score"))
    parser.add_argument("arm", choices=("A8", "closed"))
    parser.add_argument("review", type=Path)
    parser.add_argument("previous", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    previous = read(args.previous / "manifest.json")
    rows, references = load_review(args.review, holdout=previous["holdout"])
    if args.arm == "closed" and not previous["holdout"]:
        parser.error("Closed-book control is for the holdout")
    if args.output.resolve() == args.previous.resolve():
        parser.error("Control must use a separate output directory")
    for name in ("questions", "references"):
        if previous[
            {"questions": "question_sha256", "references": "reference_sha256"}[name]
        ] != content_hash(args.review / f"{name}.json"):
            raise ValueError("Control revisions differ from the archived question or answer key")
    if previous["judge_model"] != JUDGE_MODEL or not previous["web_refresh"]:
        raise ValueError("Control requires the current archived judge and retrieval configuration")
    pilot = read(args.previous / "pilot_usage.json")
    if not pilot["passed"]:
        raise ValueError("Control requires a verified Tavily pilot")
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        open_run(
            args.output,
            {
                "arm": args.arm,
                "prompt_date": previous["prompt_date"],
                "previous_summary_sha256": content_hash(args.previous / "summary.json"),
                "queries_per_case": 8 if args.arm == "A8" else 0,
                "generation_model": "qwen-flash",
                "judge_model": JUDGE_MODEL,
            },
        )
        atomic_json(args.output / "pilot_usage.json", pilot)
        if args.stage == "generate":
            asyncio.run(
                generate(rows, args.output, args.arm, date.fromisoformat(previous["prompt_date"]))
            )
        else:
            asyncio.run(score(rows, references, args.output, arms=(args.arm,)))


if __name__ == "__main__":
    main()
