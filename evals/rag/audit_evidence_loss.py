"""Offline, label-only loss attribution over the hash-bound E4.10 paired outputs."""

import argparse
import json
import math
from collections import Counter
from pathlib import Path

from evals.rag.protocol import canonical_sha256
from evals.rag.run_context_rerank import load_pools
from evals.rag.run_retention import DATASET, score
from evals.rag.scoring import matches
from evals.runners.common import ROOT, write_json
from evals.runners.experiment import build_manifest, file_sha256

REPORT = ROOT / "evals/reports/e4-10-source-context-rerank-2026-10-28.json"
# Evaluator-only structural references. Never passed to retrieval or a model.
DIAGNOSTIC_TARGETS = {
    "transfer_local_001": "02092c12-ee31-4a8f-b611-e34696214c4c",
    "transfer_local_002": "be6b8c3c-b7b6-47fa-b889-8c59d83cc585",
}


def attribute(unit, corpus, policy, *, threshold=1, top_k=8):
    """First gate losing ALL finite alternative locations, not semantic relevance."""
    ids = policy["reranked_ids"]
    scores = policy["rerank_scores"]
    if (
        len(ids) != len(set(ids))
        or set(ids) != set(scores)
        or any(i not in corpus or not math.isfinite(scores[i]) for i in ids)
        or any(scores[a] < scores[b] for a, b in zip(ids, ids[1:]))
    ):
        raise ValueError("invalid_saved_ranking")
    eligible = [i for i in ids if scores[i] >= threshold]
    retained = eligible[:top_k]
    hits = policy["hits"]
    delivered = [h["chunk_id"] for h in hits]
    if (
        len(delivered) > 6
        or len(delivered) != len(set(delivered))
        or delivered != retained[: len(delivered)]
    ):
        raise ValueError("invalid_saved_delivery_order")
    if any(h["document_sha256"] != corpus[h["chunk_id"]]["document_sha256"] for h in hits):
        raise ValueError("unbound_delivered_document")
    matched_corpus = {i for i, row in corpus.items() if matches(unit, row)}
    matched_pool = matched_corpus.intersection(ids)
    stages = [
        ("corpus_reference_absent", matched_corpus),
        ("candidate_pool", matched_pool),
        ("score_threshold", matched_pool.intersection(eligible)),
        ("retained_top_k", matched_pool.intersection(retained)),
        ("delivery_budget", matched_pool.intersection(delivered)),
        ("delivered_text", {h["chunk_id"] for h in hits if matches(unit, h)}),
    ]
    loss = next((name for name, members in stages if not members), "delivered")
    documents = {loc["document_sha256"] for loc in unit["locations"]}
    return {
        "first_loss": loss,
        "corpus_match_count": len(matched_corpus),
        "matched_candidates": [
            {"chunk_id": i, "rank": rank, "score": scores[i]}
            for rank, i in enumerate(ids, 1)
            if i in matched_pool
        ],
        "delivered_match_ids": [h["chunk_id"] for h in hits if matches(unit, h)],
        "delivered_from_reference_documents": sum(h["document_sha256"] in documents for h in hits),
        "delivered_reference_document_without_anchor": sum(
            h["document_sha256"] in documents and not matches(unit, h) for h in hits
        ),
    }


def audit_rows(tasks, corpus, saved):
    if saved["status"] != "evaluated" or [r["id"] for r in saved["cases"]] != [
        t["id"] for t in tasks
    ]:
        raise ValueError("invalid_saved_cases")
    rows = []
    for task, row in zip(tasks, saved["cases"], strict=True):
        if row["status"] != "ok" or row["candidate_pool_sha256"] != canonical_sha256(
            task["hybrid_ids"]
        ):
            raise ValueError("candidate_binding_changed")
        if set(row["policies"]) != {"baseline", "source_context"}:
            raise ValueError("missing_paired_policy")
        if "case" in task:
            units = task["case"]["evidence_units"]
        else:
            ref = corpus[DIAGNOSTIC_TARGETS[task["id"]]]
            units = [
                {
                    "id": "diagnostic_reference",
                    "locations": [
                        {"document_sha256": ref["document_sha256"], "anchor": ref["content"]}
                    ],
                }
            ]
        item = {"id": task["id"], "units": [], "delivered_counts": {}}
        for name, policy in row["policies"].items():
            if set(policy["reranked_ids"]) != set(task["hybrid_ids"]):
                raise ValueError("policy_candidate_membership_changed")
            if "case" in task and score(task["case"], policy["hits"]) != policy["metrics"]:
                raise ValueError("saved_metrics_do_not_reproduce")
            item["delivered_counts"][name] = len(policy["hits"])
        for unit in units:
            item["units"].append(
                {
                    "unit_id": unit["id"],
                    "policies": {
                        name: attribute(unit, corpus, policy)
                        for name, policy in row["policies"].items()
                    },
                }
            )
        rows.append(item)
    return rows


def run(output):
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    hashes = {str(REPORT): file_sha256(REPORT)}
    groups = {}
    for group, diagnostic in (("development", False), ("diagnostic", True)):
        tasks, corpus, inputs = load_pools(diagnostic=diagnostic)
        hashes.update(inputs)
        path = ROOT / "evals/results" / report[f"{group}_run"] / "results.json"
        if file_sha256(path) != report[f"{group}_results_sha256"]:
            raise ValueError("paired_results_changed")
        hashes[str(path)] = file_sha256(path)
        saved = json.loads(path.read_text(encoding="utf-8"))
        groups[group] = audit_rows(tasks, corpus, saved)
    counts = {
        name: dict(
            Counter(
                unit["policies"][name]["first_loss"]
                for row in groups["development"]
                for unit in row["units"]
            )
        )
        for name in ("baseline", "source_context")
    }
    result = {
        "stage": "E4.11",
        "date": "2026-10-29",
        "status": "audited",
        "manifest": build_manifest(DATASET, {"mode": "offline_loss_attribution"}),
        "gate_configuration": {"min_score": 1, "retained_top_k": 8, "max_delivered": 6},
        "input_sha256": hashes,
        "groups": groups,
        "development_unit_gates": counts,
        "local_retrieval_queries": 0,
        "local_rerank_calls": 0,
        "generator_calls": 0,
        "search_queries": 0,
        "production_default_changed": False,
        "human_accuracy": None,
        "interpretation": "Finite-anchor attribution only; source identity is not passage support. "
        "Missing anchors do not establish semantic irrelevance or corpus absence.",
    }
    if not all(file_sha256(Path(p)) == h for p, h in hashes.items()):
        raise ValueError("audit_inputs_changed")
    # Output contains IDs, ranks, counts and hashes; no source passages or anchor text.
    if output.resolve() in {Path(p).resolve() for p in hashes}:
        raise ValueError("output_would_overwrite_input")
    write_json(output, result)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "evals/results/evidence_loss_audit.json"
    )
    print(run(parser.parse_args().output))


if __name__ == "__main__":
    main()
