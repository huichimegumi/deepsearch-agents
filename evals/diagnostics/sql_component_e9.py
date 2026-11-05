"""Reference-literal assisted SQL diagnostic; no report, Web inference or holdout claims."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import re
from pathlib import Path

from app.research.actions import describe
from app.research.bounded import _structured
from app.research.request_budget import RequestBudget, usage
from app.research.sources import SourceCatalog
from app.research.sql_intent import INSTRUCTION, SQLIntent, execute_intent
from app.research.trace import ResearchTrace
from evals.diagnostics.e8 import INPUTS, digest, read
from evals.diagnostics.e9 import LOCK
from evals.diagnostics.score_e8 import equivalent, execute_sql
from evals.public_benchmarks.run import code_hash
from evals.public_benchmarks.score import model_for
from evals.worker_supervisor import atomic_json


def assisted_literals(query):
    values = list(
        dict.fromkeys(
            value[1:-1].replace("''", "'") for value in re.findall(r"'(?:''|[^'])*'", query)
        )
    )
    return {f"v{i + 1}": value for i, value in enumerate(values)}


async def run(output):
    lock = read(LOCK)
    references = [r for r in read(INPUTS / "references.json") if r["suite"] == "hybrid"]
    public = {r["id"]: r for r in read(INPUTS / "public.json")}
    if digest(list(public.values())) != lock["public_sha256"]:
        raise ValueError("component_public_lock_changed")
    if digest(read(INPUTS / "references.json")) != lock["references_sha256"]:
        raise ValueError("component_reference_lock_changed")
    databases = {
        str(Path(row["catalog"]["sqlite_path"]).resolve()): hashlib.sha256(
            Path(row["catalog"]["sqlite_path"]).read_bytes()
        ).hexdigest()
        for row in public.values()
        if row.get("suite") == "hybrid"
    }
    manifest = {
        "version": "e9-sql-component-2",
        "database_sha256": databases,
        "provider": "qwen",
        "references_sha256": digest(references),
        "public_sha256": digest(list(public.values())),
        "source_sha256": code_hash(),
        "scope": lock["component_sql"]["mode"],
        "budget": lock["component_sql"],
    }
    output.mkdir(parents=True, exist_ok=True)
    if (output / "manifest.json").exists() and read(output / "manifest.json") != manifest:
        raise ValueError("sql_component_resume_mismatch")
    atomic_json(output / "manifest.json", manifest)
    model = model_for("qwen")
    rows = []
    for reference in references:
        if code_hash() != manifest["source_sha256"]:
            raise ValueError("sql_component_source_changed")
        if any(
            hashlib.sha256(Path(path).read_bytes()).hexdigest() != sha
            for path, sha in databases.items()
        ):
            raise ValueError("sql_component_database_changed")
        case_id = reference["id"]
        path = output / hashlib.sha256(case_id.encode()).hexdigest()[:16]
        if (path / "summary.json").exists():
            rows.append(read(path / "summary.json"))
            continue
        if path.exists():
            rows.append(
                {
                    "id": case_id,
                    "sql_result_match": False,
                    "status": "interrupted",
                    "requests": usage(path / "requests.jsonl"),
                }
            )
            atomic_json(path / "summary.json", rows[-1])
            continue
        config = dict(public[case_id]["catalog"])
        config["sqlite_path"] = Path(config["sqlite_path"])
        catalog = SourceCatalog(**config)
        values = assisted_literals(reference["oracle"]["reference_sql"])
        # This isolated input intentionally contains evaluator-derived literal hints.
        # It is never written to public.json or reused in production/end-to-end runs.
        payload = {
            "question": public[case_id]["question"],
            "sources": describe(catalog, public[case_id]["question"]),
            "resolved_values": values,
        }
        atomic_json(path / "assisted-input.json", payload)
        budget = RequestBudget(
            path / "requests.jsonl", max_requests=2, max_reserved_tokens=50000, finalizing=True
        )
        attempts, last_parameters, last_query = [], {}, None
        with budget.activate(), ResearchTrace(path).activate():
            try:
                async with asyncio.timeout(250):
                    for attempt in range(2):
                        intent, metadata = await _structured(
                            SQLIntent, INSTRUCTION, payload, model=model, cap=2400
                        )
                        atomic_json(path / f"intent-{attempt + 1}.json", intent.model_dump())
                        try:
                            records, notices, parameters, observation = await asyncio.to_thread(
                                execute_intent, catalog.sqlite_path, intent, values
                            )
                            last_query, last_parameters = intent.sql, parameters
                            atomic_json(
                                path / f"observation-{attempt + 1}.json",
                                {
                                    "records": records,
                                    "notices": notices,
                                    "observation": observation,
                                },
                            )
                            attempts.append({"status": "executed", **observation})
                            if not observation["empty_result"] or attempt:
                                break
                            payload["actual_engine_feedback"] = {
                                "empty_result": True,
                                "prior_intent": intent.model_dump(),
                                "instruction": "Verify actual filter semantics; do not force nonempty results.",
                            }
                        except Exception as exc:
                            attempts.append(
                                {"status": "tool_error", "error_class": type(exc).__name__}
                            )
                            payload["actual_engine_feedback"] = {
                                "error": str(exc),
                                "prior_intent": intent.model_dump(),
                            }
            except Exception as exc:
                attempts.append(
                    {"status": "model_or_runtime_error", "error_class": type(exc).__name__}
                )
        # Reference comparison happens AFTER generation; no gold-match feedback/retry.
        matched, audit_error = False, None
        try:
            expected = execute_sql(catalog.sqlite_path, reference["oracle"]["reference_sql"])
            if last_query is not None:
                matched = equivalent(
                    expected, execute_sql(catalog.sqlite_path, last_query, last_parameters)
                )
        except Exception as exc:
            audit_error = type(exc).__name__
        row = {
            "id": case_id,
            "direction": reference["oracle"]["direction"],
            "status": attempts[-1]["status"] if attempts else "not_started",
            "sql_result_match": bool(matched),
            "attempts": attempts,
            "audit_error": audit_error,
            "provided_literal_count": len(values),
            "reservations": usage(budget.path),
        }
        rows.append(row)
        atomic_json(path / "summary.json", row)
        print(
            {"completed": len(rows), "matched": bool(matched), "status": row["status"]}, flush=True
        )
    matches = sum(row["sql_result_match"] for row in rows)
    summary = {
        "scope": manifest["scope"],
        "scheduled": 6,
        "completed": len(rows),
        "matches": matches,
        "required_matches": 4,
        "gate_passed": len(rows) == 6 and matches >= 4,
        "provider": "qwen",
        "cases": rows,
        "no_gold_match_feedback": True,
        "not_end_to_end": True,
    }
    atomic_json(output / "summary.json", summary)
    print({k: v for k, v in summary.items() if k != "cases"})
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    asyncio.run(run(p.parse_args().output))
