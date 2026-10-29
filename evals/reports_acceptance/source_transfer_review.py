"""Validate a provisional AI source review against immutable Writer and Evidence artifacts."""

import argparse
import json
from collections import Counter
from pathlib import Path

from evals.reports_acceptance.extended import safe_path
from evals.reports_acceptance.source_transfer import DATASET, load_inputs
from evals.runners.common import write_json
from evals.runners.experiment import file_sha256

VERDICTS = {"supported", "partial", "unsupported", "contradicted", "uncertain", "unresolved"}


def validate(generation_run: Path, review_file: Path):
    source = safe_path(generation_run)
    review_file = safe_path(review_file)
    results_path = safe_path(source / "results.json")
    results = json.loads(results_path.read_text(encoding="utf-8"))
    review = json.loads(review_file.read_text(encoding="utf-8"))
    inputs, hashes = load_inputs()
    if (
        results.get("inputs_unchanged") is not True
        or results.get("source_unchanged") is not True
        or results["manifest"]["dataset_sha256"] != file_sha256(DATASET)
        or results["input_sha256"] != hashes
        or review.get("reviewer_type") != "ai_assistant_preliminary"
        or review.get("human_review") != "pending"
        or review.get("generation_results_sha256") != file_sha256(results_path)
    ):
        raise ValueError("source_transfer_review_provenance_invalid")
    by_case = {case["id"]: case for case in inputs}
    if [row["id"] for row in results["cases"]] != [case["id"] for case in inputs]:
        raise ValueError("source_transfer_case_order_changed")
    expected = {}
    outputs = {}
    for row in results["cases"]:
        case_id = row["id"]
        folder = safe_path(source / case_id)
        for name, digest in row["artifact_sha256"].items():
            if file_sha256(safe_path(folder / name)) != digest:
                raise ValueError("generation_artifact_hash_changed")
        audit = json.loads((folder / "assertions.json").read_text(encoding="utf-8"))
        writer_input = json.loads((folder / "writer_inputs.json").read_text(encoding="utf-8"))
        if writer_input["question"] != by_case[case_id]["question"]:
            raise ValueError("writer_question_changed")
        extracts = {item["quote_id"]: item for item in writer_input["extracts"]}
        source_records = {item["evidence_id"]: item for item in by_case[case_id]["records"]}
        for part in audit["parts"]:
            part_id = part["part_id"]
            assertions = part["assertions"]
            for index in range(len(assertions)) if assertions else (None,):
                key = (case_id, part_id, index)
                expected[key] = (
                    assertions[index] if index is not None else None,
                    extracts,
                    source_records,
                )
        outputs[case_id] = row["status"]
    items = review.get("items", [])
    keys = [
        (item.get("case_id"), item.get("part_id"), item.get("assertion_index")) for item in items
    ]
    if Counter(keys) != Counter(expected.keys()):
        raise ValueError("review_must_cover_every_assertion_or_gap_once")
    for item in items:
        key = (item["case_id"], item["part_id"], item["assertion_index"])
        assertion, extracts, records = expected[key]
        verdict = item.get("verdict")
        quotes = item.get("evidence_quotes", [])
        if verdict not in VERDICTS or not str(item.get("reason", "")).strip():
            raise ValueError("invalid_review_verdict_or_reason")
        if assertion is None:
            if verdict != "unresolved" or quotes:
                raise ValueError("unresolved_part_cannot_claim_support")
            continue
        if verdict == "unresolved" or not str(assertion.get("text", "")).strip():
            raise ValueError("assertion_requires_semantic_verdict")
        linked = {extracts[q]["evidence_id"] for q in assertion["quote_ids"]}
        if linked != set(assertion["evidence_ids"]):
            raise ValueError("assertion_quote_link_changed")
        if verdict in {"supported", "partial", "contradicted"} and not quotes:
            raise ValueError("evidence_verdict_requires_source_quote")
        for quote in quotes:
            evidence_id = quote["evidence_id"]
            passage = quote["quote"]
            if (
                evidence_id not in linked
                or evidence_id not in records
                or not isinstance(passage, str)
                or not passage.strip()
                or passage not in records[evidence_id]["content"]
            ):
                raise ValueError("review_quote_not_in_linked_original_evidence")
    return {
        "generation_run": source.name,
        "generation_results_sha256": file_sha256(results_path),
        "review_file_sha256": file_sha256(review_file),
        "reviewer_type": "ai_assistant_preliminary",
        "human_review": "pending",
        "human_accuracy": None,
        "quote_links_valid": True,
        "semantic_verdicts_are_provisional": True,
        "verdict_counts": dict(Counter(item["verdict"] for item in items)),
        "case_statuses": outputs,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generation_run", type=Path)
    parser.add_argument("review_file", type=Path)
    args = parser.parse_args()
    result = validate(args.generation_run, args.review_file)
    target = safe_path(args.review_file.parent / "validated_review.json")
    write_json(target, result)
    print(target)


if __name__ == "__main__":
    main()
