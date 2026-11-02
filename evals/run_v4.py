"""Run the shared application workflow in isolated workers over source-disjoint tasks."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.research.request_budget import usage
from evals.standards.prepare import DATA, LOCK, ROOT, catalog, sha
from evals.worker_supervisor import atomic_json, supervise

TASKS = Path(__file__).parent / "standards"


def source_hash() -> str:
    digest = hashlib.sha256()
    files = [
        *sorted((ROOT / "app").rglob("*.py")),
        Path(__file__),
        Path(__file__).with_name("scoring_v4.py"),
        *sorted(TASKS.glob("*.py")),
        *sorted(TASKS.glob("*.json")),
    ]
    for path in files:
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def verify_sources() -> None:
    lock = json.loads(LOCK.read_text())
    for item in lock["files"]:
        if sha(DATA / item["name"]) != item["sha256"]:
            raise ValueError("public_source_hash_mismatch")
    for split in ("dev", "holdout"):
        private = json.loads((TASKS / f"{split}.json").read_text())
        public = json.loads((TASKS / f"{split}.public.json").read_text())
        if [
            {key: row[key] for key in ("id", "question", "sources", "split")} for row in private
        ] != public:
            raise ValueError("public_task_projection_mismatch")


def worker(split: str, workflow: str, case_id: str, result_path: Path) -> None:
    # This process reads only the public task projection. No oracle or checklist is
    # included in any model message or available through an execution tool.
    public = json.loads((TASKS / f"{split}.public.json").read_text())
    task = next(row for row in public if row["id"] == case_id)
    os.environ["LLM_PROVIDER"] = "deepseek"
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    from app.research.bounded import execute

    result = asyncio.run(
        execute(
            task["question"],
            catalog(split, task["sources"]),
            result_path.parent,
            workflow=workflow,
            timeout_seconds=180,
        )
    )
    result["id"] = case_id
    atomic_json(result_path, result)


def run(split: str, workflow: str, output: Path | None = None) -> Path:
    verify_sources()
    public_file = TASKS / f"{split}.public.json"
    tasks = json.loads(public_file.read_text())
    if output is None:
        output = (
            ROOT
            / "evals/results"
            / f"benchmark_v4_{datetime.now(UTC):%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:8]}"
        )
    output.mkdir(parents=True, exist_ok=True)
    config = {
        "version": "4.0",
        "split": split,
        "workflow": workflow,
        "profile": "deepseek",
        "public_tasks_sha256": sha(public_file),
        "source_sha256": source_hash(),
        "sources_sha256": sha(LOCK),
        "database_sha256": sha(DATA / f"{split}.sqlite"),
        "case_ids": [row["id"] for row in tasks],
        "deadline_seconds": 210,
        "case_model_token_reservation_limit": 180000,
        "batch_token_reservation_limit": 2_000_000,
        "web_mode": "snapshot_only",
        "gpu": "cpu",
    }
    manifest = output / "manifest.json"
    if manifest.exists() and json.loads(manifest.read_text()) != config:
        raise ValueError("execution_resume_mismatch")
    atomic_json(manifest, config)
    results_path = output / "results.json"
    results = json.loads(results_path.read_text()) if results_path.exists() else []
    if [row["id"] for row in results] != config["case_ids"][: len(results)]:
        raise ValueError("execution_checkpoint_order_mismatch")
    for task in tasks[len(results) :]:
        if source_hash() != config["source_sha256"]:
            raise ValueError("execution_source_changed_during_run")
        attempt = output / task["id"] / "attempt-0001"
        spent = sum(row.get("model_reservations", {}).get("reserved_tokens", 0) for row in results)
        if spent + 180000 > config["batch_token_reservation_limit"]:
            result = {"status": "budget_exhausted", "elapsed_seconds": 0}
        elif (attempt / "worker_result.json").exists():
            result = json.loads((attempt / "worker_result.json").read_text())
        else:
            # Preserve an interrupted attempt without silently repeating possibly paid calls.
            if attempt.exists():
                result = {"status": "interrupted", "elapsed_seconds": 0}
            else:
                outcome = supervise(
                    [
                        sys.executable,
                        "-m",
                        "evals.run_v4",
                        "--worker",
                        "--split",
                        split,
                        "--workflow",
                        workflow,
                        "--case-id",
                        task["id"],
                    ],
                    cwd=ROOT,
                    attempt_dir=attempt,
                    timeout_seconds=210,
                )
                result = outcome.result or {"status": outcome.status}
                result["status"] = outcome.status
                result["elapsed_seconds"] = outcome.elapsed_seconds
        result["model_reservations"] = usage(attempt / "model_requests.jsonl")
        if "report" not in result:
            result["report"] = {
                "title": "Research incomplete",
                "answerability": "insufficient_evidence",
                "claims": [],
                "facts": [],
                "limitations": [result["status"]],
            }
        result["id"] = task["id"]
        results.append(result)
        atomic_json(results_path, results)
        print(f"{task['id']}: {result['status']} ({result.get('elapsed_seconds')}s)", flush=True)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("dev", "holdout"), required=True)
    parser.add_argument("--workflow", choices=("bounded", "simple"), default="bounded")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--score", action="store_true")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--case-id")
    parser.add_argument("--result-path", type=Path)
    args = parser.parse_args()
    if args.worker:
        worker(args.split, args.workflow, args.case_id, args.result_path)
        return
    output = run(args.split, args.workflow, args.output)
    print(output)
    if args.score:
        from evals.scoring_v4 import score

        summary = asyncio.run(
            score(
                json.loads((TASKS / f"{args.split}.json").read_text()),
                json.loads((output / "results.json").read_text()),
                output / "score-v4",
            )
        )
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
