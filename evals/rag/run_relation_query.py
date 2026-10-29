"""Frozen-pool query/title ablation crossed with raw/context passage formats."""

import argparse
import copy
import json
import re
from pathlib import Path

from evals.rag import run_context_rerank as context
from evals.rag.run_retention import DATASET, LOCK, summarize
from evals.runners.common import ROOT, write_json
from evals.runners.experiment import build_manifest, file_sha256, new_run_id

POLICIES = ("original_raw", "original_context", "relation_raw", "relation_context")
REPORT = ROOT / "evals/reports/e4-10-source-context-rerank-2026-10-28.json"


def relation_query(query):
    """Replace explicit book-title source names only; do not infer aliases or new cues."""
    titles = {}

    def replace(match):
        title = match.group(1)
        if title not in titles:
            titles[title] = f"文档{len(titles) + 1}"
        return titles[title]

    return re.sub(r"《([^《》\n]+)》", replace, query)


def load_inputs(*, diagnostic=False):
    tasks, corpus, hashes = context.load_pools(diagnostic=diagnostic)
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    group = "diagnostic" if diagnostic else "development"
    path = ROOT / "evals/results" / report[f"{group}_run"] / "results.json"
    if file_sha256(path) != report[f"{group}_results_sha256"]:
        raise ValueError("historical_context_control_changed")
    saved = json.loads(path.read_text(encoding="utf-8"))
    if saved["status"] != "evaluated" or [r["id"] for r in saved["cases"]] != [
        t["id"] for t in tasks
    ]:
        raise ValueError("invalid_historical_controls")
    hashes.update({str(REPORT): file_sha256(REPORT), str(path): file_sha256(path)})
    return tasks, corpus, hashes, {r["id"]: r for r in saved["cases"]}


def delivery_ids(policy):
    return [hit["chunk_id"] for hit in policy["hits"]]


def evaluate(task, corpus, control):
    original = context.evaluate(task, corpus)
    if original["status"] != "ok":
        return original
    query = relation_query(task["query"])
    unchanged = query == task["query"]
    relation = original if unchanged else context.evaluate({**task, "query": query}, corpus)
    calls = original["local_rerank_calls"] + (0 if unchanged else relation["local_rerank_calls"])
    if relation["status"] != "ok":
        return {**relation, "local_rerank_calls": calls}
    policies = {
        "original_raw": original["policies"]["baseline"],
        "original_context": original["policies"]["source_context"],
        "relation_raw": copy.deepcopy(relation["policies"]["baseline"]),
        "relation_context": copy.deepcopy(relation["policies"]["source_context"]),
    }
    controls_equal = {
        new: delivery_ids(policies[new]) == delivery_ids(control["policies"][old])
        for new, old in (("original_raw", "baseline"), ("original_context", "source_context"))
    }
    return {
        "id": task["id"],
        "status": "ok" if all(controls_equal.values()) else "invalid",
        "candidate_pool_sha256": original["candidate_pool_sha256"],
        "pool_order_source": original["pool_order_source"],
        "local_rerank_calls": calls,
        "relation_query_unchanged": unchanged,
        "relation_reused_current_controls": unchanged,
        "historical_delivery_controls_equal": controls_equal,
        "policies": policies,
    }


def verify_configuration():
    from app.config import get_settings
    from app.rag.config import get_rag_settings

    settings = get_rag_settings()
    frozen = json.loads(LOCK.read_text(encoding="utf-8"))["configuration"]
    if (
        settings.rerank_model != frozen["rerank_model"]
        or settings.min_relevance_score != 1
        or settings.rerank_top_k != 8
        or get_settings().rag_answer_max_hits != 6
        or get_settings().rag_answer_max_context_chars != 10000
    ):
        raise ValueError("frozen_reranker_configuration_changed")


def run(*, execute=False, diagnostic=False):
    tasks, corpus, hashes, controls = load_inputs(diagnostic=diagnostic)
    output = (
        ROOT
        / "evals/results"
        / new_run_id("relation_query_diagnostic" if diagnostic else "relation_query_dev")
    )
    output.mkdir(parents=True, exist_ok=False)
    plan = [
        {"id": task["id"], "original": task["query"], "relation": relation_query(task["query"])}
        for task in tasks
    ]
    write_json(output / "query_plan.json", plan)
    hashes[str(output / "query_plan.json")] = file_sha256(output / "query_plan.json")
    result = {
        "manifest": build_manifest(
            DATASET,
            {
                "execute": execute,
                "diagnostic": diagnostic,
                "query_policy": "explicit_book_titles_to_stable_document_placeholders_v1",
                "max_local_rerank_calls": sum(
                    2 if r["original"] == r["relation"] else 4 for r in plan
                ),
                "test_split_executed": False,
            },
        ),
        "input_sha256": hashes,
        "status": "plan_only",
        "cases": [],
        "local_retrieval_queries": 0,
        "generator_calls": 0,
        "search_queries": 0,
    }
    write_json(output / "results.json", result)
    if not execute:
        return output
    verify_configuration()
    result["model_artifacts"] = context.model_artifacts()
    result["status"] = "running"
    write_json(output / "results.json", result)
    for task in tasks:
        try:
            row = evaluate(task, corpus, controls[task["id"]])
        except Exception as exc:  # noqa: BLE001 - retain failure without retries
            row = {
                "id": task["id"],
                "status": "invalid",
                "error_type": type(exc).__name__,
                "local_rerank_calls": None,
            }
        result["cases"].append(row)
        if not diagnostic:
            result["summary"] = summarize(result["cases"], POLICIES)
        write_json(output / "results.json", result)
    result["inputs_unchanged"] = all(file_sha256(Path(p)) == h for p, h in hashes.items())
    result["source_unchanged"] = (
        result["manifest"]["source_sha256"] == build_manifest(DATASET, {})["source_sha256"]
    )
    result["model_artifacts_unchanged"] = result["model_artifacts"] == context.model_artifacts()
    result["status"] = (
        "evaluated"
        if all(
            result[key]
            for key in ("inputs_unchanged", "source_unchanged", "model_artifacts_unchanged")
        )
        and all(row["status"] == "ok" for row in result["cases"])
        else "invalid"
    )
    write_json(output / "results.json", result)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--diagnostic", action="store_true")
    args = parser.parse_args()
    print(run(execute=args.execute, diagnostic=args.diagnostic))


if __name__ == "__main__":
    main()
