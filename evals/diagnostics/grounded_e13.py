"""One frozen Qwen run of the shared SQL subtask path; references only in scoring."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.research.grounded_query import query_sql
from app.research.grounded_sql import MetricRelations, grounded_context
from app.research.metrics import MetricRegistry
from app.research.query_plan import BoundValue
from evals.diagnostics.audit_e13 import context_audit, name_audit
from evals.diagnostics.compare_e12 import INPUTS, case_dir, catalog
from evals.diagnostics.compare_e12 import snapshot as base_snapshot
from evals.diagnostics.e8 import digest, read
from evals.diagnostics.score_e8 import equivalent, execute_sql
from evals.public_benchmarks.score import model_for
from evals.worker_supervisor import atomic_json

PROTOCOL = Path(__file__).with_name("e13-grounded.lock.json")


def snapshot():
    frozen = base_snapshot()
    protocol = read(PROTOCOL)
    if (
        protocol["provider"] != "qwen"
        or protocol["model"] != "qwen-flash"
        or protocol["cases"] != frozen["protocol"]["cases"]
        or not 1 <= protocol["requests_per_case"] <= 2
        or not 1 <= protocol["reserved_tokens_per_case"] <= 80000
        or protocol["required_matches"] != len(protocol["cases"])
    ):
        raise ValueError("grounded_protocol_not_admitted")
    frozen["protocol"] = protocol
    return frozen


def prepare(output):
    frozen = snapshot()
    tasks = {r["id"]: r for r in read(INPUTS / "public.json")}
    output.mkdir(parents=True, exist_ok=False)
    packets = {}
    for key in frozen["protocol"]["cases"]:
        path = case_dir(output, key)
        path.mkdir()
        _, observed, relations, payload = grounded_context(
            catalog(tasks[key]), tasks[key]["question"], complete_definitions=True
        )
        try:
            values = {name: value.model_dump() for name, value in observed.values.items()}
            atomic_json(path / "input.json", payload)
            atomic_json(path / "values.json", values)
            atomic_json(path / "evidence.json", observed.evidence)
            relation_metadata = {
                "row_counts": relations.counts,
                "projection_sql": relations.queries,
                "metric_sources": relations.sources,
            }
            atomic_json(path / "relations.json", relation_metadata)
            packets[key] = {
                "input_sha256": digest(payload),
                "values_sha256": digest(values),
                "relations_sha256": digest(relation_metadata),
                "evidence_sha256": digest(observed.evidence),
            }
        finally:
            relations.close()
    atomic_json(output / "manifest.json", {"frozen": frozen, "packets": packets})


def validate(output, manifest):
    if snapshot() != manifest["frozen"]:
        raise ValueError("grounded_snapshot_changed")
    if set(manifest["packets"]) != set(manifest["frozen"]["protocol"]["cases"]):
        raise ValueError("grounded_packet_set_changed")
    for key, packet in manifest["packets"].items():
        path = case_dir(output, key)
        for name, expected in packet.items():
            if digest(read(path / f"{name.removesuffix('_sha256')}.json")) != expected:
                raise ValueError("grounded_packet_changed")


def grade(output, manifest, rows):
    """No generation or repair here; all cases must already have terminated."""
    protocol = manifest["frozen"]["protocol"]
    if len(rows) != len(protocol["cases"]) or {r["id"] for r in rows} != set(protocol["cases"]):
        raise ValueError("grounded_incomplete_generation")
    public = {r["id"]: r for r in read(INPUTS / "public.json")}
    references = {r["id"]: r for r in read(INPUTS / "references.json")}
    cases = []
    for row in rows:
        key = row["id"]
        scored = {**row, "strict_match": False}
        if row["status"] in {"executed", "empty"}:
            database = Path(public[key]["catalog"]["sqlite_path"])
            query = references[key]["oracle"]["reference_sql"]
            expected = execute_sql(database, query)
            actual = read(case_dir(output, key) / "query/final-result.json")
            scored["strict_match"] = equivalent(expected, (actual["columns"], actual["rows"]))
            scored["name_audit"] = name_audit(database, query, actual)
            entries = [
                json.loads(line)
                for line in public[key]["catalog"].get("schema_notes", "").splitlines()
                if line.strip()
            ]
            scored["context_audit"] = context_audit(
                entries,
                read(case_dir(output, key) / "input.json"),
                public[key]["question"],
                query,
            )
        cases.append(scored)
    matches = sum(r["strict_match"] for r in cases)
    return {
        "scope": "Exposed SQL subtasks only; not end-to-end or held-out results",
        "provider": "qwen",
        "model": "qwen-flash",
        "manifest_sha256": digest(manifest),
        "source_sha256": manifest["frozen"]["source_sha256"],
        "strict_matches": matches,
        "required_matches": protocol["required_matches"],
        "eligible_for_components": matches >= protocol["required_matches"],
        "requests": sum(r["reservations"]["requests"] for r in rows),
        "reserved_tokens": sum(r["reservations"]["reserved_tokens"] for r in rows),
        "cases": cases,
        "full_components": "NOT RUN",
        "full_development": "NOT RUN",
        "independent_validation": "NOT RUN",
    }


async def run(output):
    manifest = read(output / "manifest.json")
    validate(output, manifest)
    if (output / "started.json").exists():
        raise FileExistsError("grounded_paid_resume_forbidden")
    # Exclusive marker survives interruptions and refuses any paid continuation.
    with (output / "started.json").open("x", encoding="utf-8") as handle:
        handle.write('{"attempt":1}\n')
    model = model_for("qwen")
    tasks = {r["id"]: r for r in read(INPUTS / "public.json")}
    protocol = manifest["frozen"]["protocol"]
    rows = []
    for key in protocol["cases"]:
        validate(output, manifest)
        path = case_dir(output, key)
        source = catalog(tasks[key])
        registry = MetricRegistry(
            source.sqlite_path,
            [json.loads(line) for line in source.schema_notes.splitlines() if line.strip()],
        )
        payload = read(path / "input.json")
        values = {k: BoundValue.model_validate(v) for k, v in read(path / "values.json").items()}
        relations = MetricRelations(registry, [d["table"] for d in payload["datasets"]])
        try:
            metadata = {
                "row_counts": relations.counts,
                "projection_sql": relations.queries,
                "metric_sources": relations.sources,
            }
            if digest(metadata) != manifest["packets"][key]["relations_sha256"]:
                raise ValueError("grounded_materialization_changed")
            result = await query_sql(
                payload,
                relations,
                values,
                path / "query",
                model=model,
                max_requests=protocol["requests_per_case"],
                reserved_tokens=protocol["reserved_tokens_per_case"],
                output_tokens=protocol["output_tokens"],
            )
            rows.append({"id": key, **result})
            atomic_json(output / "generation.json", {"cases": rows})
            print({"completed": len(rows), "status": result["status"]}, flush=True)
        finally:
            relations.close()
    validate(output, manifest)
    summary = grade(output, manifest, rows)
    atomic_json(output / "summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        prepare(args.output)
        print({"prepared": True, "api_calls": 0})
    else:
        summary = asyncio.run(run(args.output))
        print({k: v for k, v in summary.items() if k != "cases"})
