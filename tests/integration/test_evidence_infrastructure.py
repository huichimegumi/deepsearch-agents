"""Opt-in acceptance tests for the live M1.2 evidence infrastructure.

These tests intentionally stay out of the default unit-test path unless
RUN_EVIDENCE_INFRASTRUCTURE_TESTS=1 is set. They exercise the real MySQL,
PostgreSQL, Qdrant, and pinned DABStep data configured by the local `.env`.
"""

from __future__ import annotations

import json
import os
from importlib.metadata import version
from urllib.request import urlopen

import pytest

from app.research.claims import ClaimDraft, validate_claims, validate_report_citations
from app.tools.evidence_tool import collect_evidence

pytestmark = [
    pytest.mark.infrastructure,
    pytest.mark.skipif(
        os.getenv("RUN_EVIDENCE_INFRASTRUCTURE_TESTS") != "1",
        reason="set RUN_EVIDENCE_INFRASTRUCTURE_TESTS=1 to run live infrastructure tests",
    ),
]


def _collect(payload: dict[str, str]) -> dict:
    return json.loads(collect_evidence.invoke(payload))


def _record_identity(batch: dict) -> dict[str, tuple[str, object]]:
    return {
        record["evidence_id"]: (record["locator"], record["content"]) for record in batch["records"]
    }


def test_qdrant_server_matches_locked_client_compatibility_window():
    qdrant_url = os.getenv("RAG_QDRANT_URL", "http://localhost:6333").rstrip("/")
    with urlopen(f"{qdrant_url}/", timeout=5) as response:  # noqa: S310 - local test endpoint
        server_payload = json.load(response)

    client_version = version("qdrant-client")
    server_version = server_payload["version"]
    client_major, client_minor = (int(part) for part in client_version.split(".")[:2])
    server_major, server_minor = (int(part) for part in server_version.split(".")[:2])

    assert client_major == server_major
    assert abs(client_minor - server_minor) <= 1, (
        f"qdrant-client {client_version} is outside the supported compatibility window "
        f"for Qdrant server {server_version}"
    )


def test_mysql_evidence_is_live_repeatable_and_read_only():
    tables = _collect({"source": "sql", "operation": "list_tables"})
    assert tables["status"] == "OK"
    assert tables["records"]

    request = {"source": "sql", "query": "SELECT 1 AS evidence_smoke_value"}
    first = _collect(request)
    second = _collect(request)
    assert first["status"] == second["status"] == "OK"
    assert _record_identity(first) == _record_identity(second)

    rejected = _collect({"source": "sql", "query": "DELETE FROM inventory"})
    assert rejected["status"] == "ERROR"
    assert rejected["records"] == []
    assert any("read-only" in warning for warning in rejected["warnings"])


def test_fee_evidence_is_repeatable_against_the_pinned_snapshot():
    psp_reference = os.getenv("EVIDENCE_TEST_PSP_REFERENCE", "20034594130")
    request = {"source": "fee_engine", "psp_reference": psp_reference}

    first = _collect(request)
    second = _collect(request)

    assert first["status"] == second["status"] == "OK"
    assert _record_identity(first) == _record_identity(second)


def test_local_document_evidence_crosses_postgres_and_qdrant_repeatably():
    knowledge_base = os.getenv("EVIDENCE_TEST_KNOWLEDGE_BASE", "rag-test")
    query = os.getenv(
        "EVIDENCE_TEST_DOCUMENT_QUERY",
        "平台在2026年计划重点提升什么，以及会在哪些场景接入金融服务？",
    )
    request = {
        "source": "local_document",
        "knowledge_base": knowledge_base,
        "query": query,
    }

    first = _collect(request)
    second = _collect(request)

    assert first["status"] in {"OK", "PARTIAL"}
    assert second["status"] in {"OK", "PARTIAL"}
    assert first["records"] and second["records"]
    assert _record_identity(first) == _record_identity(second)


def test_live_sql_evidence_can_back_a_validated_claim_and_report():
    batch = _collect({"source": "sql", "query": "SELECT 1 AS evidence_smoke_value"})
    evidence_id = batch["records"][0]["evidence_id"]

    claims = validate_claims(
        [ClaimDraft(text="The deterministic smoke value is 1.", evidence_ids=[evidence_id])],
        available_evidence_ids=[evidence_id],
    )
    citations = validate_report_citations(
        f"The deterministic smoke value is 1 [{evidence_id}].",
        allowed_evidence_ids=claims.referenced_evidence_ids,
    )

    assert len(claims.accepted) == 1
    assert claims.accepted[0].claim_id.startswith("clm1_")
    assert citations.valid is True
