"""Measure the exact source preview path on the public development split."""

import argparse
import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from app.research import rfc_demo
from evals.rfc_demo.verify import HERE, check_split, norm, sections


def hits(records, anchors):
    return sum(
        any(
            record["locator"].endswith(f"rfc{rfc}.html#section-{section}")
            and text in norm(record["content"])
            for record in records
        )
        for rfc, section, text in anchors
    )


async def run(output):
    lock = json.loads((HERE / "suite.lock.json").read_bytes())
    check_split(HERE, lock["splits"]["development"], "D", sections(lock["corpus_sha256"]))
    questions = json.loads((HERE / "questions.json").read_bytes())
    refs = {r["id"]: r for r in json.loads((HERE / "references.json").read_bytes())}
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for question in questions:
        key = question["id"]
        pool = []
        real_collect = rfc_demo.candidate_records

        def capture(query):
            candidates, limit = real_collect(query)
            pool.extend(candidates)
            return candidates, limit

        with (
            patch.object(rfc_demo, "candidate_records", side_effect=capture) as collect,
            patch.object(
                rfc_demo, "get_model", side_effect=AssertionError("unexpected Writer")
            ) as writer,
        ):
            result = await rfc_demo.run_rfc_qa(
                question["question"], output / key, sources_only=True
            )
            writer.assert_not_called()
            if collect.call_count != 1 or result["requests"]:
                raise ValueError("unexpected_execution_path")
        ref = refs[key]
        anchors = {
            (a["rfc"], a["section"], norm(a["text"]))
            for point in ref["points"]
            for a in point["anchors"]
        }
        records = {r["evidence_id"]: r for r in pool}
        excerpts = [line[4:] for line in result["answer"].splitlines() if line.startswith("    ")]
        visible = [
            {**records[key], "content": excerpt}
            for key, excerpt in zip(result["evidence_ids"], excerpts, strict=True)
        ]
        rows.append(
            {
                "id": key,
                "category": ref["category"],
                "status": result["status"],
                "anchors": len(anchors),
                "pool_hits": hits(pool, anchors),
                "visible_hits": hits(visible, anchors),
                "visible_count": len(visible),
                "sections": sorted({r["locator"] for r in visible}),
                "requests": result["requests"],
                "seconds": result["duration_seconds"],
            }
        )
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    asyncio.run(run(parser.parse_args().output))
