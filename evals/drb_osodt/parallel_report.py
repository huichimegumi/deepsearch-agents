"""Summarize the closed-book and parallel-web runs against archived paired scores."""

import argparse
from pathlib import Path

from evals.drb_osodt.crossover_report import compare
from evals.drb_osodt.process_report import aggregate
from evals.public_benchmarks.run import read
from evals.worker_supervisor import atomic_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = args.archive
    historical = read(root / "score/summary.json")["tasks"]
    ids = sorted(historical, key=int)
    if len(ids) != 15:
        raise ValueError("Expected the 15 frozen tasks")
    scores = {q: {arm: historical[q][arm]["weighted_total"] for arm in ("A", "C")} for q in ids}
    result = {}
    for folder, arm in (("closed-book", "Closed"), ("parallel", "P")):
        path = root / folder / "score/summary.json"
        if not path.exists():
            continue
        rows = read(path)["tasks"]
        if not rows or rows.keys() - historical.keys():
            raise ValueError(f"Unexpected task IDs in {arm} scores")
        for question, row in rows.items():
            scores[question][arm] = row[arm]["weighted_total"]
        common = [q for q in ids if q in rows]
        result[arm] = {
            "excluded_tasks": [q for q in ids if q not in rows],
            "vs_A": compare(scores, common, arm, "A"),
        }
        if arm == "P":
            result[arm]["vs_C"] = compare(scores, common, arm, "C")
    process = {"C": aggregate(root / "C", set(map(int, ids)))}
    parallel = root / "parallel/P"
    if (root / "parallel/stage").read_text().strip() in {"scoring", "complete"}:
        process["P"] = aggregate(parallel, set(map(int, ids)))
    result["process"] = process
    atomic_json(args.output, result)


if __name__ == "__main__":
    main()
