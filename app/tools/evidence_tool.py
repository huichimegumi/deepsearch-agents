from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from time import monotonic
from typing import Literal

from langchain_core.tools import tool

from app.agent.runtime import get_research_trace
from app.api.audit import write_audit_event
from app.api.monitor import monitor
from app.config import get_settings
from app.rag.retrieval import hybrid_search, hybrid_search_many
from app.research.evidence import (
    EvidenceBatch,
    EvidenceBatchStatus,
    EvidenceRequest,
    EvidenceSource,
    fee_calculation_to_evidence,
    retrieved_chunks_to_evidence,
    sql_rows_to_evidence,
)
from app.research.fee_engine import FeeDataset
from app.tools.db_tools import _apply_query_timeout, _preview_sql_query, get_db_config
from app.tools.local_rag_tools import (
    _limit_hits_for_answer,
    _resolve_knowledge_bases,
)

EVIDENCE_TOOL_NAME = "统一证据工具：collect_evidence"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
READ_ONLY_SQL_PREFIXES = frozenset({"select", "with", "show", "describe", "desc", "explain"})
MUTATING_SQL_PATTERN = re.compile(
    r"\b(insert|update|delete|replace|merge|alter|drop|truncate|create|grant|revoke|call|load)\b",
    re.IGNORECASE,
)


def _error_batch(source: EvidenceSource, query: str | None, exc: Exception) -> EvidenceBatch:
    return EvidenceBatch(
        source=source,
        status=EvidenceBatchStatus.ERROR,
        query=query,
        warnings=(f"{exc.__class__.__name__}: {exc}",),
    )


def _collect_sql(query: str, operation: str) -> EvidenceBatch:
    from mysql.connector import connect

    config = get_db_config()
    database_identity = (
        f"{config.get('host', 'localhost')}:{config.get('port', 3306)}/{config['database']}"
    )
    if operation == "list_tables":
        executed_query = "SHOW TABLES"
    else:
        executed_query = _validate_read_only_sql(query)

    row_limit = get_settings().db_query_preview_rows
    connection_config = {**config, "autocommit": False}
    with connect(**connection_config) as connection:
        try:
            connection.start_transaction(readonly=True)
            with connection.cursor() as cursor:
                _apply_query_timeout(cursor)
                preview_query, limited = _preview_sql_query(executed_query, row_limit)
                cursor.execute(preview_query)
                if not cursor.description:
                    raise ValueError("SQL evidence query returned no tabular result")
                columns = [item[0] for item in cursor.description]
                rows = cursor.fetchmany(row_limit + 1)
        finally:
            connection.rollback()

    truncated = len(rows) > row_limit
    records = sql_rows_to_evidence(
        query=executed_query,
        columns=columns,
        rows=rows[:row_limit],
        database_identity=database_identity,
    )
    warnings = (
        (f"SQL evidence was truncated to {row_limit} rows; narrow the query for full coverage.",)
        if truncated
        else ()
    )
    return EvidenceBatch(
        source=EvidenceSource.SQL,
        status=(
            EvidenceBatchStatus.PARTIAL
            if truncated
            else EvidenceBatchStatus.OK
            if records
            else EvidenceBatchStatus.NO_EVIDENCE
        ),
        records=records,
        warnings=warnings or (() if records else ("SQL query returned no rows.",)),
        query=executed_query,
    )


def _validate_read_only_sql(query: str) -> str:
    cleaned = query.strip().rstrip(";").strip()
    if not cleaned:
        raise ValueError("query is required for SQL evidence")
    first_token = cleaned.split(maxsplit=1)[0].casefold()
    if first_token not in READ_ONLY_SQL_PREFIXES:
        raise ValueError("SQL evidence only permits read-only queries")
    if ";" in cleaned:
        raise ValueError("SQL evidence does not permit multiple statements")
    if MUTATING_SQL_PATTERN.search(cleaned):
        raise ValueError("SQL evidence query contains a mutating keyword")
    return cleaned


def _collect_local_documents(query: str, knowledge_base: str) -> EvidenceBatch:
    if not query.strip():
        raise ValueError("query is required for local-document evidence")
    knowledge_bases = _resolve_knowledge_bases(knowledge_base)
    if not knowledge_bases:
        return EvidenceBatch(
            source=EvidenceSource.LOCAL_DOCUMENT,
            status=EvidenceBatchStatus.NO_EVIDENCE,
            query=query,
            warnings=(f"Knowledge base not found: {knowledge_base}",),
        )
    if len(knowledge_bases) == 1:
        hits = hybrid_search(query, knowledge_bases[0].id)
    else:
        hits = hybrid_search_many(query, [item.id for item in knowledge_bases])
    hits.sort(key=lambda item: item.score, reverse=True)
    limited_hits, budget = _limit_hits_for_answer(hits)
    records = retrieved_chunks_to_evidence(
        limited_hits,
        knowledge_base_ids=[item.id for item in knowledge_bases],
        query=query,
    )
    warnings = ()
    status = EvidenceBatchStatus.OK
    if not records:
        status = EvidenceBatchStatus.NO_EVIDENCE
        warnings = ("No relevant local-document chunks were found.",)
    elif budget["truncated"]:
        status = EvidenceBatchStatus.PARTIAL
        warnings = ("Local-document evidence was bounded by the retrieval context budget.",)
    return EvidenceBatch(
        source=EvidenceSource.LOCAL_DOCUMENT,
        status=status,
        records=records,
        warnings=warnings,
        query=query,
    )


