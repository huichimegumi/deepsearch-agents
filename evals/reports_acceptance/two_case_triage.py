"""Validate provisional, quote-grounded review of two delivery-ready reports."""

import argparse
import json
from collections import Counter
from pathlib import Path

from evals.rag.scoring import normalized
from evals.reports_acceptance.ten_case_batch import private_path
from evals.runners.common import ROOT, write_json
from evals.runners.experiment import file_sha256, new_run_id

CASES = ("report_local_001", "report_local_004")
VERDICTS = {"covered_candidate", "partial_candidate", "missing", "uncertain"}


def has_quote(quote: str, source: str) -> bool:
    return bool(normalized(quote)) and normalized(quote) in normalized(source)


def validate(packet_path: Path, review_path: Path) -> dict:
    packet_path, review_path = private_path(packet_path), private_path(review_path)
    batch = json.loads(packet_path.read_text(encoding="utf-8"))
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if (
        [row["id"] for row in batch["rows"] if row["delivery_protocol_ready"]] != list(CASES)
        or review.get("reviewer_type") != "ai_assistant_preliminary"
        or review.get("human_review") != "pending"
        or review.get("packet_sha256") != file_sha256(packet_path)
        or [row["case_id"] for row in review["cases"]] != list(CASES)
    ):
        raise ValueError("Review is not bound to the two delivery-ready cases")
    rows = []
    for entry in review["cases"]:
        case_id = entry["case_id"]
        input_path = packet_path.parent / case_id / "input.json"
        matching = [row for row in batch["rows"] if row["id"] == case_id]
        if file_sha256(input_path) != matching[0]["review_input_sha256"]:
            raise ValueError("Review input hash changed")
        source = json.loads(input_path.read_text(encoding="utf-8"))
        if source["case_id"] != case_id or Counter(
            item["keypoint"] for item in entry["keypoints"]
        ) != Counter(source["answer_keypoints"]):
            raise ValueError("Every frozen keypoint must be reviewed once")
        report = "\n".join(segment["text"] for segment in source["segments"])
        for item in entry["keypoints"]:
            if item["verdict"] not in VERDICTS or not item["reason"].strip():
                raise ValueError("Unknown or unexplained verdict")
            report_quote = item.get("report_quote", "")
            evidence_id = item.get("evidence_id", "")
            evidence_quote = item.get("evidence_quote", "")
            if report_quote and not has_quote(report_quote, report):
                raise ValueError("Invented report quote")
            if item["verdict"] in {"covered_candidate", "partial_candidate"} and not (
                report_quote and evidence_id and evidence_quote
            ):
                raise ValueError("Positive verdict requires actual report and cited source quotes")
            if evidence_id or evidence_quote:
                cited = source["actual_cited_evidence"]
                if evidence_id not in cited or not has_quote(
                    evidence_quote, str(cited[evidence_id]["content"])
                ):
                    raise ValueError("Invented or uncited Evidence quote")
                if not any(
                    evidence_id in segment["cited_ids"] and has_quote(report_quote, segment["text"])
                    for segment in source["segments"]
                ):
                    raise ValueError(
                        "Report quote and Evidence citation belong to different segments"
                    )
        rows.append(
            {
                "id": case_id,
                "keypoints": [
                    {"keypoint_index": index + 1, "verdict": item["verdict"]}
                    for index, item in enumerate(entry["keypoints"])
                ],
                "semantic_acceptance": None,
            }
        )
    return {
        "packet_sha256": file_sha256(packet_path),
        "review_sha256": file_sha256(review_path),
        "reviewer_type": "ai_assistant_preliminary",
        "rows": rows,
        "human_accuracy": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    args = parser.parse_args()
    output = ROOT / "evals/results" / new_run_id("two_case_triage") / "results.json"
    output.parent.mkdir(parents=True, exist_ok=False)
    write_json(output, validate(args.packet, args.review))
    print(output)


if __name__ == "__main__":
    main()
