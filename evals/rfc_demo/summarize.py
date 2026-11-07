"""Compute development retrieval and runtime counts from a completed paired run."""

import argparse
import json
from pathlib import Path
from statistics import median

from evals.rfc_demo.verify import HERE, norm, sha


def read(path):
    return json.loads(path.read_bytes())


def summarize(output):
    lock = read(HERE / "suite.lock.json")["splits"]["development"]["sha256"]
    raw = (HERE / "references.json").read_bytes()
    run = read(output / "results.json")
    if sha(raw) != lock["references.json"] or run["question_sha256"] != lock["questions.json"]:
        raise ValueError("comparison_input_changed")
    references = {r["id"]: r for r in json.loads(raw)}
    ids = set(references) - {"D02"}
    expected = {(key, arm) for key in ids for arm in ("hybrid", "rerank")}
    if len(run["rows"]) != len(expected) or {(r["id"], r["arm"]) for r in run["rows"]} != expected:
        raise ValueError("incomplete_pair")
    details = {}
    for row in run["rows"]:
        key, arm = row["id"], row["arm"]
        packet = read(output / key / "pool.json")
        selected = [packet["pool"][i] for i in packet["selected"][arm]]
        if [e["evidence_id"] for e in selected] != row["evidence_ids"]:
            raise ValueError(f"recorded_selection_changed:{key}:{arm}")
        anchors = {
            (a["rfc"], a["section"], norm(a["text"]))
            for p in references[key]["points"]
            for a in p["anchors"]
        }
        hit = sum(
            any(
                e["locator"].endswith(f"rfc{rfc}.html#section-{section}")
                and text in norm(e["content"])
                for e in selected
            )
            for rfc, section, text in anchors
        )
        details.setdefault(key, {})[arm] = {
            "status": row["status"],
            "anchors_found": hit,
            "anchors_total": len(anchors),
            "retrieval_seconds": row["retrieval_seconds"],
            "total_seconds": round(row["retrieval_seconds"] + row["duration_seconds"], 3),
            "requests": row["requests"],
            "tokens": (row["model_usage"] or {}).get("total_tokens"),
        }
    summary = {}
    for arm in ("hybrid", "rerank"):
        rows = [r[arm] for r in details.values()]
        tokens = [r["tokens"] for r in rows if r["tokens"] is not None]
        summary[arm] = {
            "anchor_hits": sum(r["anchors_found"] for r in rows),
            "anchors_total": sum(r["anchors_total"] for r in rows),
            "macro_recall": round(
                sum(r["anchors_found"] / r["anchors_total"] for r in rows if r["anchors_total"])
                / sum(bool(r["anchors_total"]) for r in rows),
                4,
            ),
            "median_retrieval_seconds": median(r["retrieval_seconds"] for r in rows),
            "median_total_seconds": median(r["total_seconds"] for r in rows),
            "requests": sum(r["requests"] for r in rows),
            "known_tokens": sum(tokens),
            "rows_without_tokens": len(rows) - len(tokens),
        }
    return {"summary": summary, "cases": details}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.output), indent=2))
