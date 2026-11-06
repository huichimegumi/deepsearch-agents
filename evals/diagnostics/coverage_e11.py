"""Evaluator-only reference shape inventory, without exporting queries or identifiers."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from evals.diagnostics.e8 import INPUTS, digest, read
from evals.worker_supervisor import atomic_json


def inventory(query):
    masked = re.sub(r"'(?:''|[^'])*'|--[^\n]*|/\*.*?\*/", " ", query, flags=re.S)
    return {
        "cte": bool(re.search(r"\bwith\b", masked, re.I)),
        "nested_select": len(re.findall(r"\bselect\b", masked, re.I)) > 1,
        "join": bool(re.search(r"\bjoin\b", masked, re.I)),
        "grouping": bool(re.search(r"\bgroup\s+by\b", masked, re.I)),
        "conditional": bool(re.search(r"\bcase\b", masked, re.I)),
        "window": bool(re.search(r"\bover\s*\(", masked, re.I)),
        "distance_order": bool(re.search(r"\babs\s*\(", masked, re.I)),
        "formatting": bool(re.search(r"\b(?:replace|printf|format|concat)\s*\(", masked, re.I)),
    }


def report(inputs=INPUTS):
    references = read(inputs / "references.json")
    return {
        "scope": "Exposed evaluator-side syntax inventory; alternative equivalent plans may use different syntax",
        "references_sha256": digest(references),
        "api_calls": 0,
        "cases": [
            {
                "id": r["id"],
                "direction": r["oracle"]["direction"],
                "reference_shape": inventory(r["oracle"]["reference_sql"]),
            }
            for r in references
            if r["suite"] == "hybrid"
        ],
        "e10_limits": [
            "No model-driven plan has passed a live SQL control",
            "No windows, subqueries or self joins in E10 compiler",
        ],
        "implementation_targets": [
            "Public-definition metric expansion with source hashes, independent of references",
            "Ordinary projection/filter/sort and bounded grouped bands/aggregations",
            "Unique observed anchor lookup and peer filters using bound values",
        ],
        "unsupported_targets": [
            "Cross-table computed metrics and nearest-to-group-mean queries until separately verified"
        ],
        "warning": "This inventory is not an implementation capability or benchmark pass count",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    atomic_json(args.output, report())
