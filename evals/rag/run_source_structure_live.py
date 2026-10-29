"""Small, opt-in live source/structure retrieval check; no generation or answer scoring."""

import argparse
import json
from pathlib import Path
from time import perf_counter

from evals.rag.protocol import canonical_sha256
from evals.rag.run_retrieval import corpus_snapshot
from evals.runners.common import ROOT, write_json
from evals.runners.experiment import build_manifest, file_sha256, new_run_id

DATASET = Path(__file__).with_name("suites") / "source_structure_live_v1.json"
MAX_CASES = 5


def load_cases():
    cases = json.loads(DATASET.read_text(encoding="utf-8"))["cases"]
    if len(cases) != MAX_CASES or len({row["id"] for row in cases}) != MAX_CASES:
        raise ValueError("live_suite_requires_five_unique_cases")
    if any(
        not all(
            row.get(key)
            for key in ("query", "knowledge_base", "expected_status", "expected_structure_status")
        )
        for row in cases
    ):
        raise ValueError("live_suite_missing_required_fields")
    return cases


def check_delivery(case, batch, diagnostics, corpus_by_id):
    plan = diagnostics.get("source_structure", {})
    records = batch["records"]
    delivered = [record["metadata"]["chunk_id"] for record in records]
    target = case.get("expected_document_sha256")
    checks = {
        "reranker_applied": diagnostics.get("rerank_applied") is True,
        "status": plan.get("status") == case["expected_status"],
        "structure_status": plan.get("structure_status") == case["expected_structure_status"],
        "delivery_binding": diagnostics.get("delivered_ids") == delivered,
        "stable_evidence_ids": len({record["evidence_id"] for record in records}) == len(records),
    }
    if target:
        checks["resolved_document"] = tuple(plan.get("document_sha256", ())) == (target,)
        checks["source_scope"] = bool(records) and all(
            corpus_by_id.get(record["metadata"]["chunk_id"]) == target for record in records
        )
    if case["expected_structure_status"] == "selected":
        checks["structural_first"] = (
            bool(records)
            and records[0]["metadata"].get("retrieval_method") == "explicit_toc_structure"
        )
        checks["structural_pool_member"] = bool(plan.get("structural_ids")) and set(
            plan["structural_ids"]
        ).issubset(diagnostics.get("hybrid_ids", []))
    if case["expected_status"] != "resolved":
        checks["explicit_fallback"] = not plan.get("selected_ids")
    if case["expected_status"] == "unsupported_source_constraint":
        checks["excluded_source_not_delivered"] = not records and batch["status"] == "NO_EVIDENCE"
    return checks


def run(*, execute=False):
    cases = load_cases()
    output = ROOT / "evals/results" / new_run_id("source_structure_live")
    output.mkdir(parents=True, exist_ok=False)
    result = {
        "manifest": build_manifest(
            DATASET,
            {
                "execute": execute,
                "mode": "five_new_live_retrieval_checks",
                "max_local_queries": MAX_CASES,
                "max_generator_calls": 0,
                "max_web_queries": 0,
                "experimental_source_structure": True,
            },
        ),
        "status": "plan_only",
        "cases": [],
        "local_queries": 0,
        "generator_calls": 0,
        "web_queries": 0,
        "human_accuracy": None,
    }
    write_json(output / "results.json", result)
    if not execute:
        return output

    from app.rag.config import get_rag_settings
    from app.tools.evidence_tool import _collect_local_documents

    settings = get_rag_settings()
    if settings.min_relevance_score != 1 or settings.rerank_top_k != 8:
        raise ValueError("live_ranking_configuration_changed")
    snapshots = {
        name: corpus_snapshot([name])[1]
        for name in sorted({case["knowledge_base"] for case in cases})
    }
    before = {name: canonical_sha256(rows) for name, rows in snapshots.items()}
    by_id = {
        name: {row["chunk_id"]: row["document_sha256"] for row in rows}
        for name, rows in snapshots.items()
    }
    result["corpus_sha256"] = before
    result["status"] = "retrieving"
    write_json(output / "results.json", result)
    for case in cases:
        folder = output / case["id"]
        folder.mkdir()
        diagnostics = {}
        row = {"id": case["id"], "checks": {}}
        result["cases"].append(row)
        start = perf_counter()
        try:
            result["local_queries"] += 1
            batch = _collect_local_documents(
                case["query"],
                case["knowledge_base"],
                diagnostics=diagnostics,
                experimental_source_structure=True,
            ).to_dict()
            if batch["query"] != case["query"]:
                raise ValueError("retrieval_query_changed")
            write_json(folder / "diagnostics.json", diagnostics)
            write_json(folder / "retrieval.json", batch)
            row["checks"] = check_delivery(case, batch, diagnostics, by_id[case["knowledge_base"]])
            row["status"] = "pass" if all(row["checks"].values()) else "fail"
            row["batch_status"] = batch["status"]
            row["record_count"] = len(batch["records"])
            row["structure_status"] = diagnostics.get("source_structure", {}).get(
                "structure_status"
            )
            row["resolution_status"] = diagnostics.get("source_structure", {}).get("status")
            row["resolution_methods"] = diagnostics.get("source_structure", {}).get(
                "resolution_methods"
            )
            row["delivered_ids"] = diagnostics.get("delivered_ids", [])
        except Exception as exc:  # noqa: BLE001 - retain failed case and do not retry
            row.update(status="error", error_type=type(exc).__name__)
        finally:
            row["elapsed_ms"] = round((perf_counter() - start) * 1000, 3)
            row["artifact_sha256"] = {p.name: file_sha256(p) for p in sorted(folder.iterdir())}
            write_json(output / "results.json", result)
    result["corpus_unchanged"] = before == {
        name: canonical_sha256(corpus_snapshot([name])[1]) for name in before
    }
    result["source_unchanged"] = (
        result["manifest"]["source_sha256"] == build_manifest(DATASET, {})["source_sha256"]
    )
    result["dataset_unchanged"] = result["manifest"]["dataset_sha256"] == file_sha256(DATASET)
    result["status"] = (
        "checked"
        if result["corpus_unchanged"] and result["source_unchanged"] and result["dataset_unchanged"]
        else "invalid"
    )
    write_json(output / "results.json", result)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Run up to five local RAG queries")
    print(run(execute=parser.parse_args().execute))


if __name__ == "__main__":
    main()
