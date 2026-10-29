"""Offline exact-source/TOC replay over saved raw/context reranker scores."""

import argparse
import copy
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

from app.rag.source_structure import plan_source_structure, scoped_delivery_ids
from evals.rag.run_relation_query import load_inputs
from evals.rag.run_retention import DATASET, materialize, score, summarize
from evals.runners.common import ROOT, write_json
from evals.runners.experiment import build_manifest, file_sha256, new_run_id

POLICIES = ("baseline_raw", "scoped_raw", "baseline_context", "scoped_context")


def replay_policy(task, corpus, plan, policy):
    if plan.status != "resolved":
        return copy.deepcopy(policy)
    from app.research.evidence import retrieved_chunks_to_evidence
    from app.tools.local_rag_tools import _limit_hits_for_answer

    ids = scoped_delivery_ids(plan, corpus, policy)
    pool = SimpleNamespace(
        rows={
            i: (
                SimpleNamespace(
                    id=i,
                    content=corpus[i]["content"],
                    page_start=corpus[i]["page_start"],
                    page_end=corpus[i]["page_end"],
                    section=corpus[i].get("section"),
                    chunk_index=corpus[i]["chunk_index"],
                ),
                SimpleNamespace(
                    filename=corpus[i]["filename"], sha256=corpus[i]["document_sha256"]
                ),
            )
            for i in ids
        }
    )
    hits = materialize(
        ids, pool, {"rerank_scores": policy["rerank_scores"], "rerank_applied": True}
    )
    # Reused scores were actually computed in E4.10; structural selection did not pass its gate.
    delivered, budget = _limit_hits_for_answer(hits)
    records = retrieved_chunks_to_evidence(delivered, knowledge_base_ids=[], query=task["query"])
    output_hits = [
        {
            "chunk_id": h.chunk_id,
            "document_sha256": h.document_sha256,
            "filename": h.filename,
            "evidence_id": record.evidence_id,
            "content": h.content,
        }
        for h, record in zip(delivered, records, strict=True)
    ]
    return {
        "hits": output_hits,
        "budget": budget,
        "metrics": score(task["case"], output_hits) if "case" in task else None,
        "structural_delivery_ids": [
            h.chunk_id for h in delivered if h.chunk_id in plan.structural_ids
        ],
        "selection_method": "exact_document_scope_with_explicit_toc_reservation",
        "historical_scores_reused": True,
    }


def evaluate(task, corpus, control, *, allow_page_suffix=False):
    from evals.rag.protocol import canonical_sha256

    if control["status"] != "ok" or control["candidate_pool_sha256"] != canonical_sha256(
        task["hybrid_ids"]
    ):
        raise ValueError("control_pool_binding_changed")
    plan = plan_source_structure(
        task["query"], corpus, task["hybrid_ids"], allow_page_suffix=allow_page_suffix
    )
    output = {"id": task["id"], "status": "ok", "plan": asdict(plan), "policies": {}}
    for name, source in (("raw", "baseline"), ("context", "source_context")):
        policy = control["policies"][source]
        if set(policy["reranked_ids"]) != set(task["hybrid_ids"]):
            raise ValueError("control_ranking_membership_changed")
        if "case" in task and score(task["case"], policy["hits"]) != policy["metrics"]:
            raise ValueError("historical_metrics_changed")
        output["policies"][f"baseline_{name}"] = copy.deepcopy(policy)
        output["policies"][f"scoped_{name}"] = replay_policy(task, corpus, plan, policy)
    return output


def run(*, execute=False, diagnostic=False, allow_page_suffix=False):
    tasks, corpus, hashes, controls = load_inputs(diagnostic=diagnostic)
    output = (
        ROOT
        / "evals/results"
        / new_run_id("source_structure_diagnostic" if diagnostic else "source_structure_dev")
    )
    output.mkdir(parents=True, exist_ok=False)
    result = {
        "manifest": build_manifest(
            DATASET,
            {
                "execute": execute,
                "diagnostic": diagnostic,
                "mode": "offline_fixed_score_replay",
                "test_split_executed": False,
                "allow_indexed_page_suffix": allow_page_suffix,
            },
        ),
        "input_sha256": hashes,
        "status": "plan_only",
        "cases": [],
        "local_retrieval_queries": 0,
        "local_rerank_calls": 0,
        "generator_calls": 0,
        "search_queries": 0,
    }
    write_json(output / "results.json", result)
    if not execute:
        return output
    # Same frozen delivery settings; model artifacts need not be loaded for a replay.
    from app.config import get_settings

    if (
        get_settings().rag_answer_max_hits != 6
        or get_settings().rag_answer_max_context_chars != 10000
    ):
        raise ValueError("context_budget_changed")
    for task in tasks:
        try:
            row = evaluate(task, corpus, controls[task["id"]], allow_page_suffix=allow_page_suffix)
        except Exception as exc:  # noqa: BLE001 - explicit invalid row, never retry
            row = {"id": task["id"], "status": "invalid", "error_type": type(exc).__name__}
        result["cases"].append(row)
        if not diagnostic:
            result["summary"] = summarize(result["cases"], POLICIES)
        write_json(output / "results.json", result)
    result["inputs_unchanged"] = all(file_sha256(Path(p)) == h for p, h in hashes.items())
    result["source_unchanged"] = (
        result["manifest"]["source_sha256"] == build_manifest(DATASET, {})["source_sha256"]
    )
    result["status"] = (
        "replayed"
        if result["inputs_unchanged"]
        and result["source_unchanged"]
        and all(row["status"] == "ok" for row in result["cases"])
        else "invalid"
    )
    write_json(output / "results.json", result)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Offline replay only, no inference")
    parser.add_argument("--diagnostic", action="store_true")
    parser.add_argument(
        "--indexed-page-suffix",
        action="store_true",
        help="Allow suffix removal only when it matches scoped indexed last-page metadata",
    )
    args = parser.parse_args()
    print(
        run(
            execute=args.execute,
            diagnostic=args.diagnostic,
            allow_page_suffix=args.indexed_page_suffix,
        )
    )


if __name__ == "__main__":
    main()
