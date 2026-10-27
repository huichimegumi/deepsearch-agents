import json
import sqlite3
from types import SimpleNamespace

import pytest

from app.agent.runtime import ResearchBudgetLimits
from evals.reports_acceptance import extended
from evals.runners.experiment import file_sha256


def web_record(host="www.python.org"):
    return {
        "evidence_id": "web",
        "source": "web",
        "locator": "https://" + host + "/release",
        "content": "Release Oct. 7, 2024 experimental free-threaded",
        "metadata": {},
    }


def test_frozen_suite_allocates_ten_queries_and_no_gold_is_in_question():
    suite = extended.load_suite()
    assert [case["search_queries"] for case in suite["cases"]] == [3, 3, 4, 0]
    assert len(suite["cases"]) == 4
    assert all("expected_inventory_count" not in case["question"] for case in suite["cases"])


@pytest.mark.parametrize(
    "host,expected",
    [
        ("python.org", True),
        ("docs.python.org", True),
        ("python.org.evil.test", False),
        ("evilpython.org", False),
    ],
)
def test_web_reference_requires_actual_official_hostname(host, expected):
    unit = {"source": "web", "domains": ["python.org"], "alternatives": [["Oct. 7, 2024"]]}
    assert extended.unit_matches(unit, web_record(host)) is expected


def test_cross_source_requires_eligible_query_and_each_source_cited():
    case = {
        "required_sources": ["web", "sql"],
        "units": [{"id": "count", "source": "sql", "column": "indexed_chunk_count"}],
        "expected_inventory_count": 59,
    }
    schema = {
        "evidence_id": "schema",
        "source": "sql",
        "content": {"indexed_chunk_count": 59},
        "metadata": {"evidence_kind": "database_schema"},
        "locator": "sql://schema",
    }
    result = extended.audit_extended("[schema]", {"records": [schema, web_record()]}, case)
    assert not result["required_sources_collected"]
    assert not result["all_reference_units_retrieved"]
    query = {**schema, "metadata": {"evidence_kind": "query_result"}}
    result = extended.audit_extended("no citations", {"records": [query, web_record()]}, case)
    assert result["required_sources_collected"] and not result["required_sources_cited"]
    assert result["all_reference_units_retrieved"] and not result["all_reference_units_cited"]
    assert result["acceptance"] == "pending_human_review"


def test_schema_citations_remain_visible_without_satisfying_requirements():
    key = "ev1_sql_" + "a" * 24
    schema = {
        "evidence_id": key,
        "source": "sql",
        "content": {},
        "locator": "sql://schema",
        "metadata": {"evidence_kind": "database_schema"},
    }
    case = {
        "required_sources": ["web"],
        "units": [
            {
                "id": "web",
                "source": "web",
                "domains": ["python.org"],
                "alternatives": [["experimental"]],
            }
        ],
    }
    result = extended.audit_extended(f"[{key}]", {"records": [schema]}, case)
    assert result["cited_discovery_sql_ids"] == [key]
    assert result["unexpected_sources"] == ["sql"]
    assert not result["required_sources_collected"]


def test_paid_execution_requires_explicit_operator_opt_in():
    with pytest.raises(ValueError, match="allow-paid-search"):
        extended.run(None, execute=True)


@pytest.mark.parametrize("ids", [[], ["unknown"], ["report_web_001", "report_web_001"]])
def test_invalid_explicit_subset_is_rejected(ids):
    with pytest.raises(ValueError):
        extended.select_cases(extended.load_suite(), ids)


def test_web_subset_keeps_frozen_order_and_equal_per_case_limits():
    suite = extended.load_suite()
    subset = extended.select_cases(suite, ["report_web_002", "report_web_001"])
    assert [case["id"] for case in subset] == ["report_web_001", "report_web_002"]
    assert [case["search_queries"] for case in subset] == [3, 3]
    assert sum(case["fetched_pages"] for case in subset) == 6


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    monkeypatch.setattr(extended, "ROOT", tmp_path)
    directory = tmp_path / "evals/results/assets"
    directory.mkdir(parents=True)
    dataset = tmp_path / "suite.json"
    dataset.write_text("{}")
    monkeypatch.setattr(extended, "DATASET", dataset)
    corpus = [{"document_sha256": "a" * 64, "chunk_index": 0, "content": "local fact"}]
    (directory / "corpus.json").write_text(json.dumps(corpus))
    (directory / "reference.txt").write_text("Release official fact")
    with sqlite3.connect(directory / "inventory.sqlite") as connection:
        connection.execute(
            "CREATE TABLE document_inventory(filename TEXT, indexed_chunk_count INTEGER)"
        )
        connection.execute(
            "INSERT INTO document_inventory VALUES (?, ?)", (extended.TARGET_DOCUMENT, 1)
        )
    suite = {
        "knowledge_bases": ["test"],
        "cases": [
            {
                "units": [
                    {
                        "id": "local",
                        "source": "local_document",
                        "document_sha256": "a" * 64,
                        "alternatives": [["local fact"]],
                    },
                    {
                        "id": "web",
                        "source": "web",
                        "domains": ["python.org"],
                        "alternatives": [["official fact"]],
                    },
                ]
            }
        ],
    }
    monkeypatch.setattr(extended, "load_suite", lambda: suite)
    monkeypatch.setattr(extended, "corpus_snapshot", lambda _: ([], corpus))
    lock = {
        "dataset_sha256": file_sha256(dataset),
        "corpus_sha256": extended.canonical_sha256(corpus),
        "corpus_path": "evals/results/assets/corpus.json",
        "corpus_file_sha256": file_sha256(directory / "corpus.json"),
        "sqlite_path": "evals/results/assets/inventory.sqlite",
        "sqlite_sha256": file_sha256(directory / "inventory.sqlite"),
        "expected_inventory_count": 1,
        "reference_pages": [
            {
                "url": "https://python.org/ref",
                "status": "fetched",
                "path": "evals/results/assets/reference.txt",
                "sha256": file_sha256(directory / "reference.txt"),
            }
        ],
    }
    path = directory / "lock.json"
    path.write_text(json.dumps(lock))
    return path, lock, corpus


