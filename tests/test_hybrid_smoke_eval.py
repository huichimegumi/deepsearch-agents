import base64
import hashlib
import json
import sqlite3

import pytest

from app.agent.main_agent import _requested_artifact_formats
from app.agent.runtime import (
    ResearchBudget,
    ResearchBudgetLimits,
    ResearchRunTrace,
    reset_research_runtime,
    set_research_runtime,
)
from app.tools.evidence_tool import collect_evidence
from evals.hybrid.common import CANARY, CANARY_NOTICE, SELECTION_PATH, decrypt_record, load_json
from evals.hybrid.run_smoke import (
    _sql_result_match,
    _strict_text_match,
    _task_prompt,
    _validate_paid_search,
)


def _encrypted_record(payload: dict) -> dict:
    canonical = json.dumps(
        {**payload, "_canary": CANARY_NOTICE},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    data = canonical.encode()
    digest = hashlib.sha256(CANARY.encode()).digest()
    key = digest * (len(data) // len(digest)) + digest[: len(data) % len(digest)]
    return {
        "id": payload["id"],
        "hybrid_type": payload["hybrid_type"],
        "canary": CANARY,
        "encrypted_payload": base64.b64encode(
            bytes(left ^ right for left, right in zip(data, key))
        ).decode(),
        "payload_sha256": hashlib.sha256(data).hexdigest(),
    }


def _sqlite_database(path):
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE groups (id INTEGER PRIMARY KEY, label TEXT NOT NULL UNIQUE)"
        )
        connection.execute(
            "CREATE TABLE metrics (name TEXT, value INTEGER, group_id INTEGER, "
            "FOREIGN KEY(group_id) REFERENCES groups(id))"
        )
        connection.execute("INSERT INTO groups VALUES (1, 'primary')")
        connection.executemany(
            "INSERT INTO metrics VALUES (?, ?, ?)",
            [("alpha", 1, 1), ("beta", 2, 1)],
        )


def test_smoke_subset_has_one_task_per_mode_and_one_database():
    selection = load_json(SELECTION_PATH)

    assert len(selection["tasks"]) == 3
    assert {item["hybrid_type"] for item in selection["tasks"]} == {
        "search_to_sql",
        "sql_to_search",
        "parallel",
    }
    assert {item["db"] for item in selection["tasks"]} == {"alien"}
    assert selection["max_search_queries_per_task"] == 2
    assert selection["default_search_backend"] == "duckduckgo"


def test_hybrid_record_decryption_checks_hash_and_canary():
    encrypted = _encrypted_record({"id": "task-1", "hybrid_type": "parallel", "db": "demo"})

    decoded = decrypt_record(encrypted)
    assert decoded == {"id": "task-1", "hybrid_type": "parallel", "db": "demo"}

    encrypted["payload_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="payload hash mismatch"):
        decrypt_record(encrypted)


def test_paid_or_mixed_search_requires_explicit_authorization():
    _validate_paid_search("duckduckgo", allow_paid_search=False)

    for backend in ("tavily", "perplexity", "auto", "advanced"):
        with pytest.raises(ValueError, match="allow-paid-search"):
            _validate_paid_search(backend, allow_paid_search=False)
        _validate_paid_search(backend, allow_paid_search=True)


def test_sqlite_evidence_backend_is_read_only_and_stable(tmp_path, monkeypatch):
    database = tmp_path / "smoke.sqlite"
    _sqlite_database(database)
    monkeypatch.setenv("EVIDENCE_SQLITE_PATH", str(database))

    tables = json.loads(collect_evidence.invoke({"source": "sql", "operation": "list_tables"}))
    first = json.loads(
        collect_evidence.invoke(
            {"source": "sql", "query": "SELECT name, value FROM metrics ORDER BY name"}
        )
    )
    second = json.loads(
        collect_evidence.invoke(
            {"source": "sql", "query": " SELECT name, value FROM metrics ORDER BY name; "}
        )
    )
    rejected = json.loads(
        collect_evidence.invoke({"source": "sql", "query": "UPDATE metrics SET value = 9"})
    )

    assert tables["status"] == "OK"
    assert {item["content"]["table_name"] for item in tables["records"]} == {
        "groups",
        "metrics",
    }
    assert [item["evidence_id"] for item in first["records"]] == [
        item["evidence_id"] for item in second["records"]
    ]
    assert first["records"][0]["locator"].startswith("sql://sqlite/sha256/")
    assert rejected["status"] == "ERROR"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT SUM(value) FROM metrics").fetchone()[0] == 3


def test_sqlite_schema_and_samples_are_bounded_stable_evidence(tmp_path, monkeypatch):
    database = tmp_path / "schema.sqlite"
    _sqlite_database(database)
    monkeypatch.setenv("EVIDENCE_SQLITE_PATH", str(database))

    first = json.loads(collect_evidence.invoke({"source": "sql", "operation": "describe_schema"}))
    second = json.loads(collect_evidence.invoke({"source": "sql", "operation": "describe_schema"}))
    sample = json.loads(
        collect_evidence.invoke(
            {"source": "sql", "operation": "sample_table", "table_name": "metrics"}
        )
    )
    rejected = json.loads(
        collect_evidence.invoke(
            {
                "source": "sql",
                "operation": "sample_table",
                "table_name": 'metrics"; DROP TABLE metrics; --',
            }
        )
    )

    assert first["status"] == "OK"
    assert [item["evidence_id"] for item in first["records"]] == [
        item["evidence_id"] for item in second["records"]
    ]
    metrics = next(item for item in first["records"] if item["content"]["table_name"] == "metrics")
    assert {column["name"] for column in metrics["content"]["columns"]} == {
        "name",
        "value",
        "group_id",
    }
    assert metrics["content"]["foreign_keys"][0]["target_table"] == "groups"
    groups = next(item for item in first["records"] if item["content"]["table_name"] == "groups")
    assert groups["content"]["indexes"][0]["columns"] == ["label"]
    assert len(sample["records"]) == 2
    assert rejected["status"] == "ERROR"


def test_sqlite_query_repair_policy_blocks_duplicate_and_third_failure(tmp_path, monkeypatch):
    database = tmp_path / "repair.sqlite"
    _sqlite_database(database)
    monkeypatch.setenv("EVIDENCE_SQLITE_PATH", str(database))
    budget = ResearchBudget(
        ResearchBudgetLimits(
            profile="test",
            total_seconds=30,
            max_search_queries=0,
            max_fetched_pages=0,
            max_research_rounds=1,
            max_llm_calls=1,
            writer_reserved_seconds=0,
        )
    )
    trace = ResearchRunTrace("run", "thread", "test", budget)
    tokens = set_research_runtime(budget, trace)
    try:
        schema = json.loads(
            collect_evidence.invoke({"source": "sql", "operation": "describe_schema"})
        )
        first = json.loads(
            collect_evidence.invoke({"source": "sql", "query": "SELECT missing FROM metrics"})
        )
        duplicate = json.loads(
            collect_evidence.invoke({"source": "sql", "query": "SELECT missing FROM metrics"})
        )
        repair = json.loads(
            collect_evidence.invoke({"source": "sql", "query": "SELECT still_missing FROM metrics"})
        )
        limited = json.loads(
            collect_evidence.invoke({"source": "sql", "query": "SELECT value FROM metrics"})
        )
    finally:
        reset_research_runtime(tokens)

    assert schema["status"] == "OK"
    assert first["status"] == "ERROR"
    assert "duplicate_failed_query" in duplicate["warnings"][0]
    assert repair["status"] == "ERROR"
    assert "consecutive_failure_limit" in limited["warnings"][0]
    assert trace.sql_schema_discovery_calls == 1
    assert trace.sql_query_attempts == 2
    assert trace.sql_query_failures == 2
    assert trace.sql_query_blocked == 2


def test_smoke_correctness_helpers_do_not_require_llm_judge(tmp_path):
    database = tmp_path / "score.sqlite"
    _sqlite_database(database)
    answer = "Result: beta [ev1_sql_aaaaaaaaaaaaaaaaaaaaaaaa]."

    assert _strict_text_match(answer, "beta") is True
    assert _strict_text_match(answer, "gamma") is False
    assert (
        _sql_result_match(
            "```sql\nSELECT name FROM metrics WHERE value = 2\n```",
            "SELECT name FROM metrics WHERE value = 2",
            database,
        )
        is True
    )
    assert _sql_result_match("No SQL supplied", "SELECT name FROM metrics", database) is False


def test_smoke_prompt_does_not_accidentally_request_file_artifacts():
    prompt = _task_prompt(
        {
            "final_question": "Answer the hybrid question.",
            "hint": "",
            "db": "alien",
        }
    )

    assert _requested_artifact_formats(prompt) == set()
