"""One controlled same-input query-route comparison, separate from end-to-end research."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from pathlib import Path

from app.research.bounded import _structured
from app.research.grounded_sql import (
    BASELINE_INSTRUCTION,
    MetricRelations,
    SQLCandidate,
    grounded_context,
)
from app.research.metric_selection import SELECTION_INSTRUCTION, MetricSelection, execute_selection
from app.research.metrics import MetricRegistry
from app.research.query_plan import BoundValue
from app.research.request_budget import RequestBudget, usage
from app.research.sources import SourceCatalog
from app.research.trace import ResearchTrace
from evals.diagnostics.e8 import INPUTS, digest, read
from evals.diagnostics.e9 import LOCK
from evals.diagnostics.score_e8 import equivalent, execute_sql
from evals.public_benchmarks.run import code_hash
from evals.public_benchmarks.score import model_for
from evals.worker_supervisor import atomic_json

PROTOCOL = Path(__file__).with_name("e12-comparison.lock.json")


def catalog(task):
    config = dict(task["catalog"])
    config["sqlite_path"] = Path(config["sqlite_path"])
    return SourceCatalog(**config)


def snapshot():
    protocol, public, references, lock = (
        read(PROTOCOL),
        read(INPUTS / "public.json"),
        read(INPUTS / "references.json"),
        read(LOCK),
    )
    if protocol["provider"] != "qwen" or protocol["model"] != "qwen-flash":
        raise ValueError("comparison_qwen_only")
    if digest(public) != lock["public_sha256"] or digest(references) != lock["references_sha256"]:
        raise ValueError("comparison_inputs_changed")
    tasks = {r["id"]: r for r in public}
    databases = {tasks[key]["catalog"]["sqlite_path"] for key in protocol["cases"]}
    return {
        "protocol": protocol,
        "source_sha256": code_hash(),
        "public_sha256": digest(public),
        "references_sha256": digest(references),
        "databases": {
            path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in databases
        },
    }


def case_dir(output, key):
    return output / hashlib.sha256(key.encode()).hexdigest()[:16]


def prepare(output):
    frozen = snapshot()
    tasks = {r["id"]: r for r in read(INPUTS / "public.json")}
    output.mkdir(parents=True, exist_ok=False)
    packets = {}
    for key in frozen["protocol"]["cases"]:
        path = case_dir(output, key)
        path.mkdir()
        _, observed, relations, payload = grounded_context(
            catalog(tasks[key]), tasks[key]["question"]
        )
        try:
            values = {name: value.model_dump() for name, value in observed.values.items()}
            atomic_json(path / "input.json", payload)
            atomic_json(path / "values.json", values)
            atomic_json(path / "evidence.json", observed.evidence)
            atomic_json(
                path / "relations.json",
                {
                    "row_counts": relations.counts,
                    "projection_sql": relations.queries,
                    "metric_sources": relations.sources,
                },
            )
            packets[key] = {"input_sha256": digest(payload), "values_sha256": digest(values)}
        finally:
            relations.close()
    atomic_json(output / "manifest.json", {"frozen": frozen, "packets": packets})


def validate(output, manifest, *, backend_revision=False):
    actual, expected = snapshot(), dict(manifest["frozen"])
    if backend_revision:
        actual.pop("source_sha256")
        expected.pop("source_sha256")
    if actual != expected:
        raise ValueError("comparison_snapshot_changed")
    for key, packet in manifest["packets"].items():
        path = case_dir(output, key)
        if (
            digest(read(path / "input.json")) != packet["input_sha256"]
            or digest(read(path / "values.json")) != packet["values_sha256"]
        ):
            raise ValueError("comparison_packet_changed")


async def generate_arm(task, route, payload, values, path, protocol, model):
    path.mkdir()
    budget = RequestBudget(
        path / "requests.jsonl",
        max_requests=protocol["requests_per_arm"],
        max_reserved_tokens=protocol["reserved_tokens_per_arm"],
        finalizing=True,
    )
    row = {
        "id": task["id"],
        "route": route,
        "status": "failed",
        "input_sha256": digest(payload),
        "attempts": [],
    }
    request = dict(payload)
    source = catalog(task)
    registry = MetricRegistry(
        source.sqlite_path,
        [json.loads(line) for line in source.schema_notes.splitlines() if line.strip()],
    )
    relations = MetricRelations(registry, [d["table"] for d in payload["datasets"]])
    try:
        with budget.activate(), ResearchTrace(path).activate():
            async with asyncio.timeout(220):
                for attempt in range(protocol["requests_per_arm"]):
                    schema, instruction = (
                        (MetricSelection, SELECTION_INSTRUCTION)
                        if route == "selection"
                        else (SQLCandidate, BASELINE_INSTRUCTION)
                    )
                    candidate, _ = await _structured(
                        schema, instruction, request, model=model, cap=protocol["output_tokens"]
                    )
                    atomic_json(path / f"candidate-{attempt + 1}.json", candidate.model_dump())
                    try:
                        if route == "selection":
                            if candidate.table not in {d["table"] for d in payload["datasets"]}:
                                raise ValueError("selection_table_not_exposed")
                            records, _, parameters, _, _ = await asyncio.to_thread(
                                execute_selection, registry, candidate, values
                            )
                            query = records[0]["metadata"]["query"]
                            columns, rows = await asyncio.to_thread(
                                execute_sql, source.sqlite_path, query, parameters
                            )
                        else:
                            query = candidate.sql
                            columns, rows = await asyncio.to_thread(
                                relations.execute, query, values
                            )
                        result = {"columns": columns, "rows": rows}
                        atomic_json(path / f"result-{attempt + 1}.json", result)
                        atomic_json(path / "final-result.json", result)
                        row.update(
                            status="executed", column_count=len(columns), row_count=len(rows)
                        )
                        row["attempts"].append({"status": "executed", "empty": not rows})
                        if rows or attempt + 1 == protocol["requests_per_arm"]:
                            break
                        request["actual_engine_feedback"] = {
                            "empty_result": True,
                            "prior_candidate": candidate.model_dump(),
                            "instruction": "Verify scope without weakening requested filters.",
                        }
                    except Exception as exc:
                        row["attempts"].append(
                            {"status": "engine_error", "error_class": type(exc).__name__}
                        )
                        row["status"] = "failed"
                        atomic_json(
                            path / f"error-{attempt + 1}.json",
                            {"error_class": type(exc).__name__, "reason": str(exc)},
                        )
                        request["actual_engine_feedback"] = {
                            "error": str(exc),
                            "prior_candidate": candidate.model_dump(),
                        }
    except Exception as exc:
        row.update(status="failed", error_class=type(exc).__name__)
        atomic_json(path / "error.json", {"error_class": type(exc).__name__, "reason": str(exc)})
    finally:
        relations.close()
    row["reservations"] = usage(budget.path)
    atomic_json(path / "summary.json", row)
    return row


def grade(output, manifest, results):
    """Called only after all model generation is complete; never feeds a repair."""
    protocol = manifest["frozen"]["protocol"]
    pairs = {(key, route) for key in protocol["cases"] for route in protocol["routes"]}
    if len(results) != len(pairs) or {(r["id"], r["route"]) for r in results} != pairs:
        raise ValueError("comparison_arm_set_changed")
    public = {r["id"]: r for r in read(INPUTS / "public.json")}
    references = {r["id"]: r for r in read(INPUTS / "references.json")}
    graded = []
    for row in results:
        matched = False
        if row["status"] == "executed":
            expected = execute_sql(
                Path(public[row["id"]]["catalog"]["sqlite_path"]),
                references[row["id"]]["oracle"]["reference_sql"],
            )
            actual = read(case_dir(output, row["id"]) / row["route"] / "final-result.json")
            matched = equivalent(expected, (actual["columns"], actual["rows"]))
        graded.append({**row, "sql_result_match": bool(matched)})
    scores = {
        route: {
            "matches": sum(r["sql_result_match"] for r in graded if r["route"] == route),
            "runtime_failures": sum(
                r["status"] != "executed" for r in graded if r["route"] == route
            ),
            "requests": sum(r["reservations"]["requests"] for r in graded if r["route"] == route),
        }
        for route in protocol["routes"]
    }
    winner = max(
        protocol["routes"],
        key=lambda route: (
            scores[route]["matches"],
            -scores[route]["runtime_failures"],
            -scores[route]["requests"],
            route == protocol["tie_preference"],
        ),
    )
    return {
        "scope": "Two exposed SQL subtasks, no evaluator hints in generation; never an end-to-end grade",
        "provider": "qwen",
        "manifest_sha256": digest(manifest),
        "route_scores": scores,
        "selected_route": winner,
        "eligible_for_components": scores[winner]["matches"] >= protocol["required_matches"],
        "cases": graded,
        "full_development": "NOT RUN: full component gates still required",
        "new_validation": "NOT RUN: independent development gate still required",
    }


async def run(output):
    manifest = read(output / "manifest.json")
    validate(output, manifest)
    if (output / "started.json").exists():
        raise FileExistsError("comparison_paid_resume_forbidden")
    model = model_for("qwen")
    with (output / "started.json").open("x") as handle:
        handle.write('{"attempt":1}\n')
    tasks = {r["id"]: r for r in read(INPUTS / "public.json")}
    protocol = manifest["frozen"]["protocol"]
    results = []
    for index, key in enumerate(protocol["cases"]):
        path = case_dir(output, key)
        payload = read(path / "input.json")
        values = {
            name: BoundValue.model_validate(value)
            for name, value in read(path / "values.json").items()
        }
        routes = protocol["routes"] if index % 2 == 0 else list(reversed(protocol["routes"]))
        for route in routes:
            validate(output, manifest)
            row = await generate_arm(
                tasks[key], route, payload, values, path / route, protocol, model
            )
            results.append(row)
            atomic_json(output / "generation.json", {"cases": results})
            print({"completed": len(results), "route": route, "status": row["status"]}, flush=True)
    validate(output, manifest)
    summary = grade(output, manifest, results)
    atomic_json(output / "summary.json", summary)
    return summary


def name_diagnostic(database, query, actual):
    """Evaluator-only text signal, never a substitute for the unchanged row grade."""
    pattern = r"REPLACE\s*\(\s*REPLACE\s*\(\s*([A-Za-z_][\w.]*)\s*,\s*'(?:''|[^'])*'\s*,\s*'(?:''|[^'])*'\s*\)\s*,\s*'(?:''|[^'])*'\s*,\s*'(?:''|[^'])*'\s*\)"
    match = re.search(pattern, query, re.I)
    if not match:
        return {"available": False}
    # Preserve reference filters/order; remove only the known name-format projection.
    raw_query = query[: match.start()] + match[1] + query[match.end() :]
    columns, rows = execute_sql(database, raw_query)
    if len(columns) != 1 or len(rows) != 1 or not isinstance(rows[0][0], str):
        return {"available": False}
    texts = {
        value.casefold().strip()
        for row in actual["rows"]
        for value in row
        if isinstance(value, str)
    }
    return {
        "available": True,
        "reference_raw_text_present": rows[0][0].casefold().strip() in texts,
        "scope": "Raw reference-selected name appears in candidate row; not entity-key proof, SQL equivalence or task coverage",
    }


def replay(output, destination):
    """Re-execute exact trace-verified baseline SQL; never create a model or edit SQL."""
    manifest = read(output / "manifest.json")
    validate(output, manifest, backend_revision=True)
    destination.mkdir(parents=True, exist_ok=False)
    public = {r["id"]: r for r in read(INPUTS / "public.json")}
    references = {r["id"]: r for r in read(INPUTS / "references.json")}
    cases = []
    for key in manifest["frozen"]["protocol"]["cases"]:
        path = case_dir(output, key)
        payload = read(path / "input.json")
        values = {
            name: BoundValue.model_validate(value)
            for name, value in read(path / "values.json").items()
        }
        source = catalog(public[key])
        registry = MetricRegistry(
            source.sqlite_path,
            [json.loads(line) for line in source.schema_notes.splitlines() if line.strip()],
        )
        relations = MetricRelations(registry, [d["table"] for d in payload["datasets"]])
        attempts = []
        try:
            for candidate in sorted((path / "projected_sql").glob("candidate-*.json")):
                number = candidate.stem.split("-")[-1]
                saved = read(candidate)
                trace = read(
                    path / "projected_sql/trace" / f"model-{int(number):03d}-response.json"
                )
                if trace["parsed"] != saved:
                    raise ValueError("offline_candidate_trace_changed")
                row = {
                    "attempt": int(number),
                    "candidate_sha256": digest(saved),
                    "status": "failed",
                    "sql_result_match": False,
                }
                try:
                    columns, rows = relations.execute(saved["sql"], values)
                    actual = {"columns": columns, "rows": rows}
                    expected = execute_sql(
                        source.sqlite_path, references[key]["oracle"]["reference_sql"]
                    )
                    row.update(
                        status="executed",
                        column_count=len(columns),
                        row_count=len(rows),
                        sql_result_match=equivalent(expected, (columns, rows)),
                        name_diagnostic=name_diagnostic(
                            source.sqlite_path, references[key]["oracle"]["reference_sql"], actual
                        ),
                    )
                    atomic_json(
                        destination
                        / f"{hashlib.sha256(key.encode()).hexdigest()[:16]}-{number}.json",
                        actual,
                    )
                except Exception as exc:
                    row["error_class"] = type(exc).__name__
                attempts.append(row)
            if not attempts:
                raise ValueError("offline_no_saved_baseline_candidate")
            cases.append({"id": key, "attempts": attempts, "last_attempt": attempts[-1]})
        finally:
            relations.close()
    summary = {
        "scope": "Exact saved baseline SQL after backend revision, not new live results; last attempt only, no best-attempt selection",
        "api_calls": 0,
        "source_sha256": code_hash(),
        "original_manifest_sha256": digest(manifest),
        "last_attempt_matches": sum(c["last_attempt"]["sql_result_match"] for c in cases),
        "cases": cases,
    }
    atomic_json(destination / "summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument(
        "--offline-replay",
        type=Path,
        help="Write backend replay to a NEW directory, without model calls",
    )
    args = parser.parse_args()
    if args.offline_replay:
        summary = replay(args.output, args.offline_replay)
        print(
            {
                "offline_replay": True,
                "api_calls": 0,
                "last_attempt_matches": summary["last_attempt_matches"],
            }
        )
    elif args.prepare:
        prepare(args.output)
        print({"prepared": True, "api_calls": 0})
    else:
        summary = asyncio.run(run(args.output))
        print({key: value for key, value in summary.items() if key != "cases"})
