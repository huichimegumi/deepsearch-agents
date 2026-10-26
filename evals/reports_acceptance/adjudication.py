"""Offline, hash-bound human annotation and adjudication of saved support packets."""

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, field_validator

from evals.reports_acceptance import support_review as support
from evals.runners.common import ROOT, write_json, write_markdown
from evals.runners.experiment import file_sha256, new_run_id

ErrorTag = Literal[
    "scope_overclaim",
    "unsupported_assertion",
    "irrelevant_evidence",
    "missing_citation",
    "source_identity",
    "numeric_error",
    "other",
]


class SegmentAnnotation(support.SegmentReview):
    error_tags: list[ErrorTag]
    correction: str


class Decision(support.SupportReview):
    item_id: str
    segments: list[SegmentAnnotation]
    reference_labels: Literal["confirmed", "uncertain", "incorrect"]
    decision: Literal["accepted", "rejected", "uncertain"]
    decision_reason: str = Field(min_length=1)


class Prior(support.StrictModel):
    path: str
    sha256: str


class Annotation(support.StrictModel):
    schema_version: Literal[1]
    batch_sha256: str
    stage: Literal["annotation", "adjudication"]
    reviewer: str = Field(min_length=1)
    reviewed_at: datetime
    attestation: Literal["I personally reviewed the report and cited evidence"]
    prior_annotations: list[Prior]
    items: list[Decision]

    @field_validator("reviewer")
    @classmethod
    def reviewer_not_blank(cls, value):
        if not value.strip():
            raise ValueError("Reviewer must be identified")
        return value.strip()

    @field_validator("reviewed_at")
    @classmethod
    def timestamp_has_timezone(cls, value):
        if value.tzinfo is None:
            raise ValueError("Review timestamp needs a timezone")
        return value


def private_path(value: str | Path) -> Path:
    path = Path(value)
    path = (path if path.is_absolute() else ROOT / path).resolve()
    if not path.is_relative_to((ROOT / "evals/results").resolve()):
        raise ValueError("Review artifacts must remain under evals/results")
    return path


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_packet(path: Path) -> tuple[dict, dict]:
    """Rebuild the input from original frozen report/Evidence; never query live infrastructure."""
    path = private_path(path)
    packet = read_json(path)
    if packet.get("inputs_unchanged") is not True or packet.get("status") == "invalid_input_drift":
        raise ValueError("Requires a finalized input-stable support packet")
    inputs = private_path(path.parent / "review_input.json")
    if file_sha256(inputs) != packet["review_input_sha256"]:
        raise ValueError("Review input hash mismatch")
    payload = read_json(inputs)
    if packet["review_scope"] != payload["review_scope"]:
        raise ValueError("Packet review scope mismatch")
    original_path = private_path(Path("evals/results") / packet["original_run_id"] / "results.json")
    original = read_json(original_path)
    if original["run_id"] != packet["original_run_id"]:
        raise ValueError("Original run identity mismatch")
    if original.get("inputs_unchanged") is not True or original["manifest"][
        "dataset_sha256"
    ] != file_sha256(support.DEFAULT_DATASET):
        raise ValueError("Original execution must use the frozen stable local suite")
    if original["manifest"] != packet["execution_manifest"]:
        raise ValueError("Execution manifest mismatch")
    _, cases = support.load_cases(support.DEFAULT_DATASET)
    cases = [row for row in cases if row["id"] == packet["case_id"]]
    rows = [row for row in original["results"] if row["id"] == packet["case_id"]]
    if len(cases) != 1 or len(rows) != 1:
        raise ValueError("Expected one known case and executed row")
    directory = private_path(rows[0]["review_directory"])
    for key in ("report", "evidence"):
        artifact = private_path(directory / ("report.md" if key == "report" else "evidence.json"))
        if (
            file_sha256(artifact) != rows[0][key + "_sha256"]
            or packet[key + "_sha256"] != rows[0][key + "_sha256"]
        ):
            raise ValueError("Original report/Evidence hash mismatch")
    report = (directory / "report.md").read_text(encoding="utf-8")
    rebuilt = support.prepare_input(
        report,
        read_json(directory / "evidence.json"),
        cases[0],
        payload["selected_document_inventory"],
        exclude_rejected_drafts=(
            "final_report_citation_validation_failed" in rows[0].get("failure_reasons", [])
            and report.startswith("# Evidence-Validated Partial Result")
        ),
    )
    if payload["review_scope"] == "selected_segments_only":
        rebuilt = support.select_segments(rebuilt, [row["id"] for row in payload["segments"]])
    if rebuilt != payload:
        raise ValueError("Packet differs from its original report, evidence or frozen labels")
    return packet, payload


