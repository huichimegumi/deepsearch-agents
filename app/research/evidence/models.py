from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Mapping

SCHEMA_VERSION = "1.0"


class EvidenceSource(StrEnum):
    FEE_ENGINE = "fee_engine"
    SQL = "sql"
    LOCAL_DOCUMENT = "local_document"


class EvidenceBatchStatus(StrEnum):
    OK = "OK"
    NO_EVIDENCE = "NO_EVIDENCE"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"


def json_safe(value: Any) -> Any:
    """Return a deterministic, JSON-compatible representation."""
    if is_dataclass(value) and not isinstance(value, type):
        return json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in sorted(value.items(), key=str)}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((json_safe(item) for item in value), key=_canonical_json)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _canonical_json(value: Any) -> str:
    return json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_evidence_id(
    source: EvidenceSource,
    *,
    locator: str,
    content: Any,
    identity: Mapping[str, Any] | None = None,
) -> str:
    """Build a content-addressed ID from stable source identity, never runtime metadata."""
    payload = {
        "schema_version": SCHEMA_VERSION,
        "source": source.value,
        "locator": locator,
        "identity": json_safe(identity or {}),
        "content_sha256": hashlib.sha256(_canonical_json(content).encode("utf-8")).hexdigest(),
    }
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:24]
    return f"ev1_{source.value}_{digest}"


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    source: EvidenceSource
    locator: str
    content: Any
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        source: EvidenceSource,
        locator: str,
        content: Any,
        metadata: Mapping[str, Any] | None = None,
        identity: Mapping[str, Any] | None = None,
    ) -> EvidenceRecord:
        safe_content = json_safe(content)
        return cls(
            evidence_id=stable_evidence_id(
                source,
                locator=locator,
                content=safe_content,
                identity=identity,
            ),
            source=source,
            locator=locator,
            content=safe_content,
            metadata=json_safe(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_id": self.evidence_id,
            "source": self.source.value,
            "locator": self.locator,
            "content": json_safe(self.content),
            "metadata": json_safe(self.metadata),
        }


@dataclass(frozen=True)
class EvidenceBatch:
    source: EvidenceSource
    status: EvidenceBatchStatus
    records: tuple[EvidenceRecord, ...] = ()
    warnings: tuple[str, ...] = ()
    query: str | None = None
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source.value,
            "status": self.status.value,
            "query": self.query,
            "records": [record.to_dict() for record in self.records],
            "warnings": list(self.warnings),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)
