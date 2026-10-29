"""Planner component challenges; no retrieval or report-accuracy claims."""

import argparse
import copy
import json
from dataclasses import asdict
from pathlib import Path

from app.rag.source_structure import (
    document_inventory,
    is_toc,
    plan_source_structure,
    resolve_document_sources,
)
from evals.rag.run_context_rerank import load_pools
from evals.runners.common import ROOT, write_json
from evals.runners.experiment import build_manifest, file_sha256, new_run_id

DATASET = Path(__file__).with_name("suites") / "source_structure_v1.json"


def evaluate(case, original):
    corpus = copy.deepcopy(original)
    ids = list(corpus)
    mutation = case.get("mutation")
    if mutation:
        resolution = resolve_document_sources(
            case["query"], document_inventory(corpus), allow_page_suffix=True
        )
        if resolution.status != "resolved" or len(resolution.document_sha256) != 1:
            raise ValueError("fixture_requires_unique_document")
        document = resolution.document_sha256[0]
        targets = [
            i
            for i, row in corpus.items()
            if row["document_sha256"] == document and is_toc(row["content"])
        ]
        if len(targets) != 1:
            raise ValueError("fixture_requires_unique_toc")
        target = targets[0]
        if mutation == "duplicate_document_name":
            corpus["synthetic_duplicate_document"] = {
                **corpus[target],
                "document_sha256": "synthetic_distinct_document",
            }
        elif mutation == "duplicate_toc":
            corpus["synthetic_duplicate_toc"] = copy.deepcopy(corpus[target])
        elif mutation == "exclude_toc_from_pool":
            ids.remove(target)
        elif mutation == "exclude_toc_from_corpus":
            ids.remove(target)
            del corpus[target]
        else:
            raise ValueError("unknown_fixture_mutation")
    actual = asdict(plan_source_structure(case["query"], corpus, ids, allow_page_suffix=True))
    return {
        "id": case["id"],
        "fixture_kind": "synthetic_perturbation" if mutation else "original_corpus",
        "mutation": mutation,
        "expected": case["expected"],
        "actual": actual,
        "passed": all(actual[k] == v for k, v in case["expected"].items()),
    }


def run(output):
    _, corpus, hashes = load_pools()
    hashes[str(DATASET.resolve())] = file_sha256(DATASET)
    suite = json.loads(DATASET.read_text(encoding="utf-8"))
    cases = suite["cases"]
    if not cases or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("invalid_challenge_ids")
    result = {
        "manifest": build_manifest(
            DATASET,
            {
                "mode": "planner_component_checks",
                "candidate_policy": "full_scoped_corpus_not_fresh_recall",
            },
        ),
        "input_sha256": hashes,
        "cases": [evaluate(c, corpus) for c in cases],
        "retrieval_queries": 0,
        "rerank_calls": 0,
        "generator_calls": 0,
        "search_queries": 0,
        "human_accuracy": None,
        "production_default_changed": False,
    }
    result["passed"] = sum(r["passed"] for r in result["cases"])
    result["total"] = len(cases)
    result["inputs_unchanged"] = all(file_sha256(Path(p)) == h for p, h in hashes.items())
    result["status"] = "checked" if result["inputs_unchanged"] else "invalid"
    write_json(output, result)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "evals/results" / new_run_id("structure_challenges") / "results.json",
    )
    print(run(parser.parse_args().output))


if __name__ == "__main__":
    main()
