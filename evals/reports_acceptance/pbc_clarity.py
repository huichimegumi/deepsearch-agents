"""Two-question paired local retrieval, then frozen ID selection and Writer."""

import argparse
import asyncio
import json
from pathlib import Path

from evals.rag.protocol import canonical_sha256
from evals.rag.run_retrieval import corpus_snapshot
from evals.reports_acceptance.extended import safe_path
from evals.reports_acceptance.handoff_writer import execute_handoffs
from evals.reports_acceptance.transfer import select_case
from evals.runners.common import ROOT, write_json
from evals.runners.experiment import build_manifest, file_sha256, new_run_id

DATASET = Path(__file__).with_name("pbc_clarity_v1.json")
E416 = ROOT / "evals/reports/e4-16-new-live-structure-2026-10-29.json"
VARIANTS = ("ordinary", "experimental")


def load_suite():
    suite = json.loads(DATASET.read_text(encoding="utf-8"))
    cases = suite["cases"]
    if (
        len(cases) != 2
        or len({row["id"] for row in cases}) != 2
        or any(not row["question"] or len(row["parts"]) != 1 for row in cases)
    ):
        raise ValueError("pbc_clarity_requires_two_unique_questions")
    return suite


def validate_corpus(suite, corpus):
    by_id = {row["chunk_id"]: row for row in corpus}
    for case in suite["cases"]:
        row = by_id.get(case["reference_chunk_id"])
        if (
            row is None
            or row["document_sha256"] != suite["document_sha256"]
            or row["content_sha256"] != case["reference_content_sha256"]
        ):
            raise ValueError("frozen_source_reference_changed")
    finance_hash = json.loads(E416.read_text(encoding="utf-8"))["final"]["corpus_sha256"][
        "金融行业"
    ]
    if canonical_sha256(corpus) != finance_hash:
        raise ValueError("pbc_finance_corpus_changed")
    return by_id


def questions(suite):
    return [(case, variant) for case in suite["cases"] for variant in VARIANTS]


def retrieve(*, execute=False):
    suite = load_suite()
    output = safe_path(Path("evals/results") / new_run_id("pbc_clarity_assets"))
    output.mkdir(parents=True, exist_ok=False)
    result = {
        "manifest": build_manifest(
            DATASET,
            {
                "execute": execute,
                "knowledge_base": suite["knowledge_base"],
                "variants": VARIANTS,
                "max_local_queries": 4,
                "generator_calls": 0,
                "web_queries": 0,
                "e416_record_sha256": file_sha256(E416),
            },
        ),
        "status": "plan_only",
        "cases": [],
        "local_queries": 0,
    }
    write_json(output / "results.json", result)
    if not execute:
        return output
    from app.rag.config import get_rag_settings
    from app.tools.evidence_tool import _collect_local_documents

    settings = get_rag_settings()
    if settings.min_relevance_score != 1 or settings.rerank_top_k != 8:
        raise ValueError("pbc_ranking_configuration_changed")
    corpus = corpus_snapshot([suite["knowledge_base"]])[1]
    by_id = validate_corpus(suite, corpus)
    write_json(output / "corpus.json", corpus)
    result["corpus_sha256"] = canonical_sha256(corpus)
    result["corpus_file_sha256"] = file_sha256(output / "corpus.json")
    result["status"] = "retrieving"
    write_json(output / "results.json", result)
    for case, variant in questions(suite):
        name = f"{case['id']}__{variant}"
        folder = output / name
        folder.mkdir()
        row = {"id": name, "variant": variant, "status": "error"}
        result["cases"].append(row)
        diagnostics = {}
        try:
            result["local_queries"] += 1
            batch = _collect_local_documents(
                case["question"],
                suite["knowledge_base"],
                diagnostics=diagnostics,
                experimental_source_structure=(variant == "experimental"),
            ).to_dict()
            write_json(folder / "retrieval.json", batch)
            write_json(folder / "diagnostics.json", diagnostics)
            delivered = [item["metadata"]["chunk_id"] for item in batch["records"]]
            if (
                diagnostics.get("rerank_applied") is not True
                or diagnostics.get("delivered_ids") != delivered
                or batch["query"] != case["question"]
                or any(i not in by_id for i in delivered)
            ):
                raise ValueError("live_retrieval_binding_failed")
            row.update(
                status="ok",
                batch_status=batch["status"],
                delivered_count=len(delivered),
                reference_in_pool=case["reference_chunk_id"] in diagnostics["hybrid_ids"],
                reference_rerank_rank=(
                    diagnostics["reranked_ids"].index(case["reference_chunk_id"]) + 1
                    if case["reference_chunk_id"] in diagnostics["reranked_ids"]
                    else None
                ),
                reference_delivered_rank=(
                    delivered.index(case["reference_chunk_id"]) + 1
                    if case["reference_chunk_id"] in delivered
                    else None
                ),
                delivered_target_document=sum(
                    by_id[i]["document_sha256"] == suite["document_sha256"] for i in delivered
                ),
                source_structure=diagnostics.get("source_structure", {}).get("structure_status"),
            )
        except Exception as exc:  # noqa: BLE001 - preserve first failure, no retries
            row["error_type"] = type(exc).__name__
        finally:
            row["artifact_sha256"] = {p.name: file_sha256(p) for p in sorted(folder.iterdir())}
            write_json(output / "results.json", result)
    result["corpus_unchanged"] = result["corpus_sha256"] == canonical_sha256(
        corpus_snapshot([suite["knowledge_base"]])[1]
    )
    result["dataset_unchanged"] = result["manifest"]["dataset_sha256"] == file_sha256(DATASET)
    result["source_unchanged"] = (
        result["manifest"]["source_sha256"] == build_manifest(DATASET, {})["source_sha256"]
    )
    result["status"] = (
        "retrieved"
        if result["corpus_unchanged"]
        and result["dataset_unchanged"]
        and result["source_unchanged"]
        and all(row["status"] == "ok" for row in result["cases"])
        else "invalid"
    )
    write_json(output / "results.json", result)
    return output


