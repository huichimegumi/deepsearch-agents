"""Four frozen Web/cross-source development reports with a ten-query batch ceiling."""

import argparse
import asyncio
import contextlib
import json
import os
import sqlite3
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path
from urllib.parse import urlsplit

from app.config import get_settings
from app.research.claims import validate_report_citations
from evals.rag.protocol import canonical_sha256
from evals.rag.run_retrieval import corpus_snapshot
from evals.rag.scoring import normalized
from evals.reports_acceptance.run import execute_case
from evals.runners.common import ROOT, write_json
from evals.runners.experiment import build_manifest, file_sha256, new_run_id

DATASET = Path(__file__).with_name("extended_v1.json")
PRIMARY_REFERENCES = [
    "https://www.python.org/downloads/release/python-3130/",
    "https://docs.python.org/3.13/howto/free-threading-python.html",
    "https://www.postgresql.org/about/news/postgresql-17-released-2936/",
    "https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/5896228/index.html",
]
TARGET_DOCUMENT = "2026数字人电商直播白皮书.pdf"


def load_suite() -> dict:
    suite = json.loads(DATASET.read_text(encoding="utf-8"))
    ids = [case["id"] for case in suite["cases"]]
    if len(ids) != 4 or len(set(ids)) != 4:
        raise ValueError("Requires four unique frozen tasks")
    if (
        suite["max_batch_search_queries"] != 10
        or sum(case["search_queries"] for case in suite["cases"]) > 10
    ):
        raise ValueError("Frozen batch search ceiling exceeded")
    for case in suite["cases"]:
        if case["search_queries"] < 0 or case["fetched_pages"] < 0:
            raise ValueError("Negative retrieval limit")
        if not case["units"] or len({unit["id"] for unit in case["units"]}) != len(case["units"]):
            raise ValueError("Missing/duplicate reference units")
    return suite


def safe_path(value: str | Path) -> Path:
    path = Path(value)
    path = (path if path.is_absolute() else ROOT / path).resolve()
    if not path.is_relative_to((ROOT / "evals/results").resolve()):
        raise ValueError("Frozen assets must remain under evals/results")
    return path


def prepare() -> Path:
    suite = load_suite()
    _, corpus = corpus_snapshot(suite["knowledge_bases"])
    directory = ROOT / "evals/results" / new_run_id("extended_assets")
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory / "corpus.json", corpus)
    unique = {(row["document_sha256"], row["chunk_index"]): row for row in corpus}
    counts = Counter(row["document_sha256"] for row in unique.values())
    names = {row["document_sha256"]: row["filename"] for row in corpus}
    database = directory / "inventory.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE document_inventory (filename TEXT, document_sha256 TEXT PRIMARY KEY, indexed_chunk_count INTEGER)"
        )
        connection.executemany(
            "INSERT INTO document_inventory VALUES (?, ?, ?)",
            [(names[sha], sha, counts[sha]) for sha in sorted(counts)],
        )
        expected = connection.execute(
            "SELECT indexed_chunk_count FROM document_inventory WHERE filename=?",
            (TARGET_DOCUMENT,),
        ).fetchone()
    if expected is None:
        raise ValueError("SQL reference document missing from actual corpus")
    # Independent reference snapshots are evaluator-only and never injected into the agent.
    import requests

    from app.search.service import _TextExtractor

    references = []
    for index, url in enumerate(PRIMARY_REFERENCES):
        path = directory / f"reference_{index}.txt"
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            parser = _TextExtractor()
            parser.feed(response.text)
            path.write_text("\n".join(parser.parts), encoding="utf-8")
            references.append(
                {
                    "url": url,
                    "status": "fetched",
                    "path": path.relative_to(ROOT).as_posix(),
                    "sha256": file_sha256(path),
                }
            )
        except requests.RequestException as exc:
            references.append(
                {"url": url, "status": "unavailable", "error_type": type(exc).__name__}
            )
    lock = {
        "schema_version": 1,
        "dataset_sha256": file_sha256(DATASET),
        "corpus_sha256": canonical_sha256(corpus),
        "corpus_path": (directory / "corpus.json").relative_to(ROOT).as_posix(),
        "corpus_file_sha256": file_sha256(directory / "corpus.json"),
        "sqlite_path": database.relative_to(ROOT).as_posix(),
        "sqlite_sha256": file_sha256(database),
        "expected_inventory_count": expected[0],
        "reference_pages": references,
        "reference_status": "source_verified_by_agent_pending_human_review",
    }
    write_json(directory / "lock.json", lock)
    return directory / "lock.json"


