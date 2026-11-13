"""Pair OSODT scores of exported DeepResearch Bench reports by task. No model is called.

Scores use the judge's 0-10 scale. The weighted total applies the published dimension
weights of each task. This is not an official RACE score.
"""

import argparse
import csv
import json
from pathlib import Path
from statistics import mean

DIMENSIONS = ("comprehensiveness", "insight", "instruction_following", "readability")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Contains inputs/ and osodt/")
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()

    documents = json.loads((args.directory / "inputs/documents.json").read_bytes())
    runs = {(d["question"], d["answer"]): d for d in documents}
    labels = list(dict.fromkeys(d["run"] for d in documents))
    with (args.directory / "osodt/predictions/osodt.tsv").open(encoding="utf-8") as handle:
        scored = list(csv.DictReader(handle, delimiter="\t"))
    tasks = {}
    for row in scored:
        question = int(row["questionId"])
        rubric = json.loads(
            (args.directory / f"inputs/rubrics/criteria{question}.json").read_bytes()
        )
        weights = rubric["dimension_weight"]
        scores = {name: float(row[f"{name}_score"]) for name in DIMENSIONS}
        scores["weighted_total"] = sum(scores[n] * weights[n] for n in DIMENSIONS) / sum(
            weights[n] for n in DIMENSIONS
        )
        document = runs[question, row["answerId"]]
        tasks.setdefault(question, {})[document["run"]] = {
            "status": document["status"],
            "characters": document["characters"],
            **{name: round(value, 3) for name, value in scores.items()},
        }
    paired = {q: t for q, t in sorted(tasks.items()) if all(label in t for label in labels)}
    metrics = (*DIMENSIONS, "weighted_total")
    summary = {
        "judge": "OSODT, 0-10 scale, published DRB criteria; not an official RACE score",
        "paired_tasks": len(paired),
        "documents": len(scored),
        "mean": {
            label: {m: round(mean(t[label][m] for t in paired.values()), 3) for m in metrics}
            for label in labels
        },
        "tasks": paired,
    }
    if len(labels) == 2:
        first, second = labels
        summary["wins_by_weighted_total"] = {
            second: sum(
                t[second]["weighted_total"] > t[first]["weighted_total"] for t in paired.values()
            ),
            first: sum(
                t[first]["weighted_total"] > t[second]["weighted_total"] for t in paired.values()
            ),
        }
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.summary:
        args.summary.write_text(text + "\n", "utf-8")
    print(text)


if __name__ == "__main__":
    main()
