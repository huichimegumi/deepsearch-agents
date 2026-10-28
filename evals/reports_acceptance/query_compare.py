"""Original versus concise question queries, with stage-level local retrieval diagnostics."""

import argparse
import re
from pathlib import Path

from evals.reports_acceptance.extended import safe_path
from evals.reports_acceptance.rag_transfer import KNOWLEDGE_BASES, corpus, questions
from evals.reports_acceptance.transfer import DATASET
from evals.runners.common import write_json
from evals.runners.experiment import build_manifest, file_sha256, new_run_id


def concise_query(task):
    title = re.search(r"《([^》]+)》", task["question"])
    cues = ["目录"] if "目录" in task["question"] else []
    return " ".join(
        ([title.group(1)] if title else []) + cues + [p["label"] for p in task["parts"]]
    )


def retrieve(query):
    from app.tools.evidence_tool import _collect_local_documents

    diagnostics = {}
    batch = _collect_local_documents(query, KNOWLEDGE_BASES[0], diagnostics=diagnostics)
    return {"batch": batch.to_dict(), "diagnostics": diagnostics}


def run(*, execute=False):
    tasks = questions()
    plan = [
        {"id": task["id"], "original": task["question"], "concise": concise_query(task)}
        for task in tasks
    ]
    output = safe_path(Path("evals/results") / new_run_id("rag_query_compare"))
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "query_plan.json", plan)
    result = {
        "manifest": build_manifest(
            DATASET,
            {
                "execute": execute,
                "max_local_queries": 6,
                "generator_calls": 0,
                "search_queries": 0,
                "query_plan_sha256": file_sha256(output / "query_plan.json"),
            },
        ),
        "cases": [],
        "status": "plan_only",
    }
    write_json(output / "results.json", result)
    if not execute:
        return output
    from app.rag.config import get_rag_settings
    from evals.rag.protocol import canonical_sha256

    settings = get_rag_settings()
    result["retrieval_configuration"] = {
        k: getattr(settings, k)
        for k in (
            "embedding_model",
            "rerank_model",
            "vector_top_k",
            "lexical_top_k",
            "rerank_top_k",
            "min_relevance_score",
        )
    }
    before = corpus()
    write_json(output / "corpus.json", before)
    result["corpus_sha256"] = canonical_sha256(before)
    result["status"] = "running"
    write_json(output / "results.json", result)
    for task in plan:
        folder = output / task["id"]
        folder.mkdir()
        for variant in ("original", "concise"):
            row = {"id": task["id"], "variant": variant, "local_queries": 1}
            result["cases"].append(row)
            try:
                captured = retrieve(task[variant])
                write_json(folder / f"{variant}.json", captured)
                diagnostics = captured["diagnostics"]
                row.update(
                    status=captured["batch"]["status"],
                    stage_counts={
                        key: len(diagnostics.get(key, []))
                        for key in (
                            "vector_ids",
                            "hybrid_ids",
                            "reranked_ids",
                            "retained_ids",
                            "delivered_ids",
                        )
                    },
                    rerank_applied=diagnostics.get("rerank_applied", False),
                    artifact_sha256=file_sha256(folder / f"{variant}.json"),
                )
            except Exception as exc:  # noqa: BLE001 - retain failed comparisons without retry
                row.update(status="ERROR", error_type=type(exc).__name__)
            finally:
                write_json(output / "results.json", result)
    result["corpus_unchanged"] = canonical_sha256(corpus()) == result["corpus_sha256"]
    result["source_unchanged"] = (
        result["manifest"]["source_sha256"] == build_manifest(DATASET, {})["source_sha256"]
    )
    result["status"] = (
        "compared"
        if result["corpus_unchanged"]
        and result["source_unchanged"]
        and all(r["status"] in {"OK", "PARTIAL", "NO_EVIDENCE"} for r in result["cases"])
        else "invalid"
    )
    write_json(output / "results.json", result)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute", action="store_true", help="Six local retrieval calls; no generator"
    )
    print(run(execute=parser.parse_args().execute))


if __name__ == "__main__":
    main()
