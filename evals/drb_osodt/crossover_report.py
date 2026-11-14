"""Compare crossover reports with archived runs on matching DRB tasks."""

import argparse
from collections import Counter
from pathlib import Path
from statistics import mean, median

from evals.drb_osodt.tasks import select
from evals.public_benchmarks.run import read
from evals.worker_supervisor import atomic_json


def compare(scores, ids, left, right):
    deltas = [round(scores[q][left] - scores[q][right], 6) for q in ids]
    outcomes = Counter("win" if value > 0 else "loss" if value < 0 else "tie" for value in deltas)
    delta = mean(deltas)
    return {
        "n": len(ids),
        "mean": {arm: round(mean(scores[q][arm] for q in ids), 3) for arm in (left, right)},
        "delta": round(delta, 3),
        "wins": outcomes["win"],
        "losses": outcomes["loss"],
        "ties": outcomes["tie"],
        "decision": "ahead"
        if delta >= 0.30 and outcomes["win"] > len(ids) / 2
        else "close"
        if abs(delta) < 0.30
        else "no_improvement",
        "task_deltas": dict(zip(ids, deltas, strict=True)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    archive = args.archive
    output = archive / "crossover"
    current = read(output / "score/summary.json")["tasks"]
    historical = read(archive / "score-revised/summary.json")["tasks"]
    packets = read(output / "packets.json")
    intended = {str(p["id"]) for p in packets["X-C"]}
    if set(current) - intended or intended - historical.keys():
        raise ValueError("Mismatched task IDs")
    ids = sorted(current, key=int)
    languages = {str(t["id"]): t["language"] for t in select(8)}
    scores = {
        q: {arm: row["weighted_total"] for arm, row in (historical[q] | current[q]).items()}
        for q in ids
    }
    missing_sources = {
        arm: {str(p["id"]) for p in rows if not p["sources"]} for arm, rows in packets.items()
    }
    comparisons = {}
    for left, right in (("X-D", "A"), ("X-D", "D"), ("X-D", "X-C"), ("X-C", "C"), ("X-C", "A")):
        nonempty = [
            q for q in ids if all(q not in missing_sources.get(arm, ()) for arm in (left, right))
        ]
        pair = {
            "all": compare(scores, ids, left, right),
            "nonempty": compare(scores, nonempty, left, right),
        }
        for lang in ("zh", "en"):
            subset = [q for q in ids if languages[q] == lang]
            if subset:
                pair[lang] = compare(scores, subset, left, right)
        comparisons[f"{left} vs {right}"] = pair
    chars = {}
    for arm in ("A", "C", "D", "X-C", "X-D"):
        folder = (output if arm.startswith("X-") else archive) / arm
        sizes = {
            q: len(
                (folder / f"drb_{q}/attempt-0001/report.md")
                .read_text()
                .split("\n## Sources\n", 1)[0]
                .strip()
            )
            for q in ids
        }
        chars[arm] = {
            "median": median(sizes.values()),
            **{
                f"{lang}_median": median(size for q, size in sizes.items() if languages[q] == lang)
                for lang in ("zh", "en")
                if any(languages[q] == lang for q in sizes)
            },
        }
    atomic_json(
        output / "comparison.json",
        {
            "paired_tasks": len(ids),
            "excluded_tasks": sorted(intended - current.keys(), key=int),
            "zero_evidence_tasks": {
                arm: sorted(zeros, key=int) for arm, zeros in missing_sources.items()
            },
            "body_characters": chars,
            "comparisons": comparisons,
        },
    )


if __name__ == "__main__":
    main()
