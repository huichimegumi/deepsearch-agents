"""Run frozen ID selection and Writer on hash-bound E4.16 live evidence."""

import argparse
import asyncio
import json
from pathlib import Path

from evals.reports_acceptance.extended import safe_path
from evals.reports_acceptance.handoff_writer import execute_handoffs
from evals.reports_acceptance.transfer import select_case
from evals.runners.common import ROOT
from evals.runners.experiment import file_sha256

DATASET = Path(__file__).with_name("source_transfer_v1.json")
RETRIEVAL_RECORD = ROOT / "evals/reports/e4-16-new-live-structure-2026-10-29.json"
MAX_CASES = 4


def load_inputs():
    suite = json.loads(DATASET.read_text(encoding="utf-8"))
    cases = suite["cases"]
    if len(cases) != MAX_CASES or len({row["id"] for row in cases}) != MAX_CASES:
        raise ValueError("source_transfer_requires_four_unique_cases")
    record = json.loads(RETRIEVAL_RECORD.read_text(encoding="utf-8"))
    if suite["retrieval_run"] != record["final"]["run"] or record["final"]["passed"] != 5:
        raise ValueError("source_transfer_run_not_final_checked")
    source = safe_path(ROOT / "evals/results" / suite["retrieval_run"])
    result_path = safe_path(source / "results.json")
    if file_sha256(result_path) != record["final"]["results_sha256"]:
        raise ValueError("retrieval_result_hash_changed")
    retrieval = json.loads(result_path.read_text(encoding="utf-8"))
    if (
        retrieval["status"] != "checked"
        or retrieval["manifest"]["dataset_sha256"] != record["dataset_sha256"]
        or not all(
            retrieval[key] for key in ("source_unchanged", "dataset_unchanged", "corpus_unchanged")
        )
    ):
        raise ValueError("retrieval_provenance_invalid")
    saved_cases = {row["id"]: row for row in record["final"]["cases"]}
    hashes = {
        str(DATASET.resolve()): file_sha256(DATASET),
        str(RETRIEVAL_RECORD.resolve()): file_sha256(RETRIEVAL_RECORD),
        str(result_path): file_sha256(result_path),
    }
    inputs = []
    for case in cases:
        row = saved_cases.get(case["id"])
        if row is None or row["status"] != "pass" or not case["parts"]:
            raise ValueError("missing_or_failed_retrieval_case")
        folder = safe_path(source / case["id"])
        paths = {name: safe_path(folder / name) for name in ("retrieval.json", "diagnostics.json")}
        for name, path in paths.items():
            if file_sha256(path) != row["artifact_sha256"][name]:
                raise ValueError("saved_retrieval_artifact_changed")
            hashes[str(path)] = file_sha256(path)
        batch = json.loads(paths["retrieval.json"].read_text(encoding="utf-8"))
        diagnostics = json.loads(paths["diagnostics.json"].read_text(encoding="utf-8"))
        if (
            batch["query"] != case["question"]
            or diagnostics.get("delivered_ids")
            != [item["metadata"]["chunk_id"] for item in batch["records"]]
            or diagnostics.get("rerank_applied") is not True
            or any(item["source"] != "local_document" for item in batch["records"])
        ):
            raise ValueError("saved_evidence_binding_mismatch")
        if case["id"] == "excluded_named_source" and (
            batch["status"] != "NO_EVIDENCE" or batch["records"]
        ):
            raise ValueError("excluded_source_must_have_no_evidence")
        inputs.append(
            {
                "id": case["id"],
                "question": case["question"],
                "parts": [
                    {"part_id": part_id, "label": label, "quote_ids": []}
                    for part_id, label in case["parts"].items()
                ],
                "records": batch["records"],
                "extracts": [],
                "assisted_source_selection": False,
            }
        )
    return inputs, hashes


async def run(*, execute=False):
    inputs, hashes = load_inputs()
    return await execute_handoffs(
        inputs,
        hashes,
        execute=execute,
        dataset=DATASET,
        prefix="source_transfer",
        selector=select_case,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute", action="store_true", help="At most six model calls; no retrieval"
    )
    print(asyncio.run(run(execute=parser.parse_args().execute)))


if __name__ == "__main__":
    main()
