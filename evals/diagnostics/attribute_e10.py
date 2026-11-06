"""Offline clause/protocol signals from exposed E9 controls, with no source text export."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

from evals.diagnostics.e8 import INPUTS, ROOT, digest, read
from evals.diagnostics.e9 import LOCK
from evals.worker_supervisor import atomic_json


def clause_signals(sql, values):
    # These lexical signals guide private review; they are not a SQL equivalence test.
    masked = re.sub(r"'(?:''|[^'])*'|--[^\n]*|/\*.*?\*/", " ", sql, flags=re.S)
    return {
        "aggregate_calls": len(re.findall(r"\b(?:sum|avg|count|min|max)\s*\(", masked, re.I)),
        "arithmetic_operators": len(re.findall(r"[*/+-]", masked)),
        "joins": len(re.findall(r"\bjoin\b", masked, re.I)),
        "window_calls": len(re.findall(r"\bover\s*\(", masked, re.I)),
        "case_expressions": len(re.findall(r"\bcase\b", masked, re.I)),
        "like_predicates": len(re.findall(r"\blike\b", masked, re.I)),
        "wildcard_values_used_in_equality": sum(
            isinstance(value, str)
            and ("%" in value or "_" in value)
            and bool(re.search(r"(?<![<>!=])=\s*:" + re.escape(key) + r"\b", masked))
            for key, value in values.items()
        ),
    }


def missing_dependencies(definitions):
    supplied = {entry["id"] for entry in definitions}
    needed = set()
    for entry in definitions:
        children = entry.get("children_knowledge", [])
        if isinstance(children, int):
            children = [children]
        needed.update(child for child in children if child != -1)
    return len(needed - supplied)


def attribute(sql_run, writer_run, inputs=INPUTS, lock_path=LOCK):
    references, public = read(inputs / "references.json"), read(inputs / "public.json")
    lock = read(lock_path)
    if digest(references) != lock["references_sha256"] or digest(public) != lock["public_sha256"]:
        raise ValueError("attribution_inputs_changed")
    sql_summary, writer_summary = read(sql_run / "summary.json"), read(writer_run / "summary.json")
    sql_ids = {r["id"] for r in references if r["suite"] == "hybrid"}
    if {r["id"] for r in sql_summary["cases"]} != sql_ids:
        raise ValueError("attribution_sql_case_set_changed")
    refs = {r["id"]: r for r in references}
    rows = []
    for row in sql_summary["cases"]:
        path = sql_run / hashlib.sha256(row["id"].encode()).hexdigest()[:16]
        payload = read(path / "assisted-input.json")
        candidates = [read(p)["sql"] for p in sorted(path.glob("intent-*.json"))]
        last = row["attempts"][-1]
        classification = last["status"]
        if classification == "executed":
            classification = (
                "empty_result_mismatch" if last["empty_result"] else "nonempty_result_mismatch"
            )
            if row["sql_result_match"]:
                classification = "matched"
        rows.append(
            {
                "id": row["id"],
                "classification": classification,
                "error_class": last.get("error_class"),
                "reference_signals": clause_signals(refs[row["id"]]["oracle"]["reference_sql"], {}),
                "candidate_signals": [
                    clause_signals(q, payload["resolved_values"]) for q in candidates
                ],
                "identical_retry": len(candidates) > 1 and len(set(candidates)) == 1,
                "missing_direct_definition_dependencies": missing_dependencies(
                    payload["sources"].get("semantic_definitions", [])
                ),
            }
        )
    return {
        "scope": "Exposed development artifact review; lexical differences are signals, not proof of cause or task grades",
        "api_calls": 0,
        "source_sha256": {
            "sql": digest(sql_summary),
            "writer": digest(writer_summary),
            "references": digest(references),
        },
        "sql_cases": rows,
        "writer_cases": [
            {
                "id": row["id"],
                "protocol_pass": row["live_pass"],
                "section_errors": row.get("section_error_count"),
            }
            for row in writer_summary["cases"]
        ],
        "limits": [
            "Unlabelled evaluator-derived literals do not establish correct upstream resolution",
            "No reference SQL, identifiers, literals, questions or source texts exported",
            "Timeout and invalid output do not establish SQL semantic inability",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sql-run", type=Path, default=ROOT / "evals/results/e9-2-assisted-sql")
    parser.add_argument(
        "--writer-run", type=Path, default=ROOT / "evals/results/e9-1-live-replay-v5"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    atomic_json(args.output, attribute(args.sql_run, args.writer_run))