def test_reference_lock_is_checked_offline_or_against_live_corpus(frozen):
    path, lock, _ = frozen
    assert extended.validate_lock(path, live=False)[0] == lock
    extended.validate_lock(path)


@pytest.mark.parametrize(
    "failure",
    ["dataset", "database", "corpus", "reference", "expected_count", "outside", "live_drift"],
)
def test_frozen_inputs_reject_drift_and_unsafe_paths(frozen, monkeypatch, failure):
    path, lock, corpus = frozen
    if failure == "dataset":
        lock["dataset_sha256"] = "changed"
    elif failure == "database":
        (path.parent / "inventory.sqlite").write_bytes(b"changed")
    elif failure == "corpus":
        lock["corpus_sha256"] = "changed"
    elif failure == "reference":
        (path.parent / "reference.txt").write_text("changed")
    elif failure == "expected_count":
        lock["expected_inventory_count"] = 999
    elif failure == "outside":
        lock["sqlite_path"] = "outside.sqlite"
    else:
        monkeypatch.setattr(extended, "corpus_snapshot", lambda _: ([], []))
    path.write_text(json.dumps(lock))
    with pytest.raises(ValueError):
        extended.validate_lock(path)


def test_unavailable_web_reference_cannot_silently_validate(frozen):
    path, lock, _ = frozen
    lock["reference_pages"] = []
    path.write_text(json.dumps(lock))
    with pytest.raises(ValueError, match="Web reference anchor missing"):
        extended.validate_lock(path, live=False)


def test_execution_uses_fixed_disjoint_allowances_and_restores_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(extended, "ROOT", tmp_path)
    assets = tmp_path / "evals/results/assets"
    assets.mkdir(parents=True)
    database = assets / "inventory.sqlite"
    database.touch()
    lock_path = assets / "lock.json"
    lock_path.write_text("{}")
    lock = {"sqlite_path": "evals/results/assets/inventory.sqlite", "expected_inventory_count": 59}
    monkeypatch.setattr(extended, "validate_lock", lambda _: (lock, []))
    monkeypatch.setenv("TAVILY_API_KEY", "synthetic-not-a-real-key")
    monkeypatch.setenv("SEARCH_BACKEND_LOCK", "duckduckgo")
    settings = SimpleNamespace(
        llm_name="synthetic",
        validate_llm=lambda: None,
        research_budget_limits=lambda _: ResearchBudgetLimits(
            "deep_report", 300, 10, 10, 2, 12, 75
        ),
    )
    monkeypatch.setattr(extended, "get_settings", lambda: settings)
    monkeypatch.setattr(
        extended,
        "build_manifest",
        lambda _, config: {
            "configuration": config,
            "source_sha256": "source",
            "dataset_sha256": "dataset",
        },
    )
    seen = []

    async def execute(case, prompt, session, directory, timeout, **kwargs):
        assert "expected_inventory_count" not in prompt
        assert "59" not in prompt
        assert extended.os.environ["SEARCH_BACKEND_LOCK"] == "tavily"
        seen.append(kwargs["research_limits"].max_search_queries)
        directory.mkdir()
        (directory / "trace.json").write_text(
            json.dumps({"budget": {"usage": {"search_queries": case["search_queries"]}}})
        )
        return {"id": case["id"], "execution_status": "degraded", "error_type": None}

    monkeypatch.setattr(extended, "execute_case", execute)
    path = extended.run(lock_path, execute=True, allow_paid=True)
    result = json.loads(path.read_text())
    assert seen == [3, 3, 4, 0]
    assert (
        result["reported_admitted_search_queries"] == result["scheduled_search_query_ceiling"] == 10
    )
    assert len(result["results"]) == 4 and result["inputs_unchanged"]
    assert extended.os.environ["SEARCH_BACKEND_LOCK"] == "duckduckgo"
