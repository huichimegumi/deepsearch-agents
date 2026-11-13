"""Summarize the C repair against archived A and C on common scored tasks."""

import argparse
from collections import Counter
from pathlib import Path
from statistics import mean, median

from evals.public_benchmarks.run import read
from evals.worker_supervisor import atomic_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root
    original = read(root / "score/summary.json")
    repaired = read(root / "repair-score/summary.json")
    if original["paired_tasks"] != 15 or set(original["tasks"]) != set(repaired["tasks"]):
        raise ValueError("Repair comparison requires the same 15 tasks")
    results = {}
    for arm in ("A", "C", "C-repaired"):
        for_question = {}
        for question, original_rows in original["tasks"].items():
            if arm == "C-repaired":
                scores = repaired["tasks"][question][arm]
            else:
                scores = original_rows[arm]
            directory = root / arm / f"drb_{question}" / "attempt-0001"
            worker = read(directory / "worker_result.json")
            for_question[question] = {
                **scores,
                "seconds": worker["seconds"],
                "reasons": worker.get("failure_reasons", []),
                "search_queries": (worker.get("usage") or {}).get("search_queries")
                if arm != "A"
                else None,
            }
        rows = list(for_question.values())
        results[arm] = {
            "status": Counter(row["status"] for row in rows),
            "failures": Counter(reason for row in rows for reason in row["reasons"]),
            "median_seconds": median(row["seconds"] for row in rows),
            "weighted_total": round(mean(row["weighted_total"] for row in rows), 3),
            "zero_search": sum(row["search_queries"] == 0 for row in rows) if arm != "A" else None,
            "tasks": for_question,
        }
    atomic_json(root / "repair-score/comparison.json", {"paired_tasks": 15, "arms": results})


if __name__ == "__main__":
    main()
