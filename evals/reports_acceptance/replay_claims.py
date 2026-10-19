"""Replay exact saved structured Claim drafts, never regenerate or infer missing inputs."""

import argparse
import json
from collections import Counter
from pathlib import Path

from app.research.claims import validate_claims
from evals.runners.common import ROOT, write_json
from evals.runners.experiment import build_manifest, file_sha256, new_run_id


def validation_counts(report) -> dict:
    return {
        "accepted": len(report.accepted),
        "rejected": len(report.rejected),
        "normalized_evidence_references": report.normalized_evidence_references,
        "issue_counts": dict(
            Counter(issue.code.value for rejected in report.rejected for issue in rejected.issues)
        ),
    }


def replay(report_results: Path) -> dict:
    original = json.loads(report_results.read_text(encoding="utf-8"))
    manifest = build_manifest(
        report_results,
        {
            "mode": "offline_identical_drafts_exact_vs_known_single_bracket_v1",
            "llm_calls": 0,
            "retrieval_calls": 0,
        },
    )
    rows = []
    for row in original["results"]:
        directory = (ROOT / row["review_directory"].replace("\\", "/")).resolve()
        if not directory.is_relative_to((ROOT / "evals/results").resolve()):
            raise ValueError("Review directory must be inside evals/results")
        snapshot_path = directory / "evidence.json"
        if file_sha256(snapshot_path) != row["evidence_sha256"]:
            raise ValueError("Evidence snapshot hash mismatch")
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        if "claim_validation_batches" not in snapshot:
            raise ValueError(
                "Legacy snapshot lacks original structured Claim drafts; cannot replay"
            )
        record_ids = {record["evidence_id"] for record in snapshot["records"]}
        batches = []
        for batch in snapshot["claim_validation_batches"]:
            eligible = batch["available_evidence_ids"]
            if not set(eligible) <= record_ids:
                raise ValueError("Eligible ID absent from saved Evidence records")
            strict = validate_claims(
                batch["drafts"], available_evidence_ids=eligible, normalize_known_wrappers=False
            )
            canonical = validate_claims(batch["drafts"], available_evidence_ids=eligible)
            if (
                len(canonical.accepted) != batch["accepted_count"]
                or len(canonical.rejected) != batch["rejected_count"]
                or canonical.normalized_evidence_references
                != batch["normalized_evidence_references"]
                or batch["policy"] != "known_single_bracket_v1"
            ):
                raise ValueError("Replayed validation differs from recorded live outcome")
            batches.append(
                {"exact": validation_counts(strict), "canonical": validation_counts(canonical)}
            )
        rows.append(
            {
                "id": row["id"],
                "evidence_sha256": row["evidence_sha256"],
                "status": "replayed" if batches else "no_validation_batches",
                "batches": batches,
            }
        )
    if file_sha256(report_results) != manifest["dataset_sha256"]:
        raise ValueError("Execution results changed during replay")
    return {
        "run_id": new_run_id("claim_replay"),
        "original_run_id": original["run_id"],
        "execution_manifest": original["manifest"],
        "replay_manifest": manifest,
        "results": rows,
        "semantic_acceptance": "pending_human_review",
        "note": "Structural reference validation only; not claim entailment or report correctness.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-results", type=Path, required=True)
    args = parser.parse_args()
    result = replay(args.report_results)
    output = ROOT / "evals/results" / result["run_id"] / "results.json"
    output.parent.mkdir(parents=True, exist_ok=False)
    write_json(output, result)
    print(f"Results: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
