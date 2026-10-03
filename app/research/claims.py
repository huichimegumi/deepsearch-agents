from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Mapping, Sequence

from pydantic import BaseModel, Field, field_validator

CLAIM_SCHEMA_VERSION = "1.0"
EVIDENCE_CITATION_PATTERN = re.compile(
    r"\[(ev1_[a-z0-9_-]+)\]",
    re.IGNORECASE,
)


class ClaimKind(StrEnum):
    FACT = "fact"
    INFERENCE = "inference"


class ClaimIssueCode(StrEnum):
    MISSING_EVIDENCE = "missing_evidence"
    UNKNOWN_EVIDENCE = "unknown_evidence"
    MISSING_INFERENCE_LIMITATION = "missing_inference_limitation"


class ClaimDraft(BaseModel):
    """Model-produced claim proposal; the backend still decides whether it is usable."""

    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    kind: ClaimKind = ClaimKind.FACT
    limitations: list[str] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("evidence_ids", "limitations")
    @classmethod
    def _normalize_string_list(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            item = value.strip()
            if item and item not in normalized:
                normalized.append(item)
        return normalized


@dataclass(frozen=True)
class ClaimIssue:
    code: ClaimIssueCode
    detail: str


@dataclass(frozen=True)
class ValidatedClaim:
    claim_id: str
    text: str
    evidence_ids: tuple[str, ...]
    kind: ClaimKind
    limitations: tuple[str, ...] = ()
    schema_version: str = CLAIM_SCHEMA_VERSION


@dataclass(frozen=True)
class RejectedClaim:
    draft: ClaimDraft
    issues: tuple[ClaimIssue, ...]


@dataclass(frozen=True)
class ClaimValidationReport:
    accepted: tuple[ValidatedClaim, ...]
    rejected: tuple[RejectedClaim, ...]
    available_evidence_ids: tuple[str, ...]

    @property
    def referenced_evidence_ids(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                evidence_id for claim in self.accepted for evidence_id in claim.evidence_ids
            )
        )

    @property
    def unknown_evidence_ids(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                issue.detail
                for claim in self.rejected
                for issue in claim.issues
                if issue.code is ClaimIssueCode.UNKNOWN_EVIDENCE
            )
        )


@dataclass(frozen=True)
class ReportCitationValidation:
    cited_evidence_ids: tuple[str, ...]
    unknown_evidence_ids: tuple[str, ...]
    missing_required_citations: bool

    @property
    def valid(self) -> bool:
        return not self.unknown_evidence_ids and not self.missing_required_citations


def _canonical_json(value: Mapping[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_claim_id(
    *,
    text: str,
    evidence_ids: Sequence[str],
    kind: ClaimKind,
    limitations: Sequence[str],
) -> str:
    payload = {
        "schema_version": CLAIM_SCHEMA_VERSION,
        "text": text.strip(),
        "evidence_ids": sorted(set(evidence_ids)),
        "kind": kind.value,
        "limitations": list(limitations),
    }
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:24]
    return f"clm1_{digest}"


def validate_claims(
    drafts: Iterable[ClaimDraft | Mapping[str, object]],
    *,
    available_evidence_ids: Iterable[str],
) -> ClaimValidationReport:
    available = tuple(dict.fromkeys(str(item) for item in available_evidence_ids if item))
    available_set = set(available)
    accepted: list[ValidatedClaim] = []
    rejected: list[RejectedClaim] = []
    seen_claim_ids: set[str] = set()

    for value in drafts:
        draft = value if isinstance(value, ClaimDraft) else ClaimDraft.model_validate(value)
        issues: list[ClaimIssue] = []
        if not draft.evidence_ids:
            issues.append(
                ClaimIssue(
                    ClaimIssueCode.MISSING_EVIDENCE,
                    "claim has no evidence_id",
                )
            )
        for evidence_id in draft.evidence_ids:
            if evidence_id not in available_set:
                issues.append(ClaimIssue(ClaimIssueCode.UNKNOWN_EVIDENCE, evidence_id))
        if draft.kind is ClaimKind.INFERENCE and not draft.limitations:
            issues.append(
                ClaimIssue(
                    ClaimIssueCode.MISSING_INFERENCE_LIMITATION,
                    "inference must state at least one limitation",
                )
            )
        if issues:
            rejected.append(RejectedClaim(draft=draft, issues=tuple(issues)))
            continue

        claim_id = stable_claim_id(
            text=draft.text,
            evidence_ids=draft.evidence_ids,
            kind=draft.kind,
            limitations=draft.limitations,
        )
        if claim_id in seen_claim_ids:
            continue
        seen_claim_ids.add(claim_id)
        accepted.append(
            ValidatedClaim(
                claim_id=claim_id,
                text=draft.text,
                evidence_ids=tuple(draft.evidence_ids),
                kind=draft.kind,
                limitations=tuple(draft.limitations),
            )
        )

    return ClaimValidationReport(
        accepted=tuple(accepted),
        rejected=tuple(rejected),
        available_evidence_ids=available,
    )


def validate_report_citations(
    report_markdown: str,
    *,
    allowed_evidence_ids: Iterable[str],
    citations_required: bool | None = None,
) -> ReportCitationValidation:
    allowed = tuple(dict.fromkeys(str(item) for item in allowed_evidence_ids if item))
    allowed_set = set(allowed)
    cited = tuple(
        dict.fromkeys(
            match.group(1) for match in EVIDENCE_CITATION_PATTERN.finditer(report_markdown)
        )
    )
    unknown = tuple(item for item in cited if item not in allowed_set)
    require_citations = bool(allowed) if citations_required is None else citations_required
    return ReportCitationValidation(
        cited_evidence_ids=cited,
        unknown_evidence_ids=unknown,
        missing_required_citations=bool(require_citations and not cited),
    )


__all__ = [
    "ClaimDraft",
    "ClaimIssue",
    "ClaimIssueCode",
    "ClaimKind",
    "ClaimValidationReport",
    "RejectedClaim",
    "ReportCitationValidation",
    "ValidatedClaim",
    "stable_claim_id",
    "validate_claims",
    "validate_report_citations",
]