def _discover_fee_data_dir() -> Path:
    configured = os.getenv("DABSTEP_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    benchmark_root = PROJECT_ROOT / "data" / "benchmarks" / "dabstep_research"
    candidates = sorted(
        path.parent.parent
        for path in benchmark_root.glob("*/context/fees.json")
        if (path.parent / "payments.csv").is_file()
        and (path.parent / "merchant_data.json").is_file()
    )
    if len(candidates) != 1:
        raise RuntimeError(
            "Set DABSTEP_DATA_DIR to one pinned dataset directory when zero or multiple "
            "local snapshots are present."
        )
    return candidates[0]


@lru_cache(maxsize=2)
def _load_fee_dataset(data_dir: str) -> FeeDataset:
    return FeeDataset.from_directory(Path(data_dir))


def _collect_fee(psp_reference: str, aci: str | None) -> EvidenceBatch:
    if not psp_reference.strip():
        raise ValueError("psp_reference is required for fee evidence")
    data_dir = _discover_fee_data_dir()
    dataset = _load_fee_dataset(str(data_dir))
    calculation = dataset.calculate(psp_reference.strip(), aci=aci or None)
    record = fee_calculation_to_evidence(
        calculation,
        dataset_fingerprint=dataset.fingerprint,
    )
    warning = calculation.error or ""
    return EvidenceBatch(
        source=EvidenceSource.FEE_ENGINE,
        status=(
            EvidenceBatchStatus.OK
            if calculation.status.value in {"MATCHED", "NO_MATCH"}
            else EvidenceBatchStatus.PARTIAL
        ),
        records=(record,),
        warnings=(warning,) if warning else (),
        query=psp_reference,
    )


def collect_evidence_request(request: EvidenceRequest) -> EvidenceBatch:
    """Programmatic entry point used by the deterministic minimal workflow."""
    try:
        source = EvidenceSource(request.source)
    except ValueError as exc:
        raise ValueError(f"unsupported evidence source: {request.source}") from exc
    try:
        if source is EvidenceSource.SQL:
            return _collect_sql(request.query, "query")
        if source is EvidenceSource.LOCAL_DOCUMENT:
            return _collect_local_documents(request.query, request.knowledge_base)
        return _collect_fee(request.psp_reference, None)
    except Exception as exc:  # noqa: BLE001 - tool errors are returned as structured batches
        return _error_batch(source, request.query or request.psp_reference, exc)


@tool
def collect_evidence(
    source: Literal["fee_engine", "sql", "local_document"],
    query: str = "",
    knowledge_base: str = "all",
    psp_reference: str = "",
    aci: str = "",
    operation: Literal["query", "list_tables"] = "query",
) -> str:
    """Collect bounded, traceable evidence with stable evidence_id values.

    Use source=sql with a read-only query (or operation=list_tables),
    source=local_document with a retrieval query and optional knowledge-base name,
    or source=fee_engine with a PSP reference and optional ACI override.
    The returned JSON is the evidence ledger input; cite its evidence_id values unchanged.
    """
    started_at = monotonic()
    source_type = EvidenceSource(source)
    monitor.report_tool(
        tool_name=EVIDENCE_TOOL_NAME,
        args={
            "source": source,
            "query": query,
            "knowledge_base": knowledge_base,
            "psp_reference": psp_reference,
            "aci": aci,
            "operation": operation,
        },
    )
    try:
        if source_type is EvidenceSource.SQL:
            batch = _collect_sql(query, operation)
        elif source_type is EvidenceSource.LOCAL_DOCUMENT:
            batch = _collect_local_documents(query, knowledge_base)
        else:
            batch = _collect_fee(psp_reference, aci or None)
    except Exception as exc:  # noqa: BLE001 - keep agent failures inspectable and bounded
        batch = _error_batch(source_type, query or psp_reference, exc)
    event = {
        "source": source,
        "status": batch.status.value,
        "evidence_ids": [record.evidence_id for record in batch.records],
        "locators": [record.locator for record in batch.records],
        "record_count": len(batch.records),
        "warnings": list(batch.warnings),
        "elapsed_ms": round((monotonic() - started_at) * 1000),
    }
    trace = get_research_trace()
    if trace is not None:
        trace.record_evidence(batch.records)
    write_audit_event("evidence_collected", event)
    if batch.status is EvidenceBatchStatus.ERROR:
        monitor.report_tool_error(EVIDENCE_TOOL_NAME, "; ".join(batch.warnings), event)
    else:
        monitor.report_tool_end(EVIDENCE_TOOL_NAME, event)
    return batch.to_json()


__all__ = ["EVIDENCE_TOOL_NAME", "collect_evidence", "collect_evidence_request"]