def load_batch(path: Path) -> tuple[dict, dict]:
    batch = read_json(path)
    if batch["schema_version"] != 1 or not batch["items"]:
        raise ValueError("Invalid or empty batch")
    payloads = {}
    identities = set()
    for item in batch["items"]:
        source = private_path(item["packet_path"])
        if file_sha256(source) != item["packet_sha256"]:
            raise ValueError("Packet changed since batch creation")
        packet, payload = load_packet(source)
        identity = (packet["original_run_id"], packet["case_id"])
        if any(item[key] != packet[key] for key in ("original_run_id", "case_id", "review_scope")):
            raise ValueError("Batch report identity/scope mismatch")
        if item["item_id"] in payloads or identity in identities:
            raise ValueError("Duplicate batch item or report scope")
        identities.add(identity)
        payloads[item["item_id"]] = payload
    return batch, payloads


def initialize(paths: list[Path]) -> Path:
    items, templates = [], []
    for index, path in enumerate(paths, 1):
        path = private_path(path)
        packet, payload = load_packet(path)
        item_id = f"item_{index:03}"
        items.append(
            {
                "item_id": item_id,
                "packet_path": path.relative_to(ROOT).as_posix(),
                "packet_sha256": file_sha256(path),
                "original_run_id": packet["original_run_id"],
                "case_id": packet["case_id"],
                "review_scope": packet["review_scope"],
            }
        )
        templates.append(
            {
                "item_id": item_id,
                "segments": [
                    {
                        "segment_id": row["id"],
                        "verdict": None,
                        "report_quote": "",
                        "evidence_quotes": [],
                        "reason": "",
                        "error_tags": [],
                        "correction": "",
                    }
                    for row in payload["segments"]
                ],
                "keypoints": [
                    {"unit_id": row["id"], "coverage": None, "report_quote": "", "reason": ""}
                    for row in payload["keypoints"]
                ],
                "abstention": None,
                "abstention_report_quote": "",
                "abstention_reason": "",
                "reference_labels": None,
                "decision": None,
                "decision_reason": "",
            }
        )
    directory = ROOT / "evals/results" / new_run_id("human_review")
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / "batch.json"
    write_json(path, {"schema_version": 1, "items": items})
    load_batch(path)  # Reject duplicates before offering a usable template.
    write_json(directory / "annotation.schema.json", Annotation.model_json_schema())
    write_json(
        directory / "annotation.template.json",
        {
            "schema_version": 1,
            "batch_sha256": file_sha256(path),
            "stage": "annotation",
            "reviewer": "",
            "reviewed_at": None,
            "attestation": None,
            "prior_annotations": [],
            "items": templates,
        },
    )
    write_markdown(
        directory / "INSTRUCTIONS.md",
        "# Human review\n\n"
        "Copy annotation.template.json to a new file, then personally read each packet's REVIEW.md "
        "and cited evidence. Fill every segment and keypoint exactly once, quote literal source text, "
        "record error tags/corrections, identify yourself and enter a timezone-aware timestamp. "
        "Do not submit model proposals as human work. Null template values are intentionally invalid. "
        "annotation.schema.json lists allowed values. The attestation must be exactly: "
        "I personally reviewed the report and cited evidence. Example timestamp: 2026-10-26T10:00:00+09:00.\n\n"
        "After annotation, copy it to a new adjudication file, set stage=adjudication, and add "
        "prior_annotations entries with repository-relative path and SHA256 of each original annotation. "
        "Personally resolve disagreements with reasons in the final decisions. The same person may "
        "adjudicate, but that is not an independent review. Preserve prior files.\n\n"
        "Validate: python -m evals.reports_acceptance.adjudication validate --batch <batch.json> "
        "--annotation <filled.json>\n\n"
        "Summarize pending: python -m evals.reports_acceptance.adjudication summarize --batch <batch.json>\n\n"
        "Summarize final: add --adjudication <final.json>. Attestations are self-reported, not authenticated.\n\n"
        + "\n".join(
            f"- {row['item_id']}: {row['packet_path']} (REVIEW.md beside results.json)"
            for row in items
        )
        + "\n",
    )
    return path


