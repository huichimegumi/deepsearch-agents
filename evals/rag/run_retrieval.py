"""Run paired A/B/C retrieval experiments against the real PostgreSQL/Qdrant stack."""

import argparse
import hashlib
import json
import statistics
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

from sqlalchemy import select

from app.rag.config import get_rag_settings
from app.rag.database import session_scope
from app.rag.embeddings import embed_query, rerank_with_status
from app.rag.models import Chunk, Document, KnowledgeBase
from app.rag.retrieval import collect_candidates
from evals.rag.scoring import matches, normalized, passage_sha256, score_retrieval, validate_cases
from evals.runners.common import RESULTS_DIR, load_jsonl, now_utc, write_json, write_markdown
from evals.runners.experiment import build_manifest, file_sha256, new_run_id

DEFAULT_DATASET = Path(__file__).with_name("pilot_dev.jsonl")


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def describe_hit(row) -> dict:
    chunk, document = row
    return {
        "chunk_id": chunk.id,
        "document_sha256": document.sha256,
        "filename": document.filename,
        "chunk_index": chunk.chunk_index,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "content_sha256": passage_sha256(chunk.content),
        "content": chunk.content,
    }


def corpus_snapshot(names: list[str]) -> tuple[list[str], list[dict]]:
    with session_scope() as session:
        bases = session.scalars(select(KnowledgeBase).where(KnowledgeBase.name.in_(names))).all()
        if {base.name for base in bases} != set(names):
            raise ValueError("An explicitly selected knowledge base does not exist")
        ids = sorted(base.id for base in bases)
        rows = session.execute(
            select(Chunk, Document)
            .join(Document, Document.id == Chunk.document_id)
            .where(Chunk.knowledge_base_id.in_(ids), Document.status == "ready")
        ).all()
        snapshot = [describe_hit(row) for row in rows]
    if not snapshot:
        raise ValueError("Selected corpus has no ready chunks")
    return ids, sorted(snapshot, key=lambda row: (row["document_sha256"], row["chunk_index"]))


def validate_annotations(cases: list[dict], snapshot: list[dict]) -> None:
    validate_cases(cases)
    for case in cases:
        for unit in case["evidence_units"]:
            if not any(matches(unit, hit) for hit in snapshot):
                raise ValueError(f"Unresolved evidence anchor: {case['id']}/{unit['id']}")
        for term in case.get("absent_terms", []):
            if any(normalized(term) in normalized(hit["content"]) for hit in snapshot):
                raise ValueError(f"No-answer literal absence check failed: {case['id']}")


def _ranked_hits(pool, ids: list[str]) -> list[dict]:
    return [describe_hit(pool.rows[chunk_id]) for chunk_id in ids]


def evaluate_case(case: dict, knowledge_base_ids: list[str]) -> list[dict]:
    rows = []
    hybrid_pool = None
    hybrid_ms = 0.0
    for mode in ("A_vector", "B_hybrid", "C_hybrid_rerank"):
        started = perf_counter()
        try:
            rerank_status = None
            if mode == "A_vector":
                pool = collect_candidates(
                    case["question"], knowledge_base_ids, include_lexical=False
                )
                ids = pool.vector_ids
            elif mode == "B_hybrid":
                pool = hybrid_pool = collect_candidates(case["question"], knowledge_base_ids)
                ids = pool.hybrid_ids
                hybrid_ms = (perf_counter() - started) * 1000
            else:
                if hybrid_pool is None:
                    raise ValueError("Hybrid candidate pool was unavailable")
                pool = hybrid_pool
                reranking = rerank_with_status(
                    case["question"], [pool.rows[i][0].content for i in pool.hybrid_ids]
                )
                rerank_status = {
                    "model": reranking.model,
                    "applied": reranking.applied,
                    "error_type": reranking.error_type,
                }
                ids = sorted(
                    zip(pool.hybrid_ids, reranking.scores, strict=True),
                    key=lambda pair: pair[1],
                    reverse=True,
                )
                ids = [chunk_id for chunk_id, _ in ids]
            hits = _ranked_hits(pool, ids[:5])
            valid = mode != "C_hybrid_rerank" or bool(rerank_status["applied"])
            candidate_ids = pool.vector_ids if mode == "A_vector" else pool.hybrid_ids
            row = {
                "case_id": case["id"],
                "mode": mode,
                "status": "ok" if valid else "invalid_reranker",
                "metrics": score_retrieval(case, hits) if valid else None,
                "elapsed_ms": round(
                    (perf_counter() - started) * 1000
                    + (hybrid_ms if mode == "C_hybrid_rerank" else 0),
                    3,
                ),
                "candidate_count": len(candidate_ids),
                "candidate_pool_sha256": digest(
                    [(pool.rows[i][1].sha256, pool.rows[i][0].chunk_index) for i in candidate_ids]
                ),
                "reranker": rerank_status,
                "top_hits": hits,
            }
        except Exception as exc:
            row = {
                "case_id": case["id"],
                "mode": mode,
                "status": "blocked",
                "error_type": type(exc).__name__,
                "metrics": None,
            }
        rows.append(row)
    return rows


