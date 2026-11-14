"""Compare the frozen A/P outputs with A8 and the closed-book holdout control."""

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import median

from evals.public_benchmarks.run import read
from evals.retrieval_necessity.run import attempt_path, content_hash
from evals.worker_supervisor import atomic_json


def compare(archive, wider, closed=None):
    existing = read(archive / "summary.json")
    extra = read(wider / "summary.json")
    control = read(closed / "summary.json") if closed else existing
    cases = existing["slices"]["all"]["tasks"]
    controls = [(wider, extra)]
    if closed:
        controls.append((closed, control))
    for directory, summary in controls:
        if summary["slices"]["all"]["tasks"] != cases:
            raise ValueError(f"Control cases differ from {archive}")
        if read(directory / "manifest.json")["previous_summary_sha256"] != content_hash(
            archive / "summary.json"
        ):
            raise ValueError(f"Control was generated against a different archive: {directory}")
    arms = {
        "closed": (closed or archive, control),
        "A": (archive, existing),
        "A8": (wider, extra),
        "P": (archive, existing),
    }
    per_case = {}
    for case in cases:
        per_case[case] = {}
        for arm, (directory, summary) in arms.items():
            attempt = attempt_path(directory, arm, case)
            result = read(attempt / "worker_result.json")
            facts = summary["by_question"][case][arm]
            query_path = attempt / "provider_attempts.json"
            state = read(attempt / "research_result.json")["status"]
            if arm == "P":
                tokens = read(attempt / "research_trace.json")["metrics"]["input_tokens"]
            else:
                tokens = sum(item["input_tokens"] for item in result["usage"] if item)
            per_case[case][arm] = {
                "correct": facts["correct"],
                "possible": facts["possible"],
                "fact_statuses": {f["id"]: f["status"] for f in facts["facts"]},
                "seconds": result["seconds"],
                "input_tokens": tokens,
                "status": state,
                "queries": read(query_path)["attempts"] if query_path.exists() else 0,
            }

    def slice_summary(ids):
        totals = {}
        for arm in arms:
            rows = [per_case[case][arm] for case in ids]
            totals[arm] = {
                "correct": sum(row["correct"] for row in rows),
                "possible": sum(row["possible"] for row in rows),
                "queries": sum(row["queries"] for row in rows),
                "median_seconds": median(row["seconds"] for row in rows),
                "median_input_tokens": median(row["input_tokens"] for row in rows),
                "status": dict(Counter(row["status"] for row in rows)),
                "correct_by_position": {
                    fid: sum(row["fact_statuses"].get(fid) == "correct" for row in rows)
                    for fid in sorted({fid for row in rows for fid in row["fact_statuses"]})
                },
            }
        pairs = {}
        for left, right in (("A8", "A"), ("P", "A8"), ("A8", "closed")):
            deltas = [
                per_case[case][left]["correct"] - per_case[case][right]["correct"] for case in ids
            ]
            pairs[f"{left}_vs_{right}"] = {
                "wins": sum(n > 0 for n in deltas),
                "ties": deltas.count(0),
                "losses": sum(n < 0 for n in deltas),
            }
        return {"tasks": ids, "totals": totals, "pairs": pairs}

    slices = {key: slice_summary(row["tasks"]) for key, row in existing["slices"].items()}
    receipts = Counter(
        str(json.loads(line)["credits"])
        for line in (wider / "tavily_receipts.jsonl").read_text().splitlines()
    )
    attempts = len((wider / "tavily_attempts.jsonl").read_text().splitlines())
    if slices["all"]["totals"]["A8"]["queries"] != attempts:
        raise ValueError("Query ledger does not match completed A8 cases")
    return {
        "slices": slices,
        "by_question": per_case,
        "A8_attempts": attempts,
        "A8_credit_receipts": dict(receipts),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("original", type=Path)
    parser.add_argument("original_a8", type=Path)
    parser.add_argument("holdout", type=Path)
    parser.add_argument("holdout_a8", type=Path)
    parser.add_argument("holdout_closed", type=Path)
    args = parser.parse_args()
    atomic_json(
        args.output,
        {
            "original": compare(args.original, args.original_a8),
            "holdout": compare(args.holdout, args.holdout_a8, args.holdout_closed),
        },
    )


if __name__ == "__main__":
    main()
