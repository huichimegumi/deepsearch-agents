"""Measure the actual source preview path. A sealed check emits only aggregates."""

import argparse
import asyncio
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from app.research import rfc_demo
from evals.rfc_demo.validate_demo import index_digest
from evals.rfc_demo.verify import HERE, ROOT, SEALED, check_split, norm, sections


def hits(records, anchors):
    return sum(
        any(
            record["locator"].endswith(f"rfc{rfc}.html#section-{section}")
            and text in norm(record["content"])
            for record in records
        )
        for rfc, section, text in anchors
    )


async def run(output, *, baseline=False, postgres=False, sealed=False):
    lock = json.loads((HERE / "suite.lock.json").read_bytes())
    split = "sealed" if sealed else "development"
    directory = SEALED if sealed else HERE
    if sealed:
        if subprocess.check_output(
            ["git", "diff", "HEAD", "--", "app", "evals/rfc_demo"], cwd=ROOT
        ):
            raise ValueError("sealed_check_requires_committed_route")
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        index = index_digest()
    check_split(
        directory, lock["splits"][split], "H" if sealed else "D", sections(lock["corpus_sha256"])
    )
    questions = json.loads((directory / "questions.json").read_bytes())
    refs = {r["id"]: r for r in json.loads((directory / "references.json").read_bytes())}
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    rows = []
    for question in questions:
        key = question["id"]
        pool = []
        real_collect = rfc_demo.candidate_records

        def capture(query):
            candidates, limit = real_collect(query, postgres=postgres or baseline)
            pool.extend(candidates)
            return candidates, limit

        shown = []
        store_add = rfc_demo.EvidenceStore.add

        def capture_shown(store, records, step):
            shown.extend(records)
            return store_add(store, records, step)

        with (
            patch.object(rfc_demo, "candidate_records", side_effect=capture) as collect,
            patch.object(rfc_demo.EvidenceStore, "add", capture_shown),
            patch.object(
                rfc_demo, "get_model", side_effect=AssertionError("unexpected Writer")
            ) as writer,
        ):

            def original_retrieve(query):
                candidates, limit = rfc_demo.candidate_records(query)
                return candidates[:limit]

            retrieve = original_retrieve if baseline else rfc_demo._retrieve
            with patch.object(rfc_demo, "_retrieve", retrieve):
                result = await rfc_demo.run_rfc_qa(
                    question["question"], output / key, sources_only=True
                )
            writer.assert_not_called()
            if collect.call_count != 1 or result["requests"] or result["status"] == "failed":
                raise ValueError("unexpected_execution_path")
        ref = refs[key]
        occurrences = [
            (a["rfc"], a["section"], norm(a["text"]))
            for point in ref["points"]
            for a in point["anchors"]
        ]
        anchors = set(occurrences)
        records = {r["evidence_id"]: r for r in shown}
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
                "anchor_occurrences": len(occurrences),
                "pool_occurrence_hits": hits(pool, occurrences),
                "visible_occurrence_hits": hits(visible, occurrences),
                "visible_count": len(visible),
                "sections": sorted({r["locator"] for r in visible}),
                "requests": result["requests"],
                "seconds": result["duration_seconds"],
            }
        )
    if sealed:
        if index_digest() != index:
            raise ValueError("sealed_check_index_changed")
        answerable = [row for row in rows if row["anchors"]]
        rows = {
            "commit": commit,
            "index_sha256": index,
            "question_sha256": lock["splits"]["sealed"]["sha256"]["questions.json"],
            "previously_used": True,
            "questions": len(rows),
            "answerable": len(answerable),
            "anchors": sum(row["anchors"] for row in answerable),
            "pool_hits": sum(row["pool_hits"] for row in answerable),
            "visible_hits": sum(row["visible_hits"] for row in answerable),
            "all_visible": sum(row["visible_hits"] == row["anchors"] for row in answerable),
            "requests": sum(row["requests"] for row in rows),
        }
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--baseline", action="store_true", help="Postgres and original short previews"
    )
    group.add_argument("--postgres", action="store_true", help="Postgres with chapter expansion")
    group.add_argument("--sealed", action="store_true", help="Previously used five-question split")
    args = parser.parse_args()
    asyncio.run(
        run(args.output, baseline=args.baseline, postgres=args.postgres, sealed=args.sealed)
    )