def validate_lock(path: Path, *, live: bool = True) -> tuple[dict, list[dict]]:
    suite = load_suite()
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock["dataset_sha256"] != file_sha256(DATASET):
        raise ValueError("Frozen task suite changed")
    for key, digest in [("sqlite_path", "sqlite_sha256"), ("corpus_path", "corpus_file_sha256")]:
        if file_sha256(safe_path(lock[key])) != lock[digest]:
            raise ValueError("Frozen asset changed")
    for reference in lock["reference_pages"]:
        if (
            reference["status"] == "fetched"
            and file_sha256(safe_path(reference["path"])) != reference["sha256"]
        ):
            raise ValueError("Reference snapshot changed")
    corpus = json.loads(safe_path(lock["corpus_path"]).read_text(encoding="utf-8"))
    if canonical_sha256(corpus) != lock["corpus_sha256"]:
        raise ValueError("Corpus snapshot fingerprint mismatch")
    if (
        live
        and canonical_sha256(corpus_snapshot(suite["knowledge_bases"])[1]) != lock["corpus_sha256"]
    ):
        raise ValueError("Live selected corpus changed")
    with sqlite3.connect(
        f"{safe_path(lock['sqlite_path']).as_uri()}?mode=ro", uri=True
    ) as connection:
        expected = connection.execute(
            "SELECT indexed_chunk_count FROM document_inventory WHERE filename=?",
            (TARGET_DOCUMENT,),
        ).fetchone()
    if expected != (lock["expected_inventory_count"],):
        raise ValueError("Independent SQL reference mismatch")
    for case in suite["cases"]:
        for unit in case["units"]:
            if unit["source"] == "web" and not any(
                reference["status"] == "fetched"
                and unit_matches(
                    unit,
                    {
                        "source": "web",
                        "locator": reference["url"],
                        "content": safe_path(reference["path"]).read_text(encoding="utf-8"),
                    },
                )
                for reference in lock["reference_pages"]
            ):
                raise ValueError("Web reference anchor missing from frozen official snapshots")
            if unit["source"] == "local_document" and not any(
                unit_matches(
                    unit,
                    {
                        "source": "local_document",
                        "locator": f"document://sha256/{row['document_sha256']}#chunk={row['chunk_index']}",
                        "content": row["content"],
                    },
                )
                for row in corpus
            ):
                raise ValueError("Local reference anchor missing")
    return lock, corpus


def unit_matches(unit: dict, record: dict, expected_count=None) -> bool:
    if record["source"] != unit["source"]:
        return False
    if unit["source"] == "sql":
        return (
            record.get("metadata", {}).get("evidence_kind") == "query_result"
            and record["content"].get(unit["column"]) == expected_count
        )
    if unit["source"] == "web":
        host = (urlsplit(record["locator"]).hostname or "").lower()
        if not any(host == domain or host.endswith("." + domain) for domain in unit["domains"]):
            return False
    elif not record["locator"].startswith("document://sha256/" + unit["document_sha256"] + "#"):
        return False
    text = normalized(str(record["content"]))
    return any(
        all(normalized(anchor).casefold() in text.casefold() for anchor in alternative)
        for alternative in unit["alternatives"]
    )


def audit_extended(report: str, snapshot: dict | None, case: dict) -> dict:
    records = (snapshot or {}).get("records", [])
    by_id = {record["evidence_id"]: record for record in records}
    validation = validate_report_citations(
        report, allowed_evidence_ids=by_id, citations_required=True
    )
    cited = set(validation.cited_evidence_ids)
    eligible = [
        record
        for record in records
        if record["source"] != "sql"
        or record.get("metadata", {}).get("evidence_kind") == "query_result"
    ]
    observed = {record["source"] for record in eligible}
    cited_sources = {record["source"] for record in eligible if record["evidence_id"] in cited}
    coverage = []
    for unit in case["units"]:
        hits = [
            record["evidence_id"]
            for record in eligible
            if unit_matches(unit, record, case.get("expected_inventory_count"))
        ]
        coverage.append(
            {
                "unit_id": unit["id"],
                "retrieved_ids": hits,
                "cited_ids": [key for key in hits if key in cited],
            }
        )
    return {
        "report_nonempty": bool(report.strip()),
        "evidence_snapshot_present": snapshot is not None,
        "evidence_count": len(records),
        "observed_sources": sorted({record["source"] for record in records}),
        "claim_eligible_sources": sorted(observed),
        "required_sources_collected": set(case["required_sources"]) <= observed,
        "required_sources_cited": set(case["required_sources"]) <= cited_sources,
        "unexpected_sources": sorted(
            {record["source"] for record in records} - set(case["required_sources"])
        ),
        "cited_discovery_sql_ids": [
            record["evidence_id"]
            for record in records
            if record["source"] == "sql"
            and record["evidence_id"] in cited
            and record not in eligible
        ],
        "unknown_cited_ids": list(validation.unknown_evidence_ids),
        "citation_ids_resolve": validation.valid if snapshot is not None else None,
        "reference_evidence_coverage": coverage,
        "all_reference_units_retrieved": all(unit["retrieved_ids"] for unit in coverage),
        "all_reference_units_cited": all(unit["cited_ids"] for unit in coverage),
        "keypoint_correctness": "pending_review",
        "claim_entailment": "pending_review",
        "acceptance": "pending_human_review",
    }


@contextlib.contextmanager
def environment(values):
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def select_cases(suite: dict, case_ids: list[str] | None) -> list[dict]:
    if case_ids is None:
        return suite["cases"]
    known = {case["id"] for case in suite["cases"]}
    if not case_ids or len(set(case_ids)) != len(case_ids) or not set(case_ids) <= known:
        raise ValueError("Selected case IDs must be nonempty, unique and known")
    return [case for case in suite["cases"] if case["id"] in case_ids]


