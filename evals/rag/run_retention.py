"""Single predeclared vector-head retention experiment on the frozen 20-case dev split."""

import argparse
import copy
import json
import statistics
from pathlib import Path

from app.rag.retention import order_retained_by_rerank, retain_vector_head
from evals.rag.protocol import canonical_sha256
from evals.rag.scoring import score_retrieval, validate_cases
from evals.runners.common import ROOT, load_jsonl, write_json
from evals.runners.experiment import build_manifest, file_sha256, new_run_id

DATASET = Path(__file__).with_name("suites") / "v2/development.jsonl"
LOCK = DATASET.with_name("suite.lock.json")
KNOWLEDGE_BASES = ["电商行业", "金融行业"]
BUDGET = 6
PROTECTED = 3


def load_development():
    cases = load_jsonl(DATASET)
    spec = json.loads(LOCK.read_text(encoding="utf-8"))["datasets"]["dev"]
    if len(cases) != spec["count"] or canonical_sha256(cases) != spec["canonical_sha256"]:
        raise ValueError("frozen_development_changed")
    validate_cases(cases)
    if any(case["split"] != "dev" for case in cases):
        raise ValueError("development_only")
    return cases


def score(case, hits):
    value = score_retrieval(case, hits, k=BUDGET)
    return {
        "recall_at_6": value["recall_at_5"],
        "mrr_at_6": value["mrr_at_5"],
        "all_evidence_found": value["all_evidence_found"],
        "no_answer": value["no_answer"],
        "abstention_evaluated": False,
        "unit_ranks": value.get("evidence_unit_ranks", {}),
    }


def materialize(ids, pool, diagnostics):
    from app.rag.config import get_rag_settings
    from app.rag.retrieval import RetrievedChunk

    model = get_rag_settings().rerank_model
    hits = []
    for chunk_id in ids:
        chunk, document = pool.rows[chunk_id]
        hits.append(
            RetrievedChunk(
                chunk_id=chunk_id,
                content=chunk.content,
                filename=document.filename,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                section=chunk.section,
                score=diagnostics["rerank_scores"][chunk_id],
                document_sha256=document.sha256,
                chunk_index=chunk.chunk_index,
                rerank_model=model,
                rerank_applied=diagnostics["rerank_applied"],
                rerank_error_type=diagnostics.get("rerank_error_type"),
            )
        )
    return hits


def evaluate(case, knowledge_base_ids):
    from app.rag.retrieval import _rank_candidates, collect_candidates
    from app.tools.local_rag_tools import _limit_hits_for_answer

    pool = collect_candidates(case["question"], knowledge_base_ids)
    diagnostics = {}
    baseline = _rank_candidates(
        case["question"], [pool.rows[i] for i in pool.hybrid_ids], diagnostics=diagnostics
    )
    if not diagnostics["rerank_applied"]:
        raise ValueError("reranking_not_applied")
    protected_ids = retain_vector_head(
        pool.vector_ids, [h.chunk_id for h in baseline], budget=BUDGET, protected=PROTECTED
    )
    protected = materialize(protected_ids, pool, diagnostics)
    output = {"id": case["id"], "status": "ok", "policies": {}}
    for name, candidates in (("baseline", baseline), ("protected", protected)):
        delivered, budget = _limit_hits_for_answer(candidates)
        hits = [
            {
                "chunk_id": h.chunk_id,
                "document_sha256": h.document_sha256,
                "content": h.content,
                "filename": h.filename,
            }
            for h in delivered
        ]
        output["policies"][name] = {"metrics": score(case, hits), "budget": budget, "hits": hits}
    output["diagnostics"] = diagnostics
    return output


def summarize(rows, policies=("baseline", "protected")):
    valid = [row for row in rows if row["status"] == "ok"]
    summary = {"scheduled": len(rows), "valid": len(valid), "policies": {}}
    for policy in policies:
        answerable = [
            r["policies"][policy]["metrics"]
            for r in valid
            if not r["policies"][policy]["metrics"]["no_answer"]
        ]
        summary["policies"][policy] = {
            "answerable": len(answerable),
            "recall_at_6": statistics.mean(m["recall_at_6"] for m in answerable)
            if answerable
            else None,
            "mrr_at_6": statistics.mean(m["mrr_at_6"] for m in answerable) if answerable else None,
            "all_evidence_found": sum(m["all_evidence_found"] for m in answerable),
        }
    return summary


def reorder_rows(rows, cases):
    """Post-hoc ordering replay over the exact saved, already-budgeted source texts."""
    output = copy.deepcopy(rows)
    by_case = {case["id"]: case for case in cases}
    for row in output:
        if row["status"] != "ok":
            continue
        policy = copy.deepcopy(row["policies"]["protected"])
        by_id = {hit["chunk_id"]: hit for hit in policy["hits"]}
        order = order_retained_by_rerank(
            [hit["chunk_id"] for hit in policy["hits"]], row["diagnostics"]["reranked_ids"]
        )
        policy["hits"] = [by_id[chunk_id] for chunk_id in order]
        policy["metrics"] = score(by_case[row["id"]], policy["hits"])
        row["policies"]["protected_rerank_order"] = policy
    return output


