"""Run one paired comparison on development questions only."""

import argparse
import asyncio
import json
from pathlib import Path
from time import monotonic

from app.rag.embeddings import rerank_with_status
from app.research.rfc_demo import SECTION_REF, candidate_records, run_rfc_qa
from app.research.storage import write_json
from evals.public_benchmarks.score import model_for
from evals.rfc_demo.verify import HERE, sha

ARMS = ("hybrid", "rerank")


def prepare(question):
    start = monotonic()
    pool, limit = candidate_records(question)
    recall_seconds = monotonic() - start
    if not pool or limit != 8:
        raise ValueError("invalid_comparison_pool")
    start = monotonic()
    result = rerank_with_status(question, [r["content"] for r in pool])
    rerank_seconds = monotonic() - start
    if not result.applied:
        raise RuntimeError(f"reranker_not_applied:{result.error_type}")
    order = sorted(range(len(pool)), key=lambda i: -result.scores[i])
    return {
        "pool": pool,
        "reranker": result.model,
        "scores": result.scores,
        "selected": {"hybrid": list(range(min(limit, len(pool)))), "rerank": order[:limit]},
        "recall_seconds": recall_seconds,
        "rerank_seconds": rerank_seconds,
    }


async def run(output):
    raw = (HERE / "questions.json").read_bytes()
    lock = json.loads((HERE / "suite.lock.json").read_bytes())["splits"]["development"]
    if sha(raw) != lock["sha256"]["questions.json"]:
        raise ValueError("development_questions_changed")
    tasks = [q for q in json.loads(raw) if not SECTION_REF.search(q["question"])]
    if len(tasks) != 9 or {q["id"] for q in tasks} != {f"D{i:02d}" for i in range(1, 11) if i != 2}:
        raise ValueError("unexpected_paired_questions")
    output.mkdir(parents=True, exist_ok=False)
    packets = []
    # Complete CPU preflight before constructing the writer or sending anything.
    for task in tasks:
        packet = prepare(task["question"])
        write_json(output / task["id"] / "pool.json", packet)
        packets.append(packet)
        print(task["id"], "prepared", len(packet["pool"]), flush=True)
    model = model_for("qwen")
    rows = []
    for index, (task, packet) in enumerate(zip(tasks, packets, strict=True)):
        for arm in ARMS[:: 1 if index % 2 == 0 else -1]:
            evidence = [packet["pool"][i] for i in packet["selected"][arm]]
            result = await run_rfc_qa(
                task["question"], output / task["id"] / arm, model=model, prepared_evidence=evidence
            )
            rows.append(
                {
                    "id": task["id"],
                    "arm": arm,
                    **result,
                    "retrieval_seconds": round(
                        packet["recall_seconds"]
                        + (packet["rerank_seconds"] if arm == "rerank" else 0),
                        3,
                    ),
                }
            )
            write_json(output / "results.json", {"question_sha256": sha(raw), "rows": rows})
            print(task["id"], arm, result["status"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    asyncio.run(run(args.output))
