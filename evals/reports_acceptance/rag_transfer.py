"""Opt-in live RAG retrieval, followed by frozen ID selection/Writer evaluation."""

import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter

from evals.reports_acceptance.extended import safe_path
from evals.reports_acceptance.handoff_writer import execute_handoffs
from evals.reports_acceptance.transfer import DATASET, select_case
from evals.runners.common import write_json
from evals.runners.experiment import build_manifest, file_sha256, new_run_id

KNOWLEDGE_BASES = ["电商行业"]


def questions():
    rows = json.loads(DATASET.read_text(encoding="utf-8"))["cases"]
    if len(rows) != 3 or len({row["id"] for row in rows}) != 3:
        raise ValueError("requires_three_frozen_questions")
    # Deliberately do not read the fixed-pool snapshot paths or known record IDs.
    return [
        {
            "id": row["id"],
            "question": row["question"],
            "parts": [
                {"part_id": key, "label": label, "quote_ids": []}
                for key, label in row["parts"].items()
            ],
            "records": [],
            "extracts": [],
            "assisted_source_selection": False,
        }
        for row in rows
    ]


def corpus():
    from evals.rag.run_retrieval import corpus_snapshot

    return corpus_snapshot(KNOWLEDGE_BASES)[1]


def retrieve_case(query, *, source_structure=False, diagnostics=None):
    from app.tools.evidence_tool import _collect_local_documents

    if source_structure:
        return _collect_local_documents(
            query, KNOWLEDGE_BASES[0], diagnostics=diagnostics, experimental_source_structure=True
        ).to_dict()
    return _collect_local_documents(query, KNOWLEDGE_BASES[0]).to_dict()


