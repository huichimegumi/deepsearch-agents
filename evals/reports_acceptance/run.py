"""Run actual local reports with private evidence snapshots and an unapproved review package."""

import argparse
import asyncio
import json
import time
from dataclasses import asdict, replace
from pathlib import Path

from app.agent.main_agent import run_deep_agent
from app.config import get_settings
from evals.rag.protocol import canonical_sha256
from evals.rag.run_retrieval import corpus_snapshot, validate_annotations
from evals.rag.scoring import validate_cases
from evals.reports_acceptance.scoring import audit_report, review_worksheet
from evals.runners.common import ROOT, load_jsonl, write_json, write_markdown
from evals.runners.experiment import build_manifest, file_sha256, new_run_id

DEFAULT_DATASET = Path(__file__).with_name("local_v1.json")


def load_cases(dataset: Path) -> tuple[dict, list[dict]]:
    suite = json.loads(dataset.read_text(encoding="utf-8"))
    reference_path = (ROOT / suite["reference_dataset"]).resolve()
    if not reference_path.is_relative_to(ROOT / "evals"):
        raise ValueError("Reference dataset must be under evals")
    if file_sha256(reference_path) != suite["reference_sha256"]:
        raise ValueError("Reference dataset changed")
    references = {case["id"]: case for case in load_jsonl(reference_path)}
    cases = [
        {**references[row["reference_id"]], "id": row["id"], "reference_id": row["reference_id"]}
        for row in suite["cases"]
    ]
    validate_cases(cases)
    return suite, cases


async def execute_case(case: dict, prompt: str, session_id: str, directory: Path, timeout: int):
    started = time.monotonic()
    error_type = None
    report = ""
    try:
        limits = replace(
            get_settings().research_budget_limits("deep_report"),
            max_search_queries=0,
            max_fetched_pages=0,
        )
        result = await asyncio.wait_for(
            run_deep_agent(
                prompt,
                session_id=session_id,
                user_id="evals",
                monitor_thread_id=session_id,
                export_evaluation_evidence=True,
                budget_profile_override="deep_report",
                research_limits_override=limits,
            ),
            timeout=timeout,
        )
        report = str(result or "")
    except Exception as exc:  # noqa: BLE001 - persist failures, never provider error text
        error_type = type(exc).__name__
    directory.mkdir()
    write_markdown(directory / "report.md", report)
    session_dir = ROOT / "app" / "output" / "user_evals" / f"session_{session_id}"
    payloads = {}
    for name, filename in (
        ("snapshot", "evaluation_evidence.json"),
        ("trace", "research_trace.json"),
    ):
        path = session_dir / filename
        payloads[name] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    write_json(directory / "evidence.json", payloads["snapshot"] or {"records": []})
    write_json(directory / "trace.json", payloads["trace"] or {})
    write_json(directory / "reference.json", case)
    audit = audit_report(report, payloads["snapshot"], case)
    audit["local_source_scope_met"] = (
        all(source == "local_document" for source in audit["observed_sources"])
        if payloads["snapshot"] is not None
        else None
    )
    write_markdown(directory / "REVIEW.md", review_worksheet(case, audit))
    artifacts = sorted(str(path.relative_to(ROOT)) for path in session_dir.glob("*.md"))
    trace = payloads["trace"] or {}
    return {
        "id": case["id"],
        "session_id": session_id,
        "execution_status": trace.get("status", "missing_trace"),
        "error_type": error_type,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "artifact_paths": artifacts,
        "trace_metrics": trace.get("metrics", {}),
        "failure_reasons": trace.get("failure_reasons", []),
        "local_retrieval": trace.get("local_retrieval"),
        "audit": audit,
        "review_directory": str(directory.relative_to(ROOT)),
        "report_sha256": file_sha256(directory / "report.md"),
        "evidence_sha256": file_sha256(directory / "evidence.json"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--execute", action="store_true", help="Make real configured LLM calls")
    parser.add_argument("--case-id", action="append", help="Explicit subset, recorded in manifest")
    parser.add_argument("--timeout-seconds", type=int, default=330)
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("Timeout must be positive")
    suite, cases = load_cases(args.dataset)
    if args.case_id:
        if set(args.case_id) - {case["id"] for case in cases}:
            parser.error("Unknown case ID")
        cases = [case for case in cases if case["id"] in args.case_id]
    _, corpus = corpus_snapshot(suite["knowledge_bases"])
    validate_annotations(cases, corpus)
    corpus_hash = canonical_sha256(corpus)
    settings = get_settings()
    manifest = build_manifest(
        args.dataset,
        {
            "model": settings.llm_name,
            "selected_cases": [case["id"] for case in cases],
            "prompt_mode": "user_local_scope_only_no_gold_or_hidden_routes",
            "execution_enabled": args.execute,
            "timeout_seconds": args.timeout_seconds,
            "token_scope": "trace_instrumentation_not_total_provider_billing",
            "knowledge_bases": suite["knowledge_bases"],
            "limits": asdict(
                replace(
                    settings.research_budget_limits("deep_report"),
                    max_search_queries=0,
                    max_fetched_pages=0,
                )
            ),
        },
    )
    run_id = new_run_id("report_acceptance")
    directory = ROOT / "evals" / "results" / run_id
    directory.mkdir(parents=True, exist_ok=False)
    result = {
        "run_id": run_id,
        "suite_version": suite["version"],
        "manifest": manifest,
        "corpus_sha256": corpus_hash,
        "annotation_review": suite["annotation_review"],
        "results": [],
        "acceptance": "pending_human_review",
        "generative_answer_accuracy": None,
        "note": "Anchor coverage is not answer correctness or claim entailment.",
    }
    write_json(directory / "results.json", result)
    if args.execute:
        settings.validate_llm()
        for case in cases:
            prompt = suite["prompt_template"].format(question=case["question"])
            row = asyncio.run(
                execute_case(
                    case,
                    prompt,
                    f"{run_id}_{case['id']}",
                    directory / case["id"],
                    args.timeout_seconds,
                )
            )
            result["results"].append(row)
            write_json(directory / "results.json", result)
            print(f"{case['id']}: {row['execution_status']}", flush=True)
    _, final_corpus = corpus_snapshot(suite["knowledge_bases"])
    final_manifest = build_manifest(args.dataset, manifest["configuration"])
    result["inputs_unchanged"] = (
        canonical_sha256(final_corpus) == corpus_hash
        and final_manifest["source_sha256"] == manifest["source_sha256"]
        and final_manifest["dataset_sha256"] == manifest["dataset_sha256"]
    )
    write_json(directory / "results.json", result)
    print(f"Results: {directory / 'results.json'}", flush=True)
    return int(
        not result["inputs_unchanged"]
        or any(
            row["error_type"] or row["execution_status"] != "completed" for row in result["results"]
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
