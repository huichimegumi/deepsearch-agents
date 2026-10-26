"""Replay a selected lexical delivery policy over saved reports, without model or retrieval."""

import argparse
import json
from pathlib import Path

from app.agent.runtime import ResearchBudget, ResearchBudgetLimits, ResearchRunTrace
from app.research.evidence import EvidenceRecord, EvidenceSource
from app.research.local_scope import POLICY, check_local_absence_scope, enforce_local_absence_scope
from app.research.source_provenance import (
    check_source_filenames,
    document_catalog,
    enforce_local_source_references,
)
from evals.reports_acceptance.run import DEFAULT_DATASET, load_cases
from evals.runners.common import ROOT, write_json, write_markdown
from evals.runners.experiment import build_manifest, file_sha256, new_run_id


def replay(
    report_results: Path, case_ids: list[str] | None = None, *, policy: str = "filename"
) -> dict:
    if policy not in {"filename", "absence_scope"}:
        raise ValueError("Unknown replay policy")
    scope = policy == "absence_scope"
    original = json.loads(report_results.read_text(encoding="utf-8"))
    if original.get("inputs_unchanged") is not True or original["manifest"][
        "dataset_sha256"
    ] != file_sha256(DEFAULT_DATASET):
        raise ValueError("Requires a finalized input-stable frozen local_v1 execution")
    rows = original["results"]
    _, cases = load_cases(DEFAULT_DATASET)
    known = {case["id"] for case in cases}
    if not {row["id"] for row in rows} <= known or len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Unknown or duplicate executed case ID")
    if case_ids:
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("Duplicate selected case ID")
        if not set(case_ids) <= {row["id"] for row in rows}:
            raise ValueError("Selected case was not executed")
        rows = [row for row in rows if row["id"] in case_ids]
    run_id = new_run_id("scope_replay" if scope else "source_replay")
    directory = ROOT / "evals/results" / run_id
    directory.mkdir(parents=True, exist_ok=False)
    manifest = build_manifest(
        report_results,
        {
            "policy": POLICY if scope else "registered_local_filename_v1",
            "mode": "offline_absence_wording_only" if scope else "offline_filename_only",
            "llm_calls": 0,
            "retrieval_calls": 0,
        },
    )
    results = []
    for row in rows:
        private = (ROOT / row["review_directory"].replace("\\", "/")).resolve()
        paths = {
            key: (private / name).resolve()
            for key, name in (("report", "report.md"), ("evidence", "evidence.json"))
        }
        for key, path in paths.items():
            if (
                not path.is_relative_to((ROOT / "evals/results").resolve())
                or file_sha256(path) != row[f"{key}_sha256"]
            ):
                raise ValueError("Saved artifact path/hash mismatch")
        text = paths["report"].read_text(encoding="utf-8")
        snapshot = json.loads(paths["evidence"].read_text(encoding="utf-8"))
        current = ResearchRunTrace(
            "replay",
            row["id"],
            "offline",
            ResearchBudget(ResearchBudgetLimits("offline", 0, 0, 0, 0, 0, 0)),
        )
        current.local_retrieval_required = True
        current.capture_report_source_checks = True
        current.record_evidence(
            tuple(
                EvidenceRecord(
                    evidence_id=item["evidence_id"],
                    source=EvidenceSource(item["source"]),
                    locator=item["locator"],
                    content=item["content"],
                    metadata=item.get("metadata", {}),
                )
                for item in snapshot["records"]
            )
        )
        catalog = document_catalog(current.local_document_records())
        check = (
            check_local_absence_scope
            if scope
            else lambda value: check_source_filenames(value, catalog)
        )
        enforce = enforce_local_absence_scope if scope else enforce_local_source_references
        finding_key = "matched_assertions" if scope else "unverified_filenames"
        before = check(text)
        boundary = enforce(text, current, candidate_kind="saved_report_replay")
        delivered = boundary if boundary is not None else text
        after = check(delivered)
        if after[finding_key]:
            raise ValueError("Backend boundary still matches the selected policy")
        case_dir = directory / row["id"]
        case_dir.mkdir()
        write_markdown(case_dir / "delivered.md", delivered)
        write_json(case_dir / "private_source_check.json", current.export_evidence_snapshot())
        results.append(
            {
                "id": row["id"],
                "status": "withheld" if boundary is not None else "not_flagged",
                "original_report_sha256": row["report_sha256"],
                "evidence_sha256": row["evidence_sha256"],
                "delivered_report_sha256": file_sha256(case_dir / "delivered.md"),
                ("before_scope_matches" if scope else "before_unverified_mentions"): len(
                    before[finding_key]
                ),
                ("after_scope_matches" if scope else "after_unverified_mentions"): len(
                    after[finding_key]
                ),
                "source_filename_count": len(catalog),
                "candidate_unchanged": delivered == text,
            }
        )
    final_manifest = build_manifest(report_results, manifest["configuration"])
    if (
        manifest["dataset_sha256"] != final_manifest["dataset_sha256"]
        or manifest["source_sha256"] != final_manifest["source_sha256"]
    ):
        raise ValueError("Inputs changed during replay")
    result = {
        "run_id": run_id,
        "original_run_id": original["run_id"],
        "manifest": manifest,
        "execution_manifest": original["manifest"],
        "results": results,
        "semantic_acceptance": "pending_human_review",
        "note": "Selected lexical policy only, not entailment, refusal quality, or current-workflow report accuracy.",
    }
    write_json(directory / "results.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-results", type=Path, required=True)
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--policy", choices=["filename", "absence_scope"], default="filename")
    args = parser.parse_args()
    result = replay(args.report_results, args.case_id, policy=args.policy)
    print(f"Results: {ROOT / 'evals/results' / result['run_id'] / 'results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
