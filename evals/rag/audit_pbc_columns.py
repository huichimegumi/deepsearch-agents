"""Offline stage positions for five structural probes in one saved PBC retrieval."""

import argparse
import json
import math
from pathlib import Path

from evals.rag.protocol import canonical_sha256
from evals.runners.common import ROOT, write_json
from evals.runners.experiment import build_manifest, file_sha256, new_run_id

DATASET = Path(__file__).with_name("suites") / "pbc_column_probes_v1.json"
RETRIEVAL_RECORD = ROOT / "evals/reports/e4-16-new-live-structure-2026-10-29.json"
CORPUS_RECORD = ROOT / "evals/reports/e4-9-vector-retention-2026-10-28.json"
TRANSFER_RECORD = ROOT / "evals/reports/e4-17-source-transfer-2026-10-29.json"
LIVE_SUITE = ROOT / "evals/rag/suites/source_structure_live_v1.json"
TRANSFER_SUITE = ROOT / "evals/reports_acceptance/source_transfer_v1.json"
FINANCE_FILENAMES = {
    "中国人民银行2025年第四季度中国货币政策执行报告63页.pdf",
    "贝莱德BlackRock2026年全球投资展望报告17页.pdf",
    "长江商学院2025年投资者情绪问卷调查CKISS四季度报告63页.pdf",
}


def position(ids, chunk_id):
    return ids.index(chunk_id) + 1 if chunk_id in ids else None


def attribute_probe(chunk_id, diagnostics, corpus, target_sha):
    """Stage identity only; a heading hit does not imply answer support."""
    vector = diagnostics["vector_ids"]
    hybrid = diagnostics["hybrid_ids"]
    ranked = diagnostics["reranked_ids"]
    scores = diagnostics["rerank_scores"]
    selected = diagnostics["source_structure"]["selected_ids"]
    delivered = diagnostics["delivered_ids"]
    if (
        diagnostics["rerank_applied"] is not True
        or len(hybrid) != len(set(hybrid))
        or set(ranked) != set(hybrid) == set(scores)
        or any(i not in corpus or not math.isfinite(scores[i]) for i in ranked)
        or any(scores[a] < scores[b] for a, b in zip(ranked, ranked[1:]))
        or any(corpus[i]["document_sha256"] != target_sha for i in selected)
        or selected
        != [i for i in ranked if corpus[i]["document_sha256"] == target_sha and scores[i] >= 1][:8]
        or delivered != selected[: len(delivered)]
        or len(delivered) > 6
    ):
        raise ValueError("saved_stage_binding_invalid")
    if chunk_id not in corpus:
        loss = "corpus_reference_absent"
    elif chunk_id not in hybrid:
        loss = "candidate_pool"
    elif scores[chunk_id] < 1:
        loss = "score_threshold"
    elif chunk_id not in selected:
        loss = "retained_top8"
    elif chunk_id not in delivered:
        loss = "delivery_budget"
    else:
        loss = "delivered"
    return {
        "chunk_id": chunk_id,
        "first_loss": loss,
        "vector_rank": position(vector, chunk_id),
        "hybrid_rank": position(hybrid, chunk_id),
        "rerank_rank": position(ranked, chunk_id),
        "rerank_score": scores.get(chunk_id),
        "selected_rank": position(selected, chunk_id),
        "delivered_rank": position(delivered, chunk_id),
    }


