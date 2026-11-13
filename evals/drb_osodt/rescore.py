"""Compile existing OSODT responses for a fixed subset without model calls."""

import argparse
from pathlib import Path

from aeollm2_osodt.artifacts import load_jsonl_by_request_id
from aeollm2_osodt.dataset import discover_documents
from aeollm2_osodt.pipeline import _load_rubrics, compile_artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("score", type=Path)
    parser.add_argument("--exclude", type=int, required=True)
    args = parser.parse_args()
    root = args.score
    docs = [
        doc
        for doc in discover_documents(root / "inputs/reports")
        if doc.question_id != args.exclude
    ]
    rubrics = _load_rubrics(root / "inputs/rubrics", {doc.question_id for doc in docs})
    responses = load_jsonl_by_request_id(root / "osodt/responses.jsonl")
    responses = {
        key: row for key, row in responses.items() if key.split(":")[2] != f"q{args.exclude}"
    }
    if len(responses) != len(docs) * 8:
        raise ValueError("Incomplete retained response set")
    compile_artifacts("osodt", docs, rubrics, responses, root / "osodt")


if __name__ == "__main__":
    main()
