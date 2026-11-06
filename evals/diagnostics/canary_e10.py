"""One frozen Qwen-only canary; keep all questions and candidate data in ignored output."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
from pathlib import Path

from app.research.actions import describe
from app.research.bounded import _structured
from app.research.compact_report import ResultRegistry, write_report
from app.research.evidence_store import EvidenceStore
from app.research.query_plan import (
    PLAN_INSTRUCTION,
    BoundValue,
    QueryPlan,
    compile_plan,
    execute_plan,
)
from app.research.report import numeric_binding_errors
from app.research.request_budget import RequestBudget, usage
from app.research.sources import SourceCatalog
from app.research.trace import ResearchTrace
from evals.diagnostics.e8 import INPUTS, ROOT, digest, read
from evals.diagnostics.e9 import LOCK
from evals.diagnostics.score_e8 import equivalent, execute_sql
from evals.diagnostics.sql_component_e9 import assisted_literals
from evals.public_benchmarks.run import code_hash
from evals.public_benchmarks.score import model_for
from evals.worker_supervisor import atomic_json

PROTOCOL = Path(__file__).with_name("e10-canary.lock.json")
EVIDENCE = ROOT / "evals/results/e8-4-recheck/results.json"


def snapshot():
    public, references, lock = (
        read(INPUTS / "public.json"),
        read(INPUTS / "references.json"),
        read(LOCK),
    )
    if digest(public) != lock["public_sha256"] or digest(references) != lock["references_sha256"]:
        raise ValueError("canary_exposed_inputs_changed")
    protocol = read(PROTOCOL)
    if protocol["provider"] != "qwen" or protocol["model"] != "qwen-flash":
        raise ValueError("canary_qwen_only")
    public_by_id = {row["id"]: row for row in public}
    databases = {
        public_by_id[c["id"]]["catalog"]["sqlite_path"]
        for c in protocol["controls"]
        if c["kind"] == "assisted_sql"
    }
    return {
        "protocol": protocol,
        "code_sha256": code_hash(),
        "public_sha256": digest(public),
        "references_sha256": digest(references),
        "evidence_sha256": digest(read(EVIDENCE)),
        "database_sha256": {
            p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sorted(databases)
        },
    }


def prepare(output):
    manifest = snapshot()
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output / "manifest.json", manifest)
    return manifest


async def run(output):
    manifest = read(output / "manifest.json")
    if snapshot() != manifest:
        raise ValueError("canary_frozen_snapshot_changed")
    # Exclusive creation deliberately forbids resuming an interrupted paid attempt.
    with (output / "started.json").open("x", encoding="utf-8") as handle:
        handle.write('{"attempt":1}\n')
    public = {row["id"]: row for row in read(INPUTS / "public.json")}
    references = {row["id"]: row for row in read(INPUTS / "references.json")}
    evidence = {row["id"]: row for row in read(EVIDENCE)}
    model, results = model_for("qwen"), []
    for control in manifest["protocol"]["controls"]:
        if snapshot() != manifest:
            raise ValueError("canary_snapshot_changed_during_run")
        case_id, kind = control["id"], control["kind"]
        path = output / hashlib.sha256((kind + case_id).encode()).hexdigest()[:16]
        path.mkdir()
        budget = RequestBudget(
            path / "requests.jsonl",
            max_requests=control["requests"],
            max_reserved_tokens=control["reserved_tokens"],
            finalizing=True,
        )
        row = {"id": case_id, "kind": kind, "passed": False}
        try:
            with budget.activate(), ResearchTrace(path).activate():
                async with asyncio.timeout(210):
                    if kind == "assisted_sql":
                        cfg = dict(public[case_id]["catalog"])
                        cfg["sqlite_path"] = Path(cfg["sqlite_path"])
                        catalog = SourceCatalog(**cfg)
                        values = {
                            key: BoundValue(
                                value=value,
                                mode="pattern" if "%" in value or "_" in value else "exact",
                                source_ref=f"evaluator-literal:{key}",
                            )
                            for key, value in assisted_literals(
                                references[case_id]["oracle"]["reference_sql"]
                            ).items()
                        }
                        payload = {
                            "question": public[case_id]["question"],
                            "sources": describe(catalog, public[case_id]["question"]),
                            "resolved_values": {k: v.model_dump() for k, v in values.items()},
                        }
                        atomic_json(path / "input.json", payload)
                        plan, _ = await _structured(
                            QueryPlan, PLAN_INSTRUCTION, payload, model=model, cap=5000
                        )
                        atomic_json(path / "plan.json", plan.model_dump())
                        query, parameters = compile_plan(catalog.sqlite_path, plan, values)
                        atomic_json(
                            path / "compiled.json", {"sql": query, "parameters": parameters}
                        )
                        records, notices, _, observation = await asyncio.to_thread(
                            execute_plan, catalog.sqlite_path, plan, values
                        )
                        atomic_json(
                            path / "observation.json",
                            {"records": records, "notices": notices, "observation": observation},
                        )
                        # Only the independent evaluator sees reference SQL and rows.
                        expected = execute_sql(
                            catalog.sqlite_path, references[case_id]["oracle"]["reference_sql"]
                        )
                        matched = equivalent(
                            expected, execute_sql(catalog.sqlite_path, query, parameters)
                        )
                        row.update(passed=matched, sql_result_match=matched, status="executed")
                    else:
                        store = EvidenceStore(path / "evidence")
                        store.add(evidence[case_id].get("evidence", []), "frozen-replay")
                        registry = ResultRegistry(store)
                        expected_tables = sum(
                            asset["complete"] for asset in registry.tables.values()
                        )
                        report, _, errors = await write_report(
                            public[case_id]["question"],
                            store,
                            path / "writer",
                            model=model,
                            scalar=True,
                        )
                        binding = numeric_binding_errors(report, list(store.records.values()))
                        row.update(
                            passed=not errors
                            and not binding
                            and bool(report.claims)
                            and len(report.tables) == expected_tables,
                            status="assembled",
                            protocol_errors=len(errors),
                            binding_errors=len(binding),
                            accepted_claims=len(report.claims),
                            tables=len(report.tables),
                            answerability=report.answerability,
                        )
        except Exception as exc:
            row.update(status="failed", error_class=type(exc).__name__)
            atomic_json(
                path / "error.json", {"error_class": type(exc).__name__, "reason": str(exc)}
            )
        row["reservations"] = usage(budget.path)
        results.append(row)
        atomic_json(path / "summary.json", row)
        print(
            {
                "completed": len(results),
                "kind": kind,
                "passed": row["passed"],
                "status": row["status"],
            },
            flush=True,
        )
    summary = summarize(results, manifest)
    atomic_json(output / "summary.json", summary)
    return summary


def summarize(results, manifest):
    expected = [(c["id"], c["kind"]) for c in manifest["protocol"]["controls"]]
    if [(r["id"], r["kind"]) for r in results] != expected:
        raise ValueError("canary_case_set_or_order_changed")
    return {
        "version": manifest["protocol"]["version"],
        "provider": "qwen",
        "scope": "Three exposed component diagnostics, not end-to-end quality or full component gate",
        "scheduled": len(expected),
        "completed": len(results),
        "passes": sum(r["passed"] for r in results),
        "canary_passed": all(r["passed"] for r in results),
        "full_development": "NOT RUN: requires full component gates",
        "new_validation": "NOT RUN: requires independent end-to-end development gate",
        "manifest_sha256": digest(manifest),
        "cases": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--prepare", action="store_true", help="Freeze inputs/code with zero model calls"
    )
    args = parser.parse_args()
    if args.prepare:
        prepare(args.output)
        print({"prepared": True, "api_calls": 0})
    else:
        summary = asyncio.run(run(args.output))
        print({k: v for k, v in summary.items() if k != "cases"})