def load_retrieved(source):
    suite = load_suite()
    source = safe_path(source)
    path = source / "results.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    corpus_path = source / "corpus.json"
    if (
        result["status"] != "retrieved"
        or result["manifest"]["dataset_sha256"] != file_sha256(DATASET)
        or result["manifest"]["configuration"]["e416_record_sha256"] != file_sha256(E416)
        or result["corpus_file_sha256"] != file_sha256(corpus_path)
        or not all(
            result.get(key) is True
            for key in ("source_unchanged", "dataset_unchanged", "corpus_unchanged")
        )
    ):
        raise ValueError("pbc_saved_retrieval_invalid")
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    if result["corpus_sha256"] != canonical_sha256(corpus):
        raise ValueError("pbc_saved_corpus_changed")
    validate_corpus(suite, corpus)
    hashes = {
        str(path): file_sha256(path),
        str(corpus_path): file_sha256(corpus_path),
        str(DATASET.resolve()): file_sha256(DATASET),
    }
    if [row["id"] for row in result["cases"]] != [
        f"{case['id']}__{variant}" for case, variant in questions(suite)
    ]:
        raise ValueError("pbc_saved_case_set_changed")
    inputs = []
    for row, (case, variant) in zip(result["cases"], questions(suite), strict=True):
        if row["status"] != "ok":
            raise ValueError("pbc_saved_case_failed")
        folder = safe_path(source / row["id"])
        for name in ("retrieval.json", "diagnostics.json"):
            item = safe_path(folder / name)
            if file_sha256(item) != row["artifact_sha256"][name]:
                raise ValueError("pbc_saved_artifact_changed")
            hashes[str(item)] = file_sha256(item)
        batch = json.loads((folder / "retrieval.json").read_text(encoding="utf-8"))
        diagnostics = json.loads((folder / "diagnostics.json").read_text(encoding="utf-8"))
        if (
            batch["query"] != case["question"]
            or diagnostics.get("rerank_applied") is not True
            or diagnostics.get("delivered_ids")
            != [item["metadata"]["chunk_id"] for item in batch["records"]]
            or (
                variant == "experimental"
                and diagnostics.get("source_structure", {}).get("status") != "resolved"
            )
        ):
            raise ValueError("pbc_saved_delivery_binding_changed")
        inputs.append(
            {
                "id": row["id"],
                "question": case["question"],
                "parts": [
                    {"part_id": key, "label": label, "quote_ids": []}
                    for key, label in case["parts"].items()
                ],
                "records": batch["records"],
                "extracts": [],
                "assisted_source_selection": False,
            }
        )
    return inputs, hashes


async def write(source, *, execute=False):
    inputs, hashes = load_retrieved(source)
    return await execute_handoffs(
        inputs,
        hashes,
        execute=execute,
        dataset=DATASET,
        prefix="pbc_clarity_writer",
        selector=select_case,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrieve", action="store_true", help="Run four local RAG queries")
    parser.add_argument("--retrieved-run", type=Path)
    parser.add_argument(
        "--execute", action="store_true", help="Run bounded selector/Writer on saved retrieval"
    )
    args = parser.parse_args()
    if args.execute and args.retrieved_run is None:
        parser.error("--execute requires --retrieved-run")
    if args.retrieve and args.retrieved_run:
        parser.error("choose retrieval or a saved retrieval run")
    print(
        asyncio.run(write(args.retrieved_run, execute=args.execute))
        if args.retrieved_run
        else retrieve(execute=args.retrieve)
    )


if __name__ == "__main__":
    main()
