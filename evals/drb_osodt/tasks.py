"""DeepResearch Bench task selection, extending the E7 fixed hash ranking.

Tasks of each language are ranked by the same seeded digest as E7, so the first three per
language are the six E7 tasks and a larger count only appends to them.
"""

import argparse
import json

from evals.public_benchmarks.prepare import DRB, SEED, digest, lines


def select(per_language):
    rows = lines(DRB / "data/prompt_data/query.jsonl")
    chosen = []
    for language in ("zh", "en"):
        ranked = sorted(
            (r for r in rows if r["language"] == language),
            key=lambda r: digest([SEED, "drb", r["id"]]),
        )
        chosen.extend(ranked[:per_language])
    return chosen


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-language", type=int, default=3)
    args = parser.parse_args()
    print(
        json.dumps(
            [{k: r[k] for k in ("id", "language", "topic")} for r in select(args.per_language)],
            ensure_ascii=False,
            indent=1,
        )
    )