def run(lock_path: Path, execute=False, allow_paid=False, *, case_ids=None) -> Path:
    if execute and not allow_paid:
        raise ValueError("Live Tavily execution requires --allow-paid-search")
    suite = load_suite()
    cases = select_cases(suite, case_ids)
    lock, _ = validate_lock(lock_path)
    settings = get_settings()
    if execute:
        settings.validate_llm()
        if not os.getenv("TAVILY_API_KEY"):
            raise ValueError("Tavily key unavailable")
    directory = ROOT / "evals/results" / new_run_id("extended_reports")
    directory.mkdir(parents=True, exist_ok=False)
    manifest = build_manifest(
        DATASET,
        {
            "model": settings.llm_name,
            "execution_enabled": execute,
            "backend_lock": "tavily",
            "max_batch_search_queries": 10,
            "lock_sha256": file_sha256(lock_path),
            "profile": "deep_report",
            "default_researcher": True,
            "selected_cases": [case["id"] for case in cases],
            "scheduled_search_query_ceiling": sum(case["search_queries"] for case in cases),
            "outer_timeout_seconds": 330,
            "limits_by_case": {
                case["id"]: asdict(
                    replace(
                        settings.research_budget_limits("deep_report"),
                        max_search_queries=case["search_queries"],
                        max_fetched_pages=case["fetched_pages"],
                    )
                )
                for case in cases
            },
        },
    )
    result = {
        "run_id": directory.name,
        "manifest": manifest,
        "asset_lock": lock,
        "results": [],
        "acceptance": "pending_human_review",
        "generative_answer_accuracy": None,
    }
    write_json(directory / "results.json", result)
    # Fixed disjoint per-case allowances sum to ten, including requests that finish late.
    # No transfer of an interrupted case's unobserved remainder to another case.
    if execute:
        for original_case in cases:
            case = {
                **original_case,
                "answerable": True,
                "expected_inventory_count": lock["expected_inventory_count"],
            }
            limits = replace(
                settings.research_budget_limits("deep_report"),
                max_search_queries=case["search_queries"],
                max_fetched_pages=case["fetched_pages"],
            )
            with environment(
                {
                    "SEARCH_BACKEND_LOCK": "tavily",
                    "EVIDENCE_SQLITE_PATH": str(safe_path(lock["sqlite_path"])),
                    "EVIDENCE_SQLITE_COLUMN_MEANINGS_PATH": "",
                    "EVIDENCE_SQLITE_KNOWLEDGE_PATH": "",
                    "REQUIRE_ANALYTICAL_SQL_EVIDENCE": "1"
                    if "sql" in case["required_sources"]
                    else "0",
                    "INCLUDE_EXECUTED_SQL_IN_REPORT": "1"
                    if "sql" in case["required_sources"]
                    else "0",
                }
            ):
                row = asyncio.run(
                    execute_case(
                        case,
                        case["question"],
                        f"{directory.name}_{case['id']}",
                        directory / case["id"],
                        330,
                        research_limits=limits,
                        audit_function=audit_extended,
                        required_evidence_sources=tuple(case["required_sources"]),
                    )
                )
            row["configured_limits"] = asdict(limits)
            trace_path = directory / case["id"] / "trace.json"
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            row["admitted_search_queries"] = (
                trace.get("budget", {}).get("usage", {}).get("search_queries")
            )
            row["trace_sha256"] = file_sha256(trace_path)
            result["results"].append(row)
            write_json(directory / "results.json", result)
            print(f"{case['id']}: {row['execution_status']}", flush=True)
    validate_lock(lock_path)
    final = build_manifest(DATASET, manifest["configuration"])
    result["inputs_unchanged"] = (
        final["source_sha256"] == manifest["source_sha256"]
        and final["dataset_sha256"] == manifest["dataset_sha256"]
        and file_sha256(lock_path) == manifest["configuration"]["lock_sha256"]
    )
    result["scheduled_search_query_ceiling"] = (
        sum(case["search_queries"] for case in cases) if execute else 0
    )
    result["reported_admitted_search_queries"] = sum(
        row["admitted_search_queries"] or 0 for row in result["results"]
    )
    write_json(directory / "results.json", result)
    return directory / "results.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--allow-paid-search", action="store_true")
    parser.add_argument(
        "--case-id", action="append", help="Explicit frozen subset; limits remain unchanged"
    )
    args = parser.parse_args()
    if args.prepare:
        if args.execute or args.lock or args.case_id:
            parser.error("Preparation is separate from execution")
        print(prepare())
        return 0
    if not args.lock:
        parser.error("--lock is required")
    path = run(args.lock, args.execute, args.allow_paid_search, case_ids=args.case_id)
    print(path)
    result = json.loads(path.read_text(encoding="utf-8"))
    return int(
        not result["inputs_unchanged"]
        or any(
            row["execution_status"] != "completed" or row["error_type"] for row in result["results"]
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