def validate_annotation(path: Path, batch_path: Path, *, require_final: bool = False) -> Annotation:
    _, payloads = load_batch(batch_path)
    annotation = Annotation.model_validate(read_json(path))
    if annotation.batch_sha256 != file_sha256(batch_path):
        raise ValueError("Annotation is bound to another batch")
    if Counter(row.item_id for row in annotation.items) != Counter(payloads.keys()):
        raise ValueError("Every batch item must be reviewed exactly once")
    if require_final and annotation.stage != "adjudication":
        raise ValueError("Final summaries require explicit adjudication")
    if annotation.stage == "annotation" and annotation.prior_annotations:
        raise ValueError("Initial annotation cannot contain adjudication inputs")
    if annotation.stage == "adjudication":
        if not annotation.prior_annotations:
            raise ValueError("Adjudication needs at least one prior annotation")
        seen = set()
        for prior in annotation.prior_annotations:
            prior_path = private_path(prior.path)
            if (
                prior_path == path.resolve()
                or prior_path in seen
                or file_sha256(prior_path) != prior.sha256
            ):
                raise ValueError("Invalid, duplicate or changed prior annotation")
            seen.add(prior_path)
            # Reject adjudication chains before recursion, including cycles.
            if read_json(prior_path).get("stage") != "annotation":
                raise ValueError("Prior input must be an initial annotation")
            validate_annotation(prior_path, batch_path)
    for item in annotation.items:
        payload = payloads[item.item_id]
        support.validate_review(item, payload)
        if (
            not item.decision_reason.strip()
            or not item.abstention_reason.strip()
            or any(not row.reason.strip() for row in item.keypoints)
        ):
            raise ValueError("Decision, abstention and keypoint reasons cannot be blank")
        for segment in item.segments:
            if not segment.reason.strip():
                raise ValueError("Segment reasoning cannot be blank")
            failed = segment.verdict in {"partial", "unsupported", "contradicted"}
            if failed and (not segment.error_tags or not segment.correction.strip()):
                raise ValueError("Problem segments need error tags and a correction")
            if segment.verdict == "supported" and segment.error_tags:
                raise ValueError("Supported segments cannot carry error tags")
            if len(segment.error_tags) != len(set(segment.error_tags)):
                raise ValueError("Duplicate error tag")
        uncertain = (
            item.reference_labels != "confirmed"
            or any(row.verdict == "uncertain" for row in item.segments)
            or any(row.coverage == "uncertain" for row in item.keypoints)
            or item.abstention == "uncertain"
        )
        failed = (
            any(row.verdict in {"partial", "unsupported", "contradicted"} for row in item.segments)
            or any(row.coverage in {"partial", "missing"} for row in item.keypoints)
            or item.abstention == "inappropriate"
        )
        if item.decision == "accepted" and (
            uncertain
            or failed
            or payload["review_scope"] != "whole_saved_report_body"
            or not item.segments
        ):
            raise ValueError(
                "Acceptance requires complete, supported, reference-confirmed whole-report review"
            )
        if item.decision == "rejected" and not failed:
            raise ValueError("Rejection requires an explicit recorded failure")
    return annotation


