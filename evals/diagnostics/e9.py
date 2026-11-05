"""Offline E9 protocol and stage attribution over already-exposed E8 artifacts."""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
from collections import Counter
from pathlib import Path

from evals.diagnostics.e8 import INPUTS, ROOT, digest, read
from evals.diagnostics.score_e8 import reference_audit
from evals.worker_supervisor import atomic_json

LOCK = Path(__file__).with_name("e9-dev.lock.json")


def freeze():
    previous = read(Path(__file__).with_name("e8-dev.lock.json"))
    public, references = read(INPUTS / "public.json"), read(INPUTS / "references.json")
    if (
        digest(public) != previous["public_sha256"]
        or digest(references) != previous["references_sha256"]
    ):
        raise ValueError("exposed_inputs_changed")
    config = {
        "version": "e9-dev-1",
        "origin": "E8 exposed cases, development only; E8 closed and unchanged",
        "cases": previous["cases"],
        "public_sha256": digest(public),
        "references_sha256": digest(references),
        "provider": "qwen",
        "model": "qwen-flash",
        "judge_provider": "qwen",
        "budget": previous["budget"],
        "component_sql": {
            "requests_per_case": 2,
            "reserved_tokens_per_case": 50000,
            "required_matches": 4,
            "scheduled": 6,
            "mode": "reference-literal assisted upper-bound diagnostic; never an end-to-end score",
        },
        "gate": {
            "required_passes": 6,
            "scheduled": 8,
            "each_hybrid_direction_required": True,
            "research_runs": 1,
        },
        "rules": [
            "No DeepSeek calls in E9",
            "No new validation before component and development gates",
            "References confined to independent component controls and scorers",
            "Failed judge batches unknown, never zero-filled observed means",
            "CPU only; no paid search",
            "One frozen full development run, no score shopping",
        ],
    }
    if LOCK.exists() and read(LOCK) != config:
        raise ValueError("e9_protocol_changed")
    atomic_json(LOCK, config)
    return config


def accessed_columns(database, query, parameters):
    """Evaluator-side SQLite access trace; a structural signal, not SQL correctness."""
    seen = set()
    with sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True) as conn:
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}

        def authorize(op, table, column, *rest):
            if op == sqlite3.SQLITE_READ:
                seen.add((table, column))
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_OK if op in allowed else sqlite3.SQLITE_DENY

        conn.set_authorizer(authorize)
        import time

        started = time.monotonic()
        conn.set_progress_handler(lambda: int(time.monotonic() - started > 5), 10000)
        conn.execute(query, parameters).fetchmany(1)
    return seen


def diagnose(run):
    results = read(run / "results.json")
    references = {r["id"]: r for r in read(INPUTS / "references.json")}
    public = {r["id"]: r for r in read(INPUTS / "public.json")}
    rows = []
    for result in results:
        key = result["id"]
        attempt = run / hashlib.sha256(key.encode()).hexdigest()[:16] / "attempt-0001"
        records = result.get("evidence", [])
        operations = result.get("operations", [])
        views = [read(p) for p in (attempt / "evidence").glob("context-*.json")]
        viewed = {r["evidence_id"] for view in views for r in view["evidence"]}
        metadata_records = sum(bool(r.get("metadata")) for r in records)
        metadata_viewed = sum(bool(r.get("metadata")) for v in views for r in v["evidence"])
        finishes = Counter(
            read(p).get("metadata", {}).get("finish_reason", "unknown")
            for p in (attempt / "trace").glob("*response.json")
        )
        audit = (
            reference_audit(references[key], result, public[key]["catalog"]["sqlite_path"])
            if result["suite"] == "hybrid"
            else None
        )
        sql_structure = None
        if audit:
            database = public[key]["catalog"]["sqlite_path"]
            expected = accessed_columns(database, references[key]["oracle"]["reference_sql"], {})
            actual = []
            for op in operations:
                if op["source"] == "sql" and op.get("operation") == "query" and "error" not in op:
                    try:
                        actual.append(
                            accessed_columns(database, op["query"], op.get("query_parameters", {}))
                        )
                    except sqlite3.Error:
                        pass
            sql_structure = {
                "executed_queries": len(actual),
                "minimum_missing_reference_tables": min(
                    (len({t for t, c in expected} - {t for t, c in query}) for query in actual),
                    default=None,
                ),
                "minimum_missing_reference_columns": min(
                    (len(expected - query) for query in actual), default=None
                ),
                "caveat": "Matching accessed fields does not prove correct filters, joins, aggregates, or upstream values",
            }
        failures = []
        if not records:
            failures.append("no_collected_evidence")
        if audit and not audit.get("sql_result_match"):
            failures.append("no_matching_sql_result_before_writer")
        if finishes.get("length"):
            failures.append("output_protocol_length_failure")
        if metadata_records and not metadata_viewed:
            failures.append("source_metadata_omitted_from_model_views")
        if result["report"]["answerability"] != "answered":
            failures.append("no_complete_answer")
        rows.append(
            {
                "id": key,
                "status": result["status"],
                "collected_records": len(records),
                "ever_viewed_record_ids": len(viewed),
                "records_with_metadata": metadata_records,
                "view_occurrences_with_metadata": metadata_viewed,
                "successful_query_sources": dict(
                    Counter(
                        o["source"]
                        for o in operations
                        if o.get("operation", "query") == "query"
                        and o.get("record_count", 0) > 0
                        and "error" not in o
                    )
                ),
                "evidence_bindings": sum(len(o.get("bindings", [])) for o in operations),
                "model_finish_reasons": dict(finishes),
                "sql_audit": audit,
                "sql_access_structure": sql_structure,
                "confirmed_failure_codes": failures,
                "unresolved": [
                    "Upstream Web entity correctness and exact SQL clause errors need evaluator-side record review; not inferred from SQL mismatch alone"
                ],
            }
        )
    return {
        "scope": "Read-only attribution, no API calls or new benchmark tasks; record counts are not relevance/recall",
        "source_result_sha256": digest(results),
        "cases": rows,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, default=ROOT / "evals/results/e8-4-recheck")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    freeze()
    atomic_json(args.output, diagnose(args.run))
    print({"cases": 8, "api_calls": 0, "output": str(args.output)})