def summarize(rows: list[dict]) -> dict:
    summary = {}
    for mode in ("A_vector", "B_hybrid", "C_hybrid_rerank"):
        selected = [row for row in rows if row["mode"] == mode]
        valid = [row for row in selected if row["status"] == "ok"]
        answerable = [row for row in valid if not row["metrics"]["no_answer"]]
        summary[mode] = {
            "scheduled": len(selected),
            "valid": len(valid),
            "blocked_or_invalid": len(selected) - len(valid),
            "scored_answerable": len(answerable),
            "no_answer_cases": sum(row["metrics"]["no_answer"] for row in valid),
            "recall_at_5": statistics.mean(row["metrics"]["recall_at_5"] for row in answerable)
            if answerable
            else None,
            "mrr_at_5": statistics.mean(row["metrics"]["mrr_at_5"] for row in answerable)
            if answerable
            else None,
            "all_evidence_found_rate": statistics.mean(
                row["metrics"]["all_evidence_found"] for row in answerable
            )
            if answerable
            else None,
            "median_elapsed_ms": statistics.median(row["elapsed_ms"] for row in valid)
            if valid
            else None,
        }
    return summary


def summary_markdown(report: dict) -> str:
    lines = [
        "# RAG evidence retrieval pilot",
        "",
        f"Run: `{report['run_id']}`; source: `{report['manifest']['git_commit']}`; "
        f"dirty: `{report['manifest']['git_dirty']}`.",
        "",
        "Development diagnostic only. Source-verified draft labels have not been human reviewed.",
        "No-answer cases do not enter Recall/MRR denominators; abstention is not evaluated.",
        "",
        "| Mode | Valid/scheduled | Answerable | Recall@5 | MRR@5 | All evidence | Median ms |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode, metrics in report["summary"].items():

        def number(key):
            return f"{metrics[key]:.3f}" if metrics[key] is not None else "N/A"

        lines.append(
            f"| {mode} | {metrics['valid']}/{metrics['scheduled']} | "
            f"{metrics['scored_answerable']} | {number('recall_at_5')} | {number('mrr_at_5')} | "
            f"{number('all_evidence_found_rate')} | {number('median_elapsed_ms')} |"
        )
    lines += ["", "| Case | Mode | Status | Recall@5 | MRR@5 |", "| --- | --- | --- | --- | --- |"]
    for row in report["results"]:
        metrics = row.get("metrics") or {}
        lines.append(
            f"| {row['case_id']} | {row['mode']} | {row['status']} | "
            f"{metrics.get('recall_at_5')} | {metrics.get('mrr_at_5')} |"
        )
    return "\n".join(lines) + "\n"


def run(dataset: Path, knowledge_base_names: list[str], split: str = "dev") -> dict:
    cases = [case for case in load_jsonl(dataset) if case["split"] == split]
    if not cases:
        raise ValueError("No cases in selected split")
    ids, snapshot = corpus_snapshot(knowledge_base_names)
    validate_annotations(cases, snapshot)
    settings = get_rag_settings()
    configuration = {
        key: getattr(settings, key)
        for key in (
            "embedding_model",
            "rerank_model",
            "chunk_size",
            "chunk_overlap",
            "vector_top_k",
            "lexical_top_k",
            "qdrant_collection",
        )
    }
    configuration.update(
        {
            "split": split,
            "top_k": 5,
            "knowledge_base_names": knowledge_base_names,
            "relevance_threshold": None,
            "score_scope": "rank_only",
            "legacy_index_embedding_provenance": "not_recorded_by_original_indexer",
            "annotation_review": "source_verified_by_agent_pending_human_review",
            "timing_scope": "warm_sequential_local_inference; C includes shared B recall time",
        }
    )
    model_files = []
    cache = Path(settings.fastembed_cache_path or ".fastembed_cache")
    for path in sorted(cache.rglob("*")):
        if path.is_file() and path.suffix in {".onnx", ".json"}:
            model_files.append({"path": str(path.relative_to(cache)), "sha256": file_sha256(path)})
    started = perf_counter()
    embed_query("检索评测预热")
    warmup = rerank_with_status("检索评测预热", ["这是用于模型预热的文本。"])
    warmup_ms = round((perf_counter() - started) * 1000, 3)
    corpus_ids = [
        (hit["document_sha256"], hit["chunk_index"], hit["content_sha256"]) for hit in snapshot
    ]
    rows = [row for case in cases for row in evaluate_case(case, ids)]
    final_ids, final_snapshot = corpus_snapshot(knowledge_base_names)
    corpus_changed = ids != final_ids or corpus_ids != [
        (hit["document_sha256"], hit["chunk_index"], hit["content_sha256"])
        for hit in final_snapshot
    ]
    if corpus_changed:
        for row in rows:
            row.update(status="invalid_corpus_changed", metrics=None)
    return {
        "run_id": new_run_id("rag"),
        "generated_at": now_utc(),
        "manifest": build_manifest(dataset, configuration),
        "corpus_sha256": digest(corpus_ids),
        "corpus_chunks": len(snapshot),
        "corpus_documents": len({hit["document_sha256"] for hit in snapshot}),
        "model_artifacts": model_files,
        "warmup_ms": warmup_ms,
        "reranker_warmup": {key: value for key, value in asdict(warmup).items() if key != "scores"},
        "annotation_snapshot": cases,
        "summary": summarize(rows),
        "results": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--knowledge-base", action="append", required=True)
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    args = parser.parse_args()
    report = run(args.dataset, args.knowledge_base, args.split)
    output = RESULTS_DIR / report["run_id"]
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "results.json", report)
    write_markdown(output / "summary.md", summary_markdown(report))
    print(json.dumps({"output": str(output), "summary": report["summary"]}, ensure_ascii=False))
    return 0 if all(row["status"] == "ok" for row in report["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
