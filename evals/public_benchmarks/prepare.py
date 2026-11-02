"""Freeze metadata-only selections; keep licensed/canary task text in local assets."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from evals.dabstep.common import default_data_dir as dab_dir
from evals.dabstep.common import verify_files as verify_dab
from evals.hybrid.common import decrypt_record
from evals.hybrid.common import default_data_dir as hybrid_dir
from evals.hybrid.common import verify_files as verify_hybrid

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
LOCK = HERE / "suite.lock.json"
SEED = "deepsearch-e7-2026-11-02"
DRB_REVISION = "f2735b5c3636759c22f9e936c0232de8bf545b67"
DRB = ROOT / "data/benchmarks/deepresearch_bench" / DRB_REVISION


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def lines(path):
    return [
        json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line
    ]


def sources():
    dab = lines(dab_dir() / "dabstep_research.jsonl")
    hybrid = [
        decrypt_record(row)
        for row in lines(hybrid_dir() / "hybrid_ds_release/hybrid_ds_release.jsonl")
    ]
    drb = lines(DRB / "data/prompt_data/query.jsonl")
    criteria = {row["id"]: row for row in lines(DRB / "data/criteria_data/criteria.jsonl")}
    return {
        "dabstep": dab,
        "hybrid": hybrid,
        "drb": [{**row, "criteria": criteria[row["id"]]} for row in drb],
    }


def select():
    datasets = sources()
    old_dab = {int(row["source_id"]) for row in lines(ROOT / "evals/dabstep/selected_tasks.jsonl")}
    old_dab |= {row["source_id"] for row in read(ROOT / "evals/dabstep/holdout20.json")["cases"]}
    old_hybrid = {row["id"] for row in read(ROOT / "evals/hybrid/smoke_subset.json")["tasks"]}
    chosen = []
    for suite, groups in (
        ("dabstep", ("Data Analysis", "Data Insight", "Data Preparation", "Report Generation")),
        ("hybrid", ("search_to_sql", "sql_to_search", "parallel")),
        ("drb", ("zh", "en")),
    ):
        for group in groups:
            eligible = [
                r
                for r in datasets[suite]
                if (suite == "dabstep" and r["type"] == group and r["id"] not in old_dab)
                or (
                    suite == "hybrid"
                    and r["hybrid_type"] == group
                    and r["db"] == "alien"
                    and r["id"] not in old_hybrid
                )
                or (suite == "drb" and r["language"] == group)
            ]
            count = 4 if suite == "hybrid" else 3
            ranked = sorted(eligible, key=lambda r: digest([SEED, suite, r["id"]]))
            if len(ranked) < count:
                raise ValueError("insufficient_unexposed_cases")
            for row in ranked[:count]:
                question = (
                    row["question"]
                    if suite == "dabstep"
                    else row["final_question"]
                    if suite == "hybrid"
                    else row["prompt"]
                )
                chosen.append(
                    {
                        "id": f"{suite}:{row['id']}",
                        "source_id": row["id"],
                        "suite": suite,
                        "stratum": group,
                        "question_sha256": digest(question),
                        "record_sha256": digest(row),
                    }
                )
    files = [
        ROOT / "evals/dabstep/dataset.lock.json",
        ROOT / "evals/hybrid/dataset.lock.json",
        *[
            DRB / name
            for name in (
                "data/prompt_data/query.jsonl",
                "data/criteria_data/criteria.jsonl",
                "README.md",
                "LICENSE",
            )
        ],
    ]
    return {
        "version": "e7.0",
        "seed": SEED,
        "drb_revision": DRB_REVISION,
        "cases": chosen,
        "files": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
        },
        "budget": {
            "case_seconds": 300,
            "worker_seconds": 330,
            "case_requests": 8,
            "case_reserved_tokens": 180000,
            "workflow_batch_reserved_tokens": 5400000,
            "tool_lookups": 5,
            "web_queries": 5,
            "pages_per_query": 2,
            "judge_requests": 60,
            "judge_reserved_tokens": 1500000,
        },
        "protocol": {
            "generator": "deepseek-flash non-thinking",
            "workflows": ["simple", "bounded"],
            "primary_judge": "deepseek, provisional",
            "cpu_only": True,
            "holdout_policy": "one run per workflow; no research retries or post-holdout tuning",
            "primary_metrics": {
                "dabstep": "checklist coverage and cited support (not independent numeric accuracy)",
                "hybrid": "independent reference result audit, answer equivalence, cited support and executed direction",
                "drb": "published rubric coverage and cited support, custom judge; NOT official RACE/FACT",
            },
            "limitations": [
                "DABStep shares earlier source data",
                "Hybrid is alien database only",
                "Public tasks are not blind external evaluation",
                "Live Web differs across times/workflows",
                "DRB sample is not leaderboard-comparable",
            ],
        },
    }


def preflight():
    errors = verify_dab(dab_dir()) + verify_hybrid(hybrid_dir())
    if read(LOCK) != select():
        errors.append("frozen_selection_or_assets_changed")
    from evals.benchmark_preflight import DABSTEP_DATABASE

    if not DABSTEP_DATABASE.is_file():
        errors.append("dabstep_database_missing")
    return {
        "ready": not errors,
        "cases": dict(Counter(r["suite"] for r in read(LOCK)["cases"])),
        "lock_sha256": hashlib.sha256(LOCK.read_bytes()).hexdigest(),
        "errors": errors,
        "scope": "No model/search calls; no decrypted questions or answers emitted",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--freeze", action="store_true")
    p.add_argument("--download-drb", action="store_true")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if args.download_drb:
        import urllib.request

        for name in (
            "LICENSE",
            "README.md",
            "data/prompt_data/query.jsonl",
            "data/criteria_data/criteria.jsonl",
        ):
            target = DRB / name
            target.parent.mkdir(parents=True, exist_ok=True)
            content = urllib.request.urlopen(
                f"https://raw.githubusercontent.com/Ayanami0730/deep_research_bench/{DRB_REVISION}/{name}",
                timeout=60,
            ).read()
            expected = read(LOCK)["files"][str(target.relative_to(ROOT))]
            if hashlib.sha256(content).hexdigest() != expected:
                raise ValueError("download_hash_mismatch")
            target.write_bytes(content)
    if args.freeze:
        if LOCK.exists():
            raise ValueError("selection_already_frozen")
        LOCK.write_text(json.dumps(select(), indent=2) + "\n", encoding="utf-8")
    status = preflight()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status, indent=2))
    raise SystemExit(0 if status["ready"] else 1)


if __name__ == "__main__":
    main()
