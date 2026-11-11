"""Compare two Writers on the same expanded RFC excerpts from development questions."""

import argparse
import asyncio
import json
from pathlib import Path
from time import monotonic

from app.research.rfc_demo import SECTION_REF, candidate_records, expand_sections, run_rfc_qa
from app.research.storage import write_json
from evals.public_benchmarks.score import model_for
from evals.rfc_demo.summarize import read
from evals.rfc_demo.verify import HERE, check_split, sections, sha

MODELS = ("qwen-flash", "qwen3.8-max-0902")


async def run(output):
    lock = read(HERE / "suite.lock.json")
    split = lock["splits"]["development"]
    check_split(HERE, split, "D", sections(lock["corpus_sha256"]))
    tasks = [q for q in read(HERE / "questions.json") if not SECTION_REF.search(q["question"])]
    output.mkdir(parents=True, exist_ok=False)
    packets = {}
    for task in tasks:
        start = monotonic()
        pool, _ = candidate_records(task["question"])
        records = expand_sections(pool)
        if not records:
            raise ValueError(f"empty_evidence:{task['id']}")
        packets[task["id"]] = {
            "records": records,
            "evidence_sha256": sha(
                json.dumps(records, sort_keys=True, ensure_ascii=False).encode()
            ),
            "retrieval_seconds": round(monotonic() - start, 3),
        }
    write_json(output / "packets.json", packets)
    base = model_for("qwen")
    models = {
        MODELS[0]: base,
        MODELS[1]: base.model_copy(
            update={"model_name": MODELS[1], "extra_body": {"enable_thinking": False}}
        ),
    }
    rows = []
    for index, task in enumerate(tasks):
        packet = packets[task["id"]]
        for name in MODELS[:: 1 if index % 2 == 0 else -1]:
            result = await run_rfc_qa(
                task["question"],
                output / task["id"] / name,
                model=models[name],
                prepared_evidence=packet["records"],
                retry_format=False,
            )
            rows.append({"id": task["id"], "model": name, **result})
            write_json(
                output / "results.json",
                {
                    "question_sha256": split["sha256"]["questions.json"],
                    "models": list(MODELS),
                    "rows": rows,
                },
            )
            print(task["id"], name, result["status"], result["error_type"], flush=True)
            if index == 0 and result["error_type"] in {
                "AuthenticationError",
                "PermissionDeniedError",
                "NotFoundError",
                "BadRequestError",
            }:
                raise RuntimeError(f"writer_preflight_failed:{name}:{result['error_type']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    asyncio.run(run(parser.parse_args().output))
