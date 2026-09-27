from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from app.research.evidence.models import EvidenceBatch, EvidenceRecord


@dataclass(frozen=True)
class EvidenceRequest:
    source: str
    query: str = ""
    knowledge_base: str = "all"
    psp_reference: str = ""


@dataclass(frozen=True)
class EvidenceLedger:
    question: str
    records: tuple[EvidenceRecord, ...]
    warnings: tuple[str, ...]

    def to_markdown(self) -> str:
        lines = ["# Evidence Ledger", "", f"Question: {self.question}", ""]
        if not self.records:
            lines.append("No evidence records were collected.")
        for record in self.records:
            lines.extend(
                [
                    f"## [{record.evidence_id}]",
                    f"- Source: `{record.source.value}`",
                    f"- Locator: `{record.locator}`",
                    f"- Content: {record.content}",
                    "",
                ]
            )
        if self.warnings:
            lines.extend(["## Warnings", *(f"- {warning}" for warning in self.warnings)])
        return "\n".join(lines).strip()


def run_minimal_evidence_workflow(
    *,
    question: str,
    requests: Iterable[EvidenceRequest],
    collector: Callable[[EvidenceRequest], EvidenceBatch],
) -> EvidenceLedger:
    """Collect, deduplicate, and hand off evidence without an LLM synthesis step."""
    records_by_id: dict[str, EvidenceRecord] = {}
    warnings: list[str] = []
    for request in requests:
        batch = collector(request)
        warnings.extend(batch.warnings)
        for record in batch.records:
            records_by_id.setdefault(record.evidence_id, record)
    return EvidenceLedger(
        question=question,
        records=tuple(records_by_id.values()),
        warnings=tuple(dict.fromkeys(warnings)),
    )
