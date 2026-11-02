"""Bounded source adapters shared by API research and offline snapshot evaluation."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.research.evidence.models import EvidenceRecord, EvidenceSource


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]", text.lower())) - {
        "the",
        "and",
        "for",
        "what",
        "which",
        "from",
        "with",
        "this",
        "that",
        "are",
        "how",
        "does",
        "only",
        "use",
    }


@dataclass
class SourceCatalog:
    sqlite_path: Path | None = None
    documents: list[dict] | None = None
    web_pages: list[dict] | None = None
    allowed_sources: tuple[str, ...] = ("local_document", "web")
    schema_notes: str = ""
    knowledge_base: str = "all"
    _cache: dict[str, tuple[list[dict], list[str]]] = field(default_factory=dict)

    def describe(self) -> dict:
        description: dict = {"allowed_sources": self.allowed_sources}
        if self.sqlite_path and "sql" in self.allowed_sources:
            from app.tools.evidence_tool import _collect_sqlite

            batch = _collect_sqlite("", "describe_schema", self.sqlite_path)
            description["sql_schema"] = [row.to_dict() for row in batch.records]
        if self.schema_notes:
            description["schema_notes"] = self.schema_notes
        for source, pages in (("local_document", self.documents), ("web", self.web_pages)):
            if pages is not None and source in self.allowed_sources:
                description[source] = [
                    {"title": row["title"], "locator": row["locator"]} for row in pages
                ]
                description[f"{source}_mode"] = "versioned_snapshot_search"
        return description

    def collect(self, source: str, query: str) -> tuple[list[dict], list[str]]:
        if source not in self.allowed_sources:
            raise ValueError("source_not_allowed")
        pages = (
            self.documents
            if source == "local_document"
            else self.web_pages
            if source == "web"
            else None
        )
        version = (
            hashlib.sha256(json.dumps(pages, sort_keys=True).encode()).hexdigest()
            if pages is not None
            else "live"
        )
        if source == "sql" and self.sqlite_path:
            stat = self.sqlite_path.stat()
            version = f"{self.sqlite_path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}"
        key = json.dumps([source, query, version, self.knowledge_base])
        if key in self._cache:
            records, warnings = self._cache[key]
            return records, [*warnings, "content-addressed request cache hit"]
        if pages is not None:
            records = self._search_snapshot(source, query, pages)
            warnings = ["snapshot_only: no live search or fetch performed"]
        elif source == "web":
            from app.research.evidence.adapters import web_results_to_evidence
            from app.search.models import SearchRequest
            from app.search.service import get_search_service

            response = get_search_service().search(
                SearchRequest(
                    queries=[query],
                    backend="duckduckgo",
                    max_results=3,
                    fetch_full_page=True,
                    max_fetched_pages=2,
                )
            )
            records = [row.to_dict() for row in web_results_to_evidence(response.results)]
            warnings = response.notices
        else:
            from app.tools.evidence_tool import (
                _collect_fee,
                _collect_local_documents,
                _collect_sql,
                _collect_sqlite,
            )

            if source == "sql":
                batch = (
                    _collect_sqlite(query, "query", self.sqlite_path)
                    if self.sqlite_path
                    else _collect_sql(query, "query")
                )
            elif source == "local_document":
                batch = _collect_local_documents(query, self.knowledge_base)
            elif source == "fee_engine":
                batch = _collect_fee(query, None)
            else:
                raise ValueError("unsupported_source")
            records = [row.to_dict() for row in batch.records]
            warnings = list(batch.warnings)
            if batch.status.value == "ERROR":
                raise RuntimeError("; ".join(warnings))
        self._cache[key] = (records, warnings)
        return records, warnings

    def _search_snapshot(self, source: str, query: str, pages: list[dict]) -> list[dict]:
        query_words = _tokens(query)
        candidates = []
        for page in pages:
            text = page["text"]
            fingerprint = hashlib.sha256(text.encode()).hexdigest()
            for start in range(0, len(text), 2000):
                chunk = text[start : start + 2400]
                words = _tokens(chunk)
                overlap = query_words & words
                if not overlap:
                    continue
                rank = len(overlap) / math.sqrt(max(1, len(words)))
                title_matches = len(query_words & _tokens(page["title"]))
                rank += title_matches * 0.15
                record = EvidenceRecord.create(
                    source=EvidenceSource(source),
                    locator=f"{page['locator']}#offset={start}",
                    content=chunk,
                    identity={"snapshot_sha256": fingerprint, "offset": start},
                    metadata={
                        "title": page["title"],
                        "snapshot_sha256": fingerprint,
                        "start_char": start,
                        "content_scope": "source_excerpt",
                        "retrieval": "cpu_lexical",
                    },
                ).to_dict()
                candidates.append((rank, record))
        candidates.sort(key=lambda row: (-row[0], row[1]["locator"]))
        return [row[1] for row in candidates[:4]]
