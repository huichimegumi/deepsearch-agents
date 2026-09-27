from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from typing import Any, Iterable, Sequence

from app.rag.retrieval import RetrievedChunk
from app.research.evidence.models import EvidenceRecord, EvidenceSource, json_safe
from app.research.fee_engine import FeeCalculation


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_sql(query: str) -> str:
    """Normalize insignificant SQL whitespace for stable query identities."""
    return re.sub(r"\s+", " ", query.strip().rstrip(";")).strip()


def fee_calculation_to_evidence(
    calculation: FeeCalculation,
    *,
    dataset_fingerprint: str,
) -> EvidenceRecord:
    content = calculation.to_dict()
    rule_ids = ",".join(str(item) for item in calculation.matched_fee_rule_ids) or "none"
    locator = (
        f"fee://{dataset_fingerprint}/transactions/{calculation.psp_reference}?rules={rule_ids}"
    )
    return EvidenceRecord.create(
        source=EvidenceSource.FEE_ENGINE,
        locator=locator,
        content=content,
        identity={
            "dataset_fingerprint": dataset_fingerprint,
            "psp_reference": calculation.psp_reference,
        },
        metadata={
            "calculation_status": calculation.status.value,
            "fee_rule_locators": [
                component.provenance.source_locator for component in calculation.components
            ],
        },
    )


def sql_rows_to_evidence(
    *,
    query: str,
    columns: Sequence[str],
    rows: Iterable[Sequence[Any]],
    database_identity: str,
) -> tuple[EvidenceRecord, ...]:
    normalized_query = normalize_sql(query)
    query_digest = _digest(normalized_query)[:24]
    duplicates: defaultdict[str, int] = defaultdict(int)
    records: list[EvidenceRecord] = []
    for row in rows:
        content = {column: json_safe(value) for column, value in zip(columns, row, strict=True)}
        row_json = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        row_digest = _digest(row_json)[:24]
        duplicate_index = duplicates[row_digest]
        duplicates[row_digest] += 1
        locator = (
            f"sql://{database_identity}/query/{query_digest}#row={row_digest}:{duplicate_index}"
        )
        records.append(
            EvidenceRecord.create(
                source=EvidenceSource.SQL,
                locator=locator,
                content=content,
                identity={
                    "database": database_identity,
                    "query_sha256": _digest(normalized_query),
                    "row_sha256": _digest(row_json),
                    "duplicate_index": duplicate_index,
                },
                metadata={"query": normalized_query},
            )
        )
    return tuple(records)


def retrieved_chunks_to_evidence(
    hits: Iterable[RetrievedChunk],
    *,
    knowledge_base_ids: Sequence[str],
    query: str,
) -> tuple[EvidenceRecord, ...]:
    records: list[EvidenceRecord] = []
    for hit in hits:
        content_digest = _digest(hit.content)
        document_identity = hit.document_sha256 or _digest(hit.filename)
        chunk_identity = (
            str(hit.chunk_index) if hit.chunk_index is not None else content_digest[:24]
        )
        locator = f"document://sha256/{document_identity}#chunk={chunk_identity}"
        records.append(
            EvidenceRecord.create(
                source=EvidenceSource.LOCAL_DOCUMENT,
                locator=locator,
                content=hit.content,
                identity={
                    "document_sha256": document_identity,
                    "chunk": chunk_identity,
                    "content_sha256": content_digest,
                },
                metadata={
                    "chunk_id": hit.chunk_id,
                    "chunk_index": hit.chunk_index,
                    "filename": hit.filename,
                    "page_start": hit.page_start,
                    "page_end": hit.page_end,
                    "section": hit.section,
                    "citation": hit.citation,
                    "score": hit.score,
                    "knowledge_base_ids": list(knowledge_base_ids),
                    "query": query,
                },
            )
        )
    return tuple(records)