def replay_ordering(source: Path):
    source = (source if source.is_absolute() else ROOT / source).resolve()
    if not source.is_relative_to((ROOT / "evals/results").resolve()):
        raise ValueError("replay_must_use_private_results")
    path = source / "results.json"
    original = json.loads(path.read_text(encoding="utf-8"))
    cases = load_development()
    if (
        original["status"] != "evaluated"
        or original["manifest"]["configuration"]["delivery_budget"] != BUDGET
        or original["manifest"]["configuration"]["protected_vector_head"] != PROTECTED
        or original["manifest"]["dataset_sha256"] != file_sha256(DATASET)
        or [row["id"] for row in original["cases"]] != [case["id"] for case in cases]
    ):
        raise ValueError("replay_requires_valid_frozen_development_run")
    rows = reorder_rows(original["cases"], cases)
    output = ROOT / "evals/results" / new_run_id("rag_retention_order_replay")
    output.mkdir(parents=True, exist_ok=False)
    write_json(
        output / "results.json",
        {
            "manifest": build_manifest(
                DATASET,
                {
                    "post_hoc_ordering_replay": True,
                    "local_queries": 0,
                    "generator_calls": 0,
                    "source_results_sha256": file_sha256(path),
                    "membership_and_budgeted_text_unchanged": True,
                },
            ),
            "source_run": source.name,
            "cases": rows,
            "summary": summarize(rows, ("baseline", "protected", "protected_rerank_order")),
        },
    )
    return output


def run(*, execute=False):
    cases = load_development()
    output = ROOT / "evals/results" / new_run_id("rag_retention_dev")
    output.mkdir(parents=True, exist_ok=False)
    result = {
        "manifest": build_manifest(
            DATASET,
            {
                "execute": execute,
                "protected_vector_head": PROTECTED,
                "delivery_budget": BUDGET,
                "max_local_queries": len(cases),
                "knowledge_bases": KNOWLEDGE_BASES,
                "generator_calls": 0,
                "score_scope": "finite_units_after_threshold_and_context_budget",
                "test_split_executed": False,
                "suite_lock_sha256": file_sha256(LOCK),
            },
        ),
        "cases": [],
        "status": "plan_only",
    }
    write_json(output / "results.json", result)
    if not execute:
        return output
    from app.config import get_settings
    from app.rag.config import get_rag_settings
    from evals.rag.run_retrieval import corpus_snapshot, validate_annotations

    if get_settings().rag_answer_max_hits != BUDGET:
        raise ValueError("delivery_budget_changed")
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
    result["context_char_budget"] = get_settings().rag_answer_max_context_chars
    ids, snapshot = corpus_snapshot(KNOWLEDGE_BASES)
    validate_annotations(cases, snapshot)
    write_json(output / "corpus.json", snapshot)
    result["corpus_sha256"] = canonical_sha256(snapshot)
    result["status"] = "running"
    write_json(output / "results.json", result)
    for case in cases:
        try:
            row = evaluate(case, ids)
        except Exception as exc:  # noqa: BLE001 - preserve failure, no retries
            row = {"id": case["id"], "status": "invalid", "error_type": type(exc).__name__}
        result["cases"].append(row)
        result["summary"] = summarize(result["cases"])
        write_json(output / "results.json", result)
    result["corpus_unchanged"] = (
        canonical_sha256(corpus_snapshot(KNOWLEDGE_BASES)[1]) == result["corpus_sha256"]
    )
    result["source_unchanged"] = (
        result["manifest"]["source_sha256"] == build_manifest(DATASET, {})["source_sha256"]
    )
    result["dataset_unchanged"] = result["manifest"]["dataset_sha256"] == file_sha256(DATASET)
    result["lock_unchanged"] = result["manifest"]["configuration"][
        "suite_lock_sha256"
    ] == file_sha256(LOCK)
    result["status"] = (
        "evaluated"
        if all(
            result[k]
            for k in ("corpus_unchanged", "source_unchanged", "dataset_unchanged", "lock_unchanged")
        )
        and all(r["status"] == "ok" for r in result["cases"])
        else "invalid"
    )
    write_json(output / "results.json", result)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--execute", action="store_true", help="20 local recall/rerank calls; no generator"
    )
    group.add_argument(
        "--replay-ordering", type=Path, help="Offline post-hoc ordering of saved protected hits"
    )
    args = parser.parse_args()
    print(
        replay_ordering(args.replay_ordering) if args.replay_ordering else run(execute=args.execute)
    )


if __name__ == "__main__":
    main()
