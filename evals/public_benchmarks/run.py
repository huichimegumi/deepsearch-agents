"""Supervised execution of generator-only public task files; no reference reader."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

from app.research.request_budget import usage
from evals.worker_supervisor import atomic_json, supervise

ROOT = Path(__file__).resolve().parents[2]
LOCK = Path(__file__).with_name("suite.lock.json")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def code_hash():
    files = sorted((ROOT / "app").rglob("*.py")) + sorted(Path(__file__).parent.glob("*.py"))
    files += sorted((ROOT / "evals/diagnostics").glob("*.py"))
    files += [ROOT / "evals/scoring_v4.py", ROOT / "evals/worker_supervisor.py", ROOT / "uv.lock"]
    return hashlib.sha256(
        b"".join(p.relative_to(ROOT).as_posix().encode() + p.read_bytes() for p in files)
    ).hexdigest()


def worker(inputs, case_id, workflow, result_path, provider="qwen"):
    from app.research.bounded import execute
    from app.research.sources import SourceCatalog

    task = next(row for row in read(inputs) if row["id"] == case_id)
    config = dict(task["catalog"])
    if config.get("sqlite_path"):
        config["sqlite_path"] = Path(config["sqlite_path"])
    config["allowed_sources"] = tuple(config["allowed_sources"])
    from evals.public_benchmarks.score import model_for

    model = model_for(provider)
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    result = asyncio.run(
        execute(
            task["question"],
            SourceCatalog(**config),
            result_path.parent,
            workflow=workflow,
            timeout_seconds=300,
            model=model,
        )
    )
    result.update(id=case_id, suite=task["suite"])
    atomic_json(result_path, result)


def run(inputs, output, workflow, provider="qwen"):
    tasks = read(inputs)
    budget = read(LOCK)["budget"]
    databases = {
        row["catalog"]["sqlite_path"] for row in tasks if row["catalog"].get("sqlite_path")
    }
    config = {
        "version": "public-v2",
        "workflow": workflow,
        "inputs_sha256": sha(inputs),
        "source_sha256": code_hash(),
        "lock_sha256": sha(LOCK),
        "dependency_lock_sha256": sha(ROOT / "uv.lock"),
        "databases": {str(Path(p).name): sha(p) for p in sorted(databases)},
        "case_ids": [r["id"] for r in tasks],
        "budget": budget,
        "generator": "qwen-flash" if provider == "qwen" else "deepseek-flash non-thinking",
        "provider": provider,
        "web_mode": "live_duckduckgo",
        "device": "cpu",
    }
    output.mkdir(parents=True, exist_ok=True)
    if (output / "manifest.json").exists() and read(output / "manifest.json") != config:
        raise ValueError("execution_resume_mismatch")
    atomic_json(output / "manifest.json", config)
    results_path = output / "results.json"
    results = read(results_path) if results_path.exists() else []
    if [r["id"] for r in results] != config["case_ids"][: len(results)]:
        raise ValueError("execution_checkpoint_order_mismatch")
    for task in tasks[len(results) :]:
        if code_hash() != config["source_sha256"] or sha(inputs) != config["inputs_sha256"]:
            raise ValueError("execution_inputs_changed_during_run")
        attempt = output / hashlib.sha256(task["id"].encode()).hexdigest()[:16] / "attempt-0001"
        spent = sum(r.get("model_reservations", {}).get("reserved_tokens", 0) for r in results)
        if (attempt / "worker_result.json").exists():
            result = read(attempt / "worker_result.json")
        elif attempt.exists():
            result = {"status": "interrupted", "elapsed_seconds": 0}
        elif spent + budget["case_reserved_tokens"] > budget["workflow_batch_reserved_tokens"]:
            result = {"status": "budget_exhausted", "elapsed_seconds": 0}
        else:
            outcome = supervise(
                [
                    sys.executable,
                    "-m",
                    "evals.public_benchmarks.run",
                    "--worker",
                    "--inputs",
                    str(inputs.resolve()),
                    "--case-id",
                    task["id"],
                    "--workflow",
                    workflow,
                    "--provider",
                    provider,
                ],
                cwd=ROOT,
                attempt_dir=attempt,
                timeout_seconds=budget["worker_seconds"],
            )
            result = outcome.result or {}
            result.update(status=outcome.status, elapsed_seconds=outcome.elapsed_seconds)
        result["model_reservations"] = usage(attempt / "model_requests.jsonl")
        if "report" not in result:
            result["report"] = {
                "title": "Research incomplete",
                "answerability": "insufficient_evidence",
                "claims": [],
                "facts": [],
                "limitations": [result["status"]],
            }
        result.update(id=task["id"], suite=task["suite"])
        results.append(result)
        atomic_json(results_path, results)
        print(
            f"{len(results)}/{len(tasks)} {task['suite']}: {result['status']} ({result.get('elapsed_seconds')}s)",
            flush=True,
        )
    return output


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--output", type=Path)
    p.add_argument("--workflow", choices=("simple", "bounded", "adaptive"), default="bounded")
    p.add_argument("--provider", choices=("qwen", "deepseek"), default="qwen")
    p.add_argument("--worker", action="store_true")
    p.add_argument("--case-id")
    p.add_argument("--result-path", type=Path)
    args = p.parse_args()
    if args.worker:
        worker(args.inputs, args.case_id, args.workflow, args.result_path, args.provider)
    else:
        if args.output is None:
            p.error("--output required for supervised execution")
        run(args.inputs, args.output, args.workflow, args.provider)
