"""Build generator-only task projections and a separate evaluator reference file."""

from __future__ import annotations

import argparse
import json

from evals.benchmark_preflight import DABSTEP_DATABASE
from evals.dabstep.common import default_data_dir as dab_dir
from evals.hybrid.common import default_data_dir as hybrid_dir
from evals.public_benchmarks.prepare import LOCK, ROOT, digest, preflight, read, sources
from evals.worker_supervisor import atomic_json

INPUTS = ROOT / "evals/results/e7-inputs"


def build(development=False):
    if not preflight()["ready"]:
        raise ValueError("public_benchmark_preflight_failed")
    data = sources()
    selection = read(LOCK)["cases"]
    if development:
        old = read(ROOT / "evals/benchmark_v3.json")["source_sets"]
        dab = next(s for s in old if s["name"] == "dabstep_research")["case_ids"][:2]
        hybrid = next(s for s in old if s["name"] == "hybrid_deep_research")["case_ids"]
        selection = [
            {
                "id": f"dabstep:{int(i.rsplit('_', 1)[1])}",
                "source_id": int(i.rsplit("_", 1)[1]),
                "suite": "dabstep",
                "stratum": "development",
            }
            for i in dab
        ]
        selection += [
            {"id": f"hybrid:{i}", "source_id": i, "suite": "hybrid", "stratum": "development"}
            for i in hybrid
        ]
    public, private = [], []
    for item in selection:
        suite = item["suite"]
        raw = next(r for r in data[suite] if r["id"] == item["source_id"])
        if not development and digest(raw) != item["record_sha256"]:
            raise ValueError("task_record_changed")
        if suite == "dabstep":
            question = raw["question"]
            catalog = {
                "sqlite_path": str(DABSTEP_DATABASE.resolve()),
                "allowed_sources": ["sql", "local_document"],
                "documents": [
                    {
                        "title": "Merchant guide",
                        "locator": "dabstep:manual.md",
                        "text": (dab_dir() / "context/manual.md").read_text(encoding="utf-8"),
                    }
                ],
            }
            oracle = {
                "answerable": True,
                "checklist": [
                    line.strip()[2:].strip()
                    for line in raw["checklist"].splitlines()
                    if line.strip().startswith("- ")
                ],
                "reference": "Use checklist and actual source evidence. No independent gold numeric labels are available.",
            }
        elif suite == "hybrid":
            question = raw["final_question"] + (
                "\nPublished hint: " + raw["hint"] if raw.get("hint") else ""
            )
            catalog = {
                "sqlite_path": str((hybrid_dir() / "alien/alien_template.sqlite").resolve()),
                "allowed_sources": ["sql", "web"],
                "schema_notes": (hybrid_dir() / "alien/alien_kb.jsonl").read_text(encoding="utf-8"),
            }
            oracle = {
                "answerable": True,
                "checklist": [
                    "Answer the original question accurately, matching the supplied reference result and units.",
                    "Support the database and external findings with actually executed SQL and fetched Web evidence.",
                ],
                "reference": raw["final_answer"],
                "sql_reference": raw["sql_output"],
                "reference_sql": raw["sql"],
                "direction": raw["hybrid_type"],
            }
        else:
            question = raw["prompt"]
            catalog = {"allowed_sources": ["web"]}
            rubric = raw["criteria"]
            checklist = [
                f"{dimension}: {criterion['criterion']}. {criterion['explanation']}"
                for dimension, criteria in rubric["criterions"].items()
                for criterion in criteria
            ]
            oracle = {
                "answerable": True,
                "checklist": checklist,
                "reference": "Evaluate using the published criteria. This is a custom judge, not official RACE/FACT.",
                "published_rubric": rubric,
            }
        public.append({"id": item["id"], "suite": suite, "question": question, "catalog": catalog})
        private.append(
            {
                "id": item["id"],
                "suite": suite,
                "stratum": item["stratum"],
                "question": question,
                "required_sources": ["sql", "web"] if suite == "hybrid" else [],
                "oracle": oracle,
            }
        )
    target = INPUTS / ("development" if development else "validation")
    target.mkdir(parents=True, exist_ok=True)
    for name, rows in (("public.json", public), ("references.json", private)):
        path = target / name
        if path.exists() and read(path) != rows:
            raise ValueError("materialized_input_changed")
        atomic_json(path, rows)
    print(
        json.dumps(
            {
                "directory": str(target),
                "cases": len(public),
                "public_sha256": digest(public),
                "references_sha256": digest(private),
            }
        )
    )
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development", action="store_true")
    build(parser.parse_args().development)