def summarize(batch_path: Path, final_path: Path | None = None) -> dict:
    batch, payloads = load_batch(batch_path)
    final = validate_annotation(final_path, batch_path, require_final=True) if final_path else None
    counts = Counter(item.decision for item in final.items) if final else Counter()
    segment_counts = (
        Counter(row.verdict for item in final.items for row in item.segments)
        if final
        else Counter()
    )
    tags = (
        Counter(tag for item in final.items for row in item.segments for tag in row.error_tags)
        if final
        else Counter()
    )
    whole = (
        [
            item
            for item in final.items
            if payloads[item.item_id]["review_scope"] == "whole_saved_report_body"
        ]
        if final
        else []
    )
    resolved = [
        item
        for item in whole
        if item.decision != "uncertain" and item.reference_labels == "confirmed"
    ]
    prior_reviews = (
        [
            validate_annotation(private_path(prior.path), batch_path)
            for prior in final.prior_annotations
        ]
        if final
        else []
    )
    disagreements = (
        sum(
            len(
                {
                    next(row.decision for row in prior.items if row.item_id == item_id)
                    for prior in prior_reviews
                }
            )
            > 1
            for item_id in payloads
        )
        if final
        else 0
    )
    return {
        "schema_version": 1,
        "batch_sha256": file_sha256(batch_path),
        "adjudication_sha256": file_sha256(final_path) if final_path else None,
        "review_status": "adjudicated_self_attested" if final else "pending_human_review",
        "expected_report_scopes": len(payloads),
        "unique_case_count": len({item["case_id"] for item in batch["items"]}),
        "original_execution_count": len({item["original_run_id"] for item in batch["items"]}),
        "adjudicated_report_scopes": len(final.items) if final else 0,
        "pending_report_scopes": 0 if final else len(payloads),
        "prior_annotation_count": len(prior_reviews),
        "prior_final_decision_disagreement_items": disagreements,
        "same_reviewer_prior_count": sum(
            prior.reviewer == final.reviewer for prior in prior_reviews
        )
        if final
        else 0,
        "decision_counts": dict(counts),
        "segment_verdict_counts": dict(segment_counts),
        "segment_error_tag_counts": dict(tags),
        "acceptance_numerator": sum(item.decision == "accepted" for item in resolved),
        "acceptance_denominator": len(resolved),
        "excluded_from_acceptance_denominator": len(payloads) - len(resolved),
        "acceptance_rate": sum(item.decision == "accepted" for item in resolved) / len(resolved)
        if resolved
        else None,
        "note": "Self-attested human decisions on saved report scopes, not authenticated or necessarily independent; paragraph units are not atomic claims. No population accuracy estimate. Uncertain, selected-scope and unconfirmed-reference items are excluded from the acceptance denominator.",
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--review-results", type=Path, action="append", required=True)
    for name in ("validate", "summarize"):
        command = commands.add_parser(name)
        command.add_argument("--batch", type=Path, required=True)
        command.add_argument(
            "--annotation" if name == "validate" else "--adjudication",
            type=Path,
            required=name == "validate",
        )
    args = parser.parse_args()
    if args.command == "init":
        print(initialize(args.review_results))
    elif args.command == "validate":
        result = validate_annotation(args.annotation, args.batch)
        print(
            json.dumps(
                {
                    "stage": result.stage,
                    "validated_items": len(result.items),
                    "semantic_validation": "self_attested_not_automated",
                }
            )
        )
    else:
        result = summarize(args.batch, args.adjudication)
        directory = ROOT / "evals/results" / new_run_id("human_summary")
        directory.mkdir(parents=True, exist_ok=False)
        write_json(directory / "results.json", result)
        rate = result["acceptance_rate"]
        write_markdown(
            directory / "SUMMARY.md",
            "# Saved-report adjudication summary\n\n"
            f"Status: {result['review_status']}\n\n"
            f"Report scopes: {result['expected_report_scopes']}; adjudicated: {result['adjudicated_report_scopes']}; "
            f"pending: {result['pending_report_scopes']}.\n\n"
            f"Acceptance: {result['acceptance_numerator']}/{result['acceptance_denominator']}; "
            f"rate: {rate if rate is not None else 'unavailable (no eligible adjudications)'}.\n\n"
            "## Recorded segment error tags\n\n"
            + (
                "\n".join(
                    f"- {tag}: {count}" for tag, count in result["segment_error_tag_counts"].items()
                )
                or "No adjudicated error tags."
            )
            + "\n\n"
            + result["note"]
            + "\n",
        )
        print(directory / "results.json")
    return 0


def main() -> int:
    try:
        return _main()
    except ValidationError as exc:
        print(
            json.dumps(
                {
                    "status": "invalid_annotation",
                    "errors": exc.errors(
                        include_input=False, include_context=False, include_url=False
                    ),
                }
            )
        )
    except (ValueError, KeyError, OSError) as exc:
        print(
            json.dumps(
                {
                    "status": "invalid_review_input",
                    "error_type": type(exc).__name__,
                    "reason": str(exc)
                    if isinstance(exc, ValueError)
                    else "Missing, malformed or inaccessible review artifact",
                }
            )
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
