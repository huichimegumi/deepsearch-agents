import json
from decimal import Decimal

import pytest

from app.rag.retrieval import RetrievedChunk
from app.research.evidence import (
    EvidenceBatch,
    EvidenceBatchStatus,
    EvidenceRecord,
    EvidenceRequest,
    EvidenceSource,
    fee_calculation_to_evidence,
    retrieved_chunks_to_evidence,
    run_minimal_evidence_workflow,
    sql_rows_to_evidence,
    sql_schema_to_evidence,
)
from app.research.fee_engine import FeeEngine, FeeRule, TransactionContext
from app.tools.evidence_tool import _validate_read_only_sql, collect_evidence


def _fee_calculation():
    rule = FeeRule.from_mapping(
        {
            "ID": 10,
            "card_scheme": "GlobalCard",
            "account_type": [],
            "capture_delay": None,
            "monthly_fraud_level": None,
            "monthly_volume": None,
            "merchant_category_code": [],
            "is_credit": None,
            "aci": [],
            "fixed_amount": "0.10",
            "rate": "25",
            "intracountry": None,
        }
    )
    context = TransactionContext(
        merchant="Merchant",
        year=2023,
        month=1,
        card_scheme="GlobalCard",
        account_type="H",
        capture_delay="2",
        monthly_fraud_rate=Decimal("0.01"),
        monthly_volume=Decimal("1000"),
        merchant_category_code=5812,
        is_credit=True,
        aci="B",
        intracountry=True,
    )
    return FeeEngine([rule]).calculate(
        psp_reference="payment-1",
        amount=Decimal("10"),
        context=context,
    )


def test_evidence_id_is_content_addressed_and_ignores_runtime_metadata():
    first = EvidenceRecord.create(
        source=EvidenceSource.LOCAL_DOCUMENT,
        locator="document://sha256/doc#chunk=1",
        content="same fact",
        metadata={"score": 0.9},
    )
    reranked = EvidenceRecord.create(
        source=EvidenceSource.LOCAL_DOCUMENT,
        locator="document://sha256/doc#chunk=1",
        content="same fact",
        metadata={"score": 0.2},
    )
    changed = EvidenceRecord.create(
        source=EvidenceSource.LOCAL_DOCUMENT,
        locator="document://sha256/doc#chunk=1",
        content="changed fact",
        metadata={"score": 0.9},
    )

    assert first.evidence_id == reranked.evidence_id
    assert first.evidence_id != changed.evidence_id
    assert first.evidence_id.startswith("ev1_local_document_")


def test_sql_evidence_is_stable_across_insignificant_query_whitespace():
    first = sql_rows_to_evidence(
        query="SELECT merchant, total FROM fees ORDER BY merchant",
        columns=["merchant", "total"],
        rows=[("A", Decimal("1.20"))],
        database_identity="localhost/demo",
    )
    second = sql_rows_to_evidence(
        query=" SELECT  merchant, total\nFROM fees ORDER BY merchant; ",
        columns=["merchant", "total"],
        rows=[("A", Decimal("1.20"))],
        database_identity="localhost/demo",
    )

    assert first[0].evidence_id == second[0].evidence_id
    assert first[0].content == {"merchant": "A", "total": "1.20"}
    assert first[0].metadata["evidence_kind"] == "query_result"


def test_sql_schema_evidence_is_stable_and_table_scoped():
    tables = [
        {
            "table_name": "payments",
            "columns": [{"name": "id", "declared_type": "INTEGER"}],
            "foreign_keys": [],
            "indexes": [],
        }
    ]

    first = sql_schema_to_evidence(tables=tables, database_identity="sqlite/sha256/demo")
    second = sql_schema_to_evidence(tables=tables, database_identity="sqlite/sha256/demo")

    assert first[0].evidence_id == second[0].evidence_id
    assert first[0].locator.endswith("/schema/payments")
    assert first[0].metadata["evidence_kind"] == "database_schema"


def test_local_document_identity_survives_reranking():
    first = RetrievedChunk(
        chunk_id="runtime-id-1",
        content="Policy fact",
        filename="policy.pdf",
        page_start=4,
        page_end=4,
        section="Fees",
        score=0.99,
        document_sha256="a" * 64,
        chunk_index=3,
    )
    reranked = RetrievedChunk(
        chunk_id="runtime-id-2",
        content="Policy fact",
        filename="policy-renamed.pdf",
        page_start=4,
        page_end=4,
        section="Fees",
        score=0.31,
        document_sha256="a" * 64,
        chunk_index=3,
    )

    first_record = retrieved_chunks_to_evidence([first], knowledge_base_ids=["kb-1"], query="fees")[
        0
    ]
    second_record = retrieved_chunks_to_evidence(
        [reranked], knowledge_base_ids=["kb-1"], query="fees"
    )[0]

    assert first_record.evidence_id == second_record.evidence_id
    assert first_record.locator == f"document://sha256/{'a' * 64}#chunk=3"


def test_fee_evidence_preserves_calculation_and_rule_provenance():
    record = fee_calculation_to_evidence(_fee_calculation(), dataset_fingerprint="snapshot-1")

    assert record.source is EvidenceSource.FEE_ENGINE
    assert record.content["total_fee"] == "0.125"
    assert record.metadata["fee_rule_locators"] == ["fees.json#ID=10"]
    assert record.evidence_id.startswith("ev1_fee_engine_")


def test_minimal_workflow_deduplicates_records_by_evidence_id():
    record = EvidenceRecord.create(
        source=EvidenceSource.SQL,
        locator="sql://demo/query/1#row=1",
        content={"total": 2},
    )

    def collector(_request):
        return EvidenceBatch(
            source=EvidenceSource.SQL,
            status=EvidenceBatchStatus.OK,
            records=(record,),
        )

    ledger = run_minimal_evidence_workflow(
        question="What is the total?",
        requests=[
            EvidenceRequest(source="sql", query="SELECT 2"),
            EvidenceRequest(source="sql", query="SELECT 2"),
        ],
        collector=collector,
    )

    assert ledger.records == (record,)
    assert f"[{record.evidence_id}]" in ledger.to_markdown()


def test_sql_evidence_rejects_writes_and_multiple_statements():
    assert _validate_read_only_sql("SELECT 1;") == "SELECT 1"
    with pytest.raises(ValueError, match="read-only"):
        _validate_read_only_sql("DELETE FROM payments")
    with pytest.raises(ValueError, match="multiple statements"):
        _validate_read_only_sql("SELECT 1; SELECT 2")
    with pytest.raises(ValueError, match="mutating keyword"):
        _validate_read_only_sql("WITH rows AS (SELECT 1) DELETE FROM payments")


def test_unified_tool_returns_structured_error_without_invented_evidence():
    payload = json.loads(
        collect_evidence.invoke(
            {
                "source": "fee_engine",
                "psp_reference": "definitely-missing-reference",
            }
        )
    )

    assert payload["source"] == "fee_engine"
    assert payload["status"] == "ERROR"
    assert payload["records"] == []
    assert payload["warnings"]
