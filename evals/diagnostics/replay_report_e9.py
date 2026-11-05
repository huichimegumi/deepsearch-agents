"""Replay frozen collected E8 evidence through E9 reporting; never read gold answers."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
from pathlib import Path

from app.research.compact_report import ResultRegistry, TableSelection, write_report
from app.research.evidence_store import EvidenceStore
from app.research.report import ResearchReport, numeric_binding_errors
from app.research.request_budget import RequestBudget, usage
from app.research.trace import ResearchTrace
from evals.diagnostics.e8 import INPUTS, ROOT, digest, read
from evals.public_benchmarks.score import model_for
from evals.worker_supervisor import atomic_json


def source_hash():
    paths = [
        ROOT / "app/research" / name
        for name in ("compact_report.py", "report.py", "evidence_store.py", "trace.py")
    ]
    return digest([p.read_text() for p in paths] + [Path(__file__).read_text()])


async def run(output, live=False, limit=None):
    saved = read(ROOT / "evals/results/e8-4-recheck/results.json")
    public = {r["id"]: r for r in read(INPUTS / "public.json")}
    config = {
        "version": "e9-writer-control-5",
        "provider": "qwen" if live else "none",
        "source_results_sha256": digest(saved),
        "public_sha256": digest(list(public.values())),
        "code_sha256": source_hash(),
        "scope": "Collected-evidence replay, no oracle, no new retrieval, no end-to-end quality score",
    }
    output.mkdir(parents=True, exist_ok=True)
    if (output / "manifest.json").exists() and read(output / "manifest.json") != config:
        raise ValueError("replay_resume_mismatch")
    atomic_json(output / "manifest.json", config)
    model = model_for("qwen") if live else None
    rows = []
    for result in saved[:limit]:
        if source_hash() != config["code_sha256"]:
            raise ValueError("replay_code_changed")
        case_id = result["id"]
        path = output / hashlib.sha256(case_id.encode()).hexdigest()[:16]
        if (path / "summary.json").exists():
            rows.append(read(path / "summary.json"))
            continue
        store = EvidenceStore(path)
        store.add(result.get("evidence", []), "replay")
        registry = ResultRegistry(store)
        registry.save(path)
        tables = [
            registry.table(TableSelection(table_id=token, title="Actual query result"), None)
            for token, table in registry.tables.items()
            if table["complete"]
        ]
        control = ResearchReport(
            title="Lossless selected result control", answerability="partial", tables=tables
        )
        bindings = numeric_binding_errors(control, list(store.records.values()))
        roundtrip = all(registry.resolve(alias) == key for alias, key in registry.aliases.items())
        atomic_json(path / "lossless-control.json", control.model_dump())
        row = {
            "id": case_id,
            "offline_pass": not bindings and roundtrip,
            "selected_complete_tables": len(tables),
            "copied_rows": sum(len(t.rows) for t in tables),
            "excluded_incomplete_tables": sum(not t["complete"] for t in registry.tables.values()),
            "bindings_valid": not bindings,
            "short_refs_roundtrip": roundtrip,
        }
        if live:
            budget = RequestBudget(
                path / "requests.jsonl", max_requests=3, max_reserved_tokens=60000, finalizing=True
            )
            try:
                with budget.activate(), ResearchTrace(path).activate():
                    async with asyncio.timeout(300):
                        report, responses, errors = await write_report(
                            public[case_id]["question"], store, path / "writer", model=model
                        )
                binding = numeric_binding_errors(report, list(store.records.values()))
                row.update(
                    live_pass=not errors and not binding,
                    section_error_count=len(errors),
                    answerability=report.answerability,
                    claims=len(report.claims),
                    tables=len(report.tables),
                    model_reservations=usage(budget.path),
                    model_finish_reasons=[r.get("finish_reason") for r in responses],
                )
            except Exception as exc:
                row.update(
                    live_pass=False,
                    error_class=type(exc).__name__,
                    model_reservations=usage(budget.path),
                )
        rows.append(row)
        atomic_json(path / "summary.json", row)
        print(
            {
                "completed": len(rows),
                "offline_pass": row["offline_pass"],
                "live_pass": row.get("live_pass"),
            },
            flush=True,
        )
    summary = {
        "scope": config["scope"],
        "scheduled": len(saved),
        "completed": len(rows),
        "offline_passes": sum(r["offline_pass"] for r in rows),
        "live_passes": sum(r.get("live_pass", False) for r in rows) if live else None,
        "gate_passed": len(rows) == 8
        and all(r["offline_pass"] and (not live or r["live_pass"]) for r in rows),
        "cases": rows,
    }
    atomic_json(output / "summary.json", summary)
    print({k: v for k, v in summary.items() if k != "cases"})
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--live", action="store_true")
    p.add_argument("--limit", type=int)
    args = p.parse_args()
    asyncio.run(run(args.output, args.live, args.limit))
