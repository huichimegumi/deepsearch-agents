"""Replay archived public web evidence through the single-round Writer."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from time import monotonic

from app.agent.llm import get_model
from evals.drb_osodt.checkpoint import open_run, pending_case
from evals.drb_osodt.run_baseline import WRITER
from evals.drb_osodt.tasks import select
from evals.public_benchmarks.run import read
from evals.worker_supervisor import atomic_json


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def prepare(archive):
    ids = {int(q) for q in read(archive / "score/summary.json")["tasks"]}
    tasks = [task for task in select(8) if task["id"] in ids]
    if len(tasks) != len(ids) or len(ids) != 15:
        raise ValueError("Expected the frozen 15-task comparison")
    packets = {}
    for arm in ("C", "D"):
        cases = []
        for task in tasks:
            case = archive / arm / f"drb_{task['id']}" / "attempt-0001"
            evidence = read(case / "evaluation_evidence.json")["records"]
            sources = []
            for record in evidence:
                if record["source"] != "web":
                    continue
                text = record["content"]
                url = record["locator"]
                meta = record["metadata"]
                if (
                    not isinstance(text, str)
                    or not text.strip()
                    or meta["content_chars"] != len(text)
                    or not url.startswith(("https://", "http://"))
                ):
                    raise ValueError(f"Invalid archived web evidence: {arm}/{task['id']}")
                sources.append(
                    {
                        "n": len(sources) + 1,
                        "title": meta.get("title") or "",
                        "url": url,
                        "text": text,
                    }
                )
            cases.append(
                {
                    "id": task["id"],
                    "task": task["prompt"],
                    "sources": sources,
                    "excluded_non_web": len(evidence) - len(sources),
                }
            )
        packets[f"X-{arm}"] = cases
    return packets


async def run(archive, output, *, closed_book=False):
    packets = prepare(archive)
    if closed_book:
        packets = {
            "Closed": [{**item, "sources": [], "excluded_non_web": 0} for item in packets["X-C"]]
        }
    manifest = {
        "model": "qwen-flash",
        "temperature": 0,
        "max_tokens": 8000,
        "prompt_sha256": digest(WRITER),
        "packets_sha256": digest(packets),
        "tasks": [item["id"] for item in next(iter(packets.values()))],
        "search_requests": 0,
    }
    open_run(output, manifest)
    atomic_json(output / "packets.json", packets)
    model = get_model()
    if model.model_name != manifest["model"]:
        raise ValueError("Crossover requires qwen-flash")
    writer = model.bind(temperature=0, max_tokens=8000)
    for pairs in zip(*packets.values(), strict=True):
        for arm, packet in zip(packets, pairs, strict=True):
            case_id = packet["id"]
            if not pending_case(output / arm, case_id):
                continue
            attempt = output / arm / f"drb_{case_id}" / "attempt-0001"
            attempt.mkdir(parents=True)
            payload = {key: packet[key] for key in ("task", "sources")}
            start = monotonic()
            result = await writer.ainvoke(
                [
                    {"role": "system", "content": WRITER},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ]
            )
            report = str(result.content).strip()
            if not report:
                raise ValueError(f"Empty writer response: {arm}/{case_id}")
            sources = packet["sources"]
            body_chars = len(report)
            if sources:
                report += "\n\n## Sources\n" + "\n".join(
                    f"[{source['n']}] {source['title']} {source['url']}" for source in sources
                )
            (attempt / "report.md").write_text(report, encoding="utf-8")
            atomic_json(attempt / "sources.json", sources)
            status = (
                "truncated"
                if result.response_metadata.get("finish_reason") == "length"
                else "completed"
            )
            atomic_json(attempt / "research_result.json", {"status": status})
            atomic_json(
                attempt / "worker_result.json",
                {
                    "case_id": f"drb:{case_id}",
                    "seconds": round(monotonic() - start, 2),
                    "usage": [result.usage_metadata],
                    "sources": len(sources),
                    "body_chars": body_chars,
                    "search_requests": 0,
                    "input_sha256": digest(payload),
                },
            )
            print(arm, case_id, status, len(sources), body_chars, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--closed-book", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.archive, args.output, closed_book=args.closed_book))
