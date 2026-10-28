"""Paired raw/source-context reranking over immutable saved candidate pools."""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from app.rag.rerank_context import source_context_text
from evals.rag.protocol import canonical_sha256
from evals.rag.run_retention import DATASET, LOCK, load_development, materialize, score, summarize
from evals.runners.common import ROOT, write_json
from evals.runners.experiment import build_manifest, file_sha256, new_run_id


def load_pools(*, diagnostic=False):
    report_path = ROOT / (
        "evals/reports/e4-8-query-stage-diagnostics-2026-10-28.json"
        if diagnostic
        else "evals/reports/e4-9-vector-retention-2026-10-28.json"
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    source = ROOT / "evals/results" / (report["run_id"] if diagnostic else report["live_run"])
    corpus_path = source / "corpus.json"
    if file_sha256(corpus_path) != report["corpus_file_sha256"]:
        raise ValueError("saved_corpus_changed")
    snapshot = json.loads(corpus_path.read_text(encoding="utf-8"))
    corpus = {row["chunk_id"]: row for row in snapshot}
    hashes = {
        str(report_path): file_sha256(report_path),
        str(corpus_path): file_sha256(corpus_path),
    }
    tasks = []
    if diagnostic:
        plan_path = source / "query_plan.json"
        if file_sha256(plan_path) != report["query_plan_sha256"]:
            raise ValueError("diagnostic_query_plan_changed")
        hashes[str(plan_path)] = file_sha256(plan_path)
        plan = {row["id"]: row for row in json.loads(plan_path.read_text(encoding="utf-8"))}
        for case_id in ("transfer_local_001", "transfer_local_002"):
            path = source / case_id / "original.json"
            expected = next(
                row
                for row in report["cases"]
                if row["id"] == case_id and row["variant"] == "original"
            )
            if file_sha256(path) != expected["artifact_sha256"]:
                raise ValueError("diagnostic_pool_changed")
            hashes[str(path)] = file_sha256(path)
            captured = json.loads(path.read_text(encoding="utf-8"))
            tasks.append(
                {
                    "id": case_id,
                    "query": plan[case_id]["original"],
                    "hybrid_ids": captured["diagnostics"]["hybrid_ids"],
                    "cached_delivery_ids": captured["diagnostics"]["delivered_ids"],
                }
            )
    else:
        path = source / "results.json"
        if file_sha256(path) != report["live_results_sha256"]:
            raise ValueError("development_source_changed")
        hashes[str(path)] = file_sha256(path)
        hashes[str(DATASET.resolve())] = file_sha256(DATASET)
        hashes[str(LOCK.resolve())] = file_sha256(LOCK)
        saved = json.loads(path.read_text(encoding="utf-8"))
        cases = load_development()
        if saved["manifest"]["dataset_sha256"] != file_sha256(DATASET) or [
            r["id"] for r in saved["cases"]
        ] != [c["id"] for c in cases]:
            raise ValueError("development_questions_changed")
        for row, case in zip(saved["cases"], cases, strict=True):
            tasks.append(
                {
                    "id": case["id"],
                    "query": case["question"],
                    "case": case,
                    "hybrid_ids": row["diagnostics"]["reranked_ids"],
                    "pool_order_source": "saved_full_rerank_order",
                    "cached_delivery_ids": [
                        h["chunk_id"] for h in row["policies"]["baseline"]["hits"]
                    ],
                }
            )
    for task in tasks:
        if len(task["hybrid_ids"]) != len(set(task["hybrid_ids"])) or any(
            i not in corpus for i in task["hybrid_ids"]
        ):
            raise ValueError("unbound_candidate_pool")
    return tasks, corpus, hashes


def evaluate(task, corpus):
    from app.rag.config import get_rag_settings
    from app.rag.embeddings import rerank_with_status
    from app.rag.retrieval import _filter_ranked_candidates
    from app.tools.local_rag_tools import _limit_hits_for_answer

    settings = get_rag_settings()
    ids = task["hybrid_ids"]
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
    raw_texts = [corpus[i]["content"] for i in ids]
    contextual_texts = [
        source_context_text(
            corpus[i]["content"],
            filename=corpus[i]["filename"],
            page_start=corpus[i]["page_start"],
            page_end=corpus[i]["page_end"],
            section=corpus[i].get("section"),
        )
        for i in ids
    ]
    row = {
        "id": task["id"],
        "status": "ok",
        "local_rerank_calls": 0,
        "candidate_pool_sha256": canonical_sha256(ids),
        "pool_order_source": task.get("pool_order_source", "saved_hybrid_order"),
        "policies": {},
    }
    for name, texts in (("baseline", raw_texts), ("source_context", contextual_texts)):
        row["local_rerank_calls"] += 1
        reranked = rerank_with_status(task["query"], texts)
        if not reranked.applied:
            row.update(status="invalid", error_type="reranker_fallback_not_an_experiment")
            return row
        ranked = sorted(zip(ids, reranked.scores, strict=True), key=lambda x: x[1], reverse=True)
        # The production threshold and top-eight cutoff are applied independently to both formats.
        retained = _filter_ranked_candidates(
            ranked, settings.min_relevance_score, settings.rerank_top_k
        )
        diagnostics = {"rerank_scores": dict(ranked), "rerank_applied": True}
        delivered, budget = _limit_hits_for_answer(
            materialize([i for i, _ in retained], pool, diagnostics)
        )
        hits = [
            {
                "chunk_id": h.chunk_id,
                "document_sha256": h.document_sha256,
                "content": h.content,
                "filename": h.filename,
            }
            for h in delivered
        ]
        row["policies"][name] = {
            "hits": hits,
            "budget": budget,
            "metrics": score(task["case"], hits) if "case" in task else None,
            "reranked_ids": [i for i, _ in ranked],
            "rerank_scores": dict(ranked),
            "rerank_input_sha256": canonical_sha256(texts),
        }
    row["cached_baseline_delivery_equal"] = [
        h["chunk_id"] for h in row["policies"]["baseline"]["hits"]
    ] == task["cached_delivery_ids"]
    return row


def model_artifacts():
    from app.rag.config import get_rag_settings

    cache = Path(get_rag_settings().fastembed_cache_path or ".fastembed_cache")
    expected = json.loads(LOCK.read_text(encoding="utf-8"))["model_artifacts"]
    selected = [entry for entry in expected if "reranker" in entry["path"]]
    if not selected:
        raise ValueError("missing_frozen_reranker_artifacts")
    for entry in selected:
        if file_sha256(cache / entry["path"]) != entry["sha256"]:
            raise ValueError("frozen_reranker_artifact_changed")
    return selected


def run(*, execute=False, diagnostic=False):
    tasks, snapshot, hashes = load_pools(diagnostic=diagnostic)
    output = (
        ROOT
        / "evals/results"
        / new_run_id("context_rerank_diagnostic" if diagnostic else "context_rerank_dev")
    )
    output.mkdir(parents=True, exist_ok=False)
    result = {
        "manifest": build_manifest(
            DATASET,
            {
                "execute": execute,
                "diagnostic": diagnostic,
                "max_local_rerank_calls": len(tasks) * 2,
                "local_queries": 0,
                "generator_calls": 0,
                "input_policy": "source_filename_pages_available_section_v1",
                "test_split_executed": False,
            },
        ),
        "input_sha256": hashes,
        "cases": [],
        "status": "plan_only",
    }
    write_json(output / "results.json", result)
    if not execute:
        return output
    from app.config import get_settings
    from app.rag.config import get_rag_settings

    if (
        get_settings().rag_answer_max_hits != 6
        or get_settings().rag_answer_max_context_chars != 10000
    ):
        raise ValueError("context_budget_changed")
    settings = get_rag_settings()
    if (
        settings.rerank_model
        != json.loads(LOCK.read_text(encoding="utf-8"))["configuration"]["rerank_model"]
    ):
        raise ValueError("reranker_model_changed")
    if settings.min_relevance_score != 1 or settings.rerank_top_k != 8:
        raise ValueError("rerank_cutoffs_changed")
    result["model_artifacts"] = model_artifacts()
    result["reranker_model"] = settings.rerank_model
    result["status"] = "running"
    write_json(output / "results.json", result)
    for task in tasks:
        try:
            row = evaluate(task, snapshot)
        except Exception as exc:  # noqa: BLE001 - preserve failures, no retry
            row = {"id": task["id"], "status": "invalid", "error_type": type(exc).__name__}
        result["cases"].append(row)
        if not diagnostic:
            result["summary"] = summarize(result["cases"], ("baseline", "source_context"))
        write_json(output / "results.json", result)
    result["inputs_unchanged"] = all(file_sha256(Path(p)) == h for p, h in hashes.items())
    result["source_unchanged"] = (
        result["manifest"]["source_sha256"] == build_manifest(DATASET, {})["source_sha256"]
    )
    result["model_artifacts_unchanged"] = result["model_artifacts"] == model_artifacts()
    result["status"] = (
        "evaluated"
        if all(
            result[k] for k in ("inputs_unchanged", "source_unchanged", "model_artifacts_unchanged")
        )
        and all(r["status"] == "ok" for r in result["cases"])
        else "invalid"
    )
    write_json(output / "results.json", result)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute", action="store_true", help="Paired local reranking only; no retrieval/generator"
    )
    parser.add_argument(
        "--diagnostic",
        action="store_true",
        help="Two original-query diagnostic pools instead of dev split",
    )
    args = parser.parse_args()
    print(run(execute=args.execute, diagnostic=args.diagnostic))


if __name__ == "__main__":
    main()