def load_inputs():
    suite = json.loads(DATASET.read_text(encoding="utf-8"))
    probes = suite["probes"]
    if (
        len(probes) != 5
        or len({p["id"] for p in probes}) != 5
        or len({p["chunk_id"] for p in probes}) != 5
    ):
        raise ValueError("invalid_fixed_probe_set")
    retrieval_record = json.loads(RETRIEVAL_RECORD.read_text(encoding="utf-8"))
    corpus_record = json.loads(CORPUS_RECORD.read_text(encoding="utf-8"))
    transfer_record = json.loads(TRANSFER_RECORD.read_text(encoding="utf-8"))
    run = ROOT / "evals/results" / retrieval_record["final"]["run"]
    result_path = run / "results.json"
    case_id = suite["retrieval_case_id"]
    case_row = next(row for row in retrieval_record["final"]["cases"] if row["id"] == case_id)
    folder = run / case_id
    retrieval_path = folder / "retrieval.json"
    diagnostics_path = folder / "diagnostics.json"
    corpus_path = ROOT / "evals/results" / corpus_record["live_run"] / "corpus.json"
    transfer_run = ROOT / "evals/results" / transfer_record["generation"]["run"]
    transfer_results_path = transfer_run / "results.json"
    selection_path = transfer_run / case_id / "selection.json"
    paths = {
        DATASET: file_sha256(DATASET),
        RETRIEVAL_RECORD: file_sha256(RETRIEVAL_RECORD),
        CORPUS_RECORD: file_sha256(CORPUS_RECORD),
        TRANSFER_RECORD: file_sha256(TRANSFER_RECORD),
        LIVE_SUITE: retrieval_record["dataset_sha256"],
        TRANSFER_SUITE: transfer_record["dataset_sha256"],
        result_path: retrieval_record["final"]["results_sha256"],
        retrieval_path: case_row["artifact_sha256"]["retrieval.json"],
        diagnostics_path: case_row["artifact_sha256"]["diagnostics.json"],
        corpus_path: corpus_record["corpus_file_sha256"],
        transfer_results_path: transfer_record["generation"]["results_sha256"],
        selection_path: next(
            row["artifact_sha256"]["selection.json"]
            for row in transfer_record["generation"]["cases"]
            if row["id"] == case_id
        ),
    }
    if any(file_sha256(path) != digest for path, digest in paths.items()):
        raise ValueError("fixed_audit_input_hash_changed")
    if (
        retrieval_record["dataset_sha256"]
        != json.loads(result_path.read_text(encoding="utf-8"))["manifest"]["dataset_sha256"]
        or transfer_record["dataset_sha256"]
        != json.loads(transfer_results_path.read_text(encoding="utf-8"))["manifest"][
            "dataset_sha256"
        ]
    ):
        raise ValueError("fixed_audit_dataset_changed")
    whole = json.loads(corpus_path.read_text(encoding="utf-8"))
    if canonical_sha256(whole) != corpus_record["corpus_sha256"]:
        raise ValueError("archived_corpus_hash_changed")
    finance = [row for row in whole if row["filename"] in FINANCE_FILENAMES]
    if canonical_sha256(finance) != retrieval_record["final"]["corpus_sha256"]["金融行业"]:
        raise ValueError("finance_corpus_drifted")
    corpus = {row["chunk_id"]: row for row in finance}
    target = suite["document_sha256"]
    for probe in probes:
        row = corpus.get(probe["chunk_id"])
        if row is None or row["document_sha256"] != target or probe["marker"] not in row["content"]:
            raise ValueError("fixed_probe_not_in_target_document")
    batch = json.loads(retrieval_path.read_text(encoding="utf-8"))
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if (
        batch["query"]
        != next(
            row["query"]
            for row in json.loads(LIVE_SUITE.read_text(encoding="utf-8"))["cases"]
            if row["id"] == case_id
        )
        or [row["metadata"]["chunk_id"] for row in batch["records"]] != diagnostics["delivered_ids"]
        or diagnostics["source_structure"]["document_sha256"] != [target]
        or diagnostics["source_structure"]["resolution_methods"] != ["indexed_page_suffix"]
        or diagnostics["source_structure"]["structural_ids"]
        or any(part["evidence_ids"] for part in selection["proposal"]["parts"])
    ):
        raise ValueError("saved_case_or_selection_binding_invalid")
    return suite, corpus, diagnostics, {str(path): digest for path, digest in paths.items()}


def run():
    suite, corpus, diagnostics, hashes = load_inputs()
    output = ROOT / "evals/results" / new_run_id("pbc_column_audit")
    output.mkdir(parents=True, exist_ok=False)
    rows = [
        {
            "id": probe["id"],
            "kind": probe["kind"],
            **attribute_probe(probe["chunk_id"], diagnostics, corpus, suite["document_sha256"]),
        }
        for probe in suite["probes"]
    ]
    result = {
        "manifest": build_manifest(DATASET, {"mode": "offline_fixed_structural_probe_attribution"}),
        "input_sha256": hashes,
        "status": "audited",
        "probes": rows,
        "retrieval_candidates": len(diagnostics["hybrid_ids"]),
        "delivered_records": len(diagnostics["delivered_ids"]),
        "selector_selected_quotes": 0,
        "semantic_answer_reference": "not_defined_for_this_question",
        "local_retrieval_queries": 0,
        "rerank_calls": 0,
        "generator_calls": 0,
        "web_queries": 0,
        "human_accuracy": None,
        "production_default_changed": False,
    }
    result["source_unchanged"] = (
        result["manifest"]["source_sha256"] == build_manifest(DATASET, {})["source_sha256"]
    )
    result["inputs_unchanged"] = all(file_sha256(Path(p)) == h for p, h in hashes.items())
    if not result["source_unchanged"] or not result["inputs_unchanged"]:
        result["status"] = "invalid"
    write_json(output / "results.json", result)
    return output


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(run())


if __name__ == "__main__":
    main()