def prepare(*, retrieve=False, source_structure=False):
    inputs = questions()
    output = safe_path(
        Path("evals/results")
        / new_run_id("rag_structure_assets" if source_structure else "rag_transfer_assets")
    )
    output.mkdir(parents=True, exist_ok=False)
    result = {
        "manifest": build_manifest(
            DATASET,
            {
                "retrieval_enabled": retrieve,
                "experimental_source_structure": source_structure,
                "knowledge_bases": KNOWLEDGE_BASES,
                "max_local_queries": 3,
                "query_policy": "original_question_once",
                "search_queries": 0,
                "fetched_pages": 0,
            },
        ),
        "cases": [],
        "status": "plan_only",
        "model_calls": 0,
    }
    write_json(output / "results.json", result)
    if not retrieve:
        return output
    from app.rag.config import get_rag_settings
    from evals.rag.protocol import canonical_sha256

    settings = get_rag_settings()
    result["retrieval_configuration"] = {
        key: getattr(settings, key)
        for key in (
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
    result["corpus_file_sha256"] = file_sha256(output / "corpus.json")
    result["status"] = "retrieving"
    write_json(output / "results.json", result)
    for case in inputs:
        folder = output / case["id"]
        folder.mkdir()
        started = perf_counter()
        row = {"id": case["id"], "local_queries": 1}
        result["cases"].append(row)
        try:
            if source_structure:
                diagnostics = {}
                batch = retrieve_case(
                    case["question"], source_structure=True, diagnostics=diagnostics
                )
                write_json(folder / "diagnostics.json", diagnostics)
                if not diagnostics.get("rerank_applied"):
                    raise ValueError("live_reranker_not_applied")
            else:
                batch = retrieve_case(case["question"])
            if batch.get("query") != case["question"]:
                raise ValueError("retrieval_query_mismatch")
            case["records"] = batch["records"]
            write_json(folder / "retrieval.json", batch)
            write_json(folder / "inputs.json", case)
            row.update(
                status=batch["status"],
                evidence_records=len(case["records"]),
                rerank_applied_records=sum(
                    r["metadata"].get("rerank_applied") is True for r in case["records"]
                ),
            )
        except Exception as exc:  # noqa: BLE001 - preserve infrastructure failures without model calls
            row.update(status="ERROR", error_type=type(exc).__name__)
        finally:
            row["elapsed_ms"] = round((perf_counter() - started) * 1000, 3)
            row["artifact_sha256"] = {p.name: file_sha256(p) for p in sorted(folder.iterdir())}
            write_json(output / "results.json", result)
    result["corpus_unchanged"] = result["corpus_sha256"] == canonical_sha256(corpus())
    result["source_unchanged"] = (
        result["manifest"]["source_sha256"] == build_manifest(DATASET, {})["source_sha256"]
    )
    result["status"] = (
        "retrieved"
        if result["corpus_unchanged"]
        and result["source_unchanged"]
        and all(row["status"] in {"OK", "PARTIAL", "NO_EVIDENCE"} for row in result["cases"])
        else "invalid"
    )
    write_json(output / "results.json", result)
    return output


def load_retrieved(source):
    source = safe_path(source)
    path = source / "results.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    if result["status"] != "retrieved" or result["manifest"]["dataset_sha256"] != file_sha256(
        DATASET
    ):
        raise ValueError("invalid_retrieval_run_or_changed_questions")
    corpus_path = source / "corpus.json"
    if file_sha256(corpus_path) != result["corpus_file_sha256"]:
        raise ValueError("retrieval_corpus_file_changed")
    expected = questions()
    if [row["id"] for row in result["cases"]] != [row["id"] for row in expected]:
        raise ValueError("retrieved_case_set_changed")
    hashes = {
        str(path): file_sha256(path),
        str(corpus_path): file_sha256(corpus_path),
        str(DATASET.resolve()): file_sha256(DATASET),
    }
    inputs = []
    for row, task in zip(result["cases"], expected, strict=True):
        folder = safe_path(source / row["id"])
        names = ["inputs.json", "retrieval.json"]
        experimental = result["manifest"]["configuration"].get(
            "experimental_source_structure", False
        )
        if experimental:
            names.append("diagnostics.json")
        for name in names:
            item = folder / name
            if file_sha256(item) != row["artifact_sha256"][name]:
                raise ValueError("retrieved_input_hash_mismatch")
            hashes[str(item)] = file_sha256(item)
        case = json.loads((folder / "inputs.json").read_text(encoding="utf-8"))
        batch = json.loads((folder / "retrieval.json").read_text(encoding="utf-8"))
        if experimental:
            diagnostics = json.loads((folder / "diagnostics.json").read_text(encoding="utf-8"))
            if not diagnostics.get("rerank_applied") or diagnostics.get("delivered_ids") != [
                r["metadata"]["chunk_id"] for r in case["records"]
            ]:
                raise ValueError("experimental_diagnostics_binding_mismatch")
        if (
            {k: v for k, v in case.items() if k != "records"}
            != {k: v for k, v in task.items() if k != "records"}
            or case["records"] != batch["records"]
            or batch["query"] != task["question"]
            or any(
                r["source"] != "local_document"
                or not isinstance(r["content"], str)
                or not r.get("metadata", {}).get("filename")
                for r in case["records"]
            )
        ):
            raise ValueError("retrieval_binding_mismatch")
        inputs.append(case)
    return inputs, hashes


async def write(source, *, execute=False):
    inputs, hashes = load_retrieved(source)
    return await execute_handoffs(
        inputs,
        hashes,
        execute=execute,
        dataset=DATASET,
        prefix="live_rag_transfer",
        selector=select_case,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--retrieve", action="store_true", help="Three local RAG queries; no generator"
    )
    group.add_argument("--retrieved-run", type=Path)
    parser.add_argument(
        "--execute", action="store_true", help="Admit models only from a verified retrieval run"
    )
    parser.add_argument(
        "--source-structure",
        action="store_true",
        help="Opt in to exact source/TOC retrieval; ordinary search stays unchanged",
    )
    args = parser.parse_args()
    if args.execute and args.retrieved_run is None:
        parser.error("--execute requires --retrieved-run")
    if args.source_structure and args.retrieved_run:
        parser.error("--source-structure applies when preparing retrieval, not to saved runs")
    print(
        asyncio.run(write(args.retrieved_run, execute=args.execute))
        if args.retrieved_run
        else prepare(retrieve=args.retrieve, source_structure=args.source_structure)
    )


if __name__ == "__main__":
    main()
