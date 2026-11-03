"""Portable structured research delivery; independent of evaluation labels."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ReportClaim(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=8)
    section: str | None = Field(default=None, max_length=120)


class ReportFact(BaseModel):
    metric: str = Field(min_length=1, max_length=100)
    value: str = Field(
        max_length=100,
        description="A finite decimal number encoded as a string. Omit the entire fact if unknown or not numeric; never put explanatory text here.",
    )
    evidence_id: str
    entity: str | None = Field(default=None, max_length=200)
    period: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, max_length=80)
    section: str | None = Field(default=None, max_length=120)
    path: list[str | int] = Field(
        default_factory=list,
        max_length=8,
        description="Keys/indexes into the cited record's content object, not its outer wrapper. Do not bind facts to unstructured source text.",
    )

    @field_validator("value")
    @classmethod
    def finite_number(cls, value: str) -> str:
        try:
            finite = Decimal(value).is_finite()
        except InvalidOperation as exc:
            raise ValueError("nonnumeric_report_fact") from exc
        if not finite:
            raise ValueError("nonfinite_report_fact")
        return value


class ResearchReport(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    answerability: Literal["answered", "partial", "insufficient_evidence"]
    claims: list[ReportClaim] = Field(default_factory=list, max_length=48)
    facts: list[ReportFact] = Field(
        default_factory=list,
        max_length=48,
        description="Only numeric values bound to fields in structured SQL/fee Evidence. MUST be [] for refusals, unknown values, or text-only evidence. Put qualitative findings in claims.",
    )
    limitations: list[str] = Field(default_factory=list, max_length=12)

    def render(self) -> str:
        lines = [f"# {self.title}", ""]
        groups = list(
            dict.fromkeys(
                [claim.section for claim in self.claims] + [fact.section for fact in self.facts]
            )
        )
        for section in groups:
            if section:
                lines += ["## " + section, ""]
            for claim in self.claims:
                if claim.section != section:
                    continue
                lines += [claim.text + " " + " ".join(f"[{key}]" for key in claim.evidence_ids), ""]
            facts = [fact for fact in self.facts if fact.section == section]
            scoped = any(f.entity or f.period or f.unit for f in facts)
            if facts:
                lines.extend(
                    [
                        "| Metric | Entity | Period | Value | Unit | Evidence |",
                        "| --- | --- | --- | ---: | --- | --- |",
                    ]
                    if scoped
                    else ["| Metric | Value | Evidence |", "| --- | ---: | --- |"]
                )
            for fact in facts:
                if scoped:
                    lines.append(
                        f"| {fact.metric} | {fact.entity or ''} | {fact.period or ''} | {fact.value} | {fact.unit or ''} | [{fact.evidence_id}] |"
                    )
                else:
                    lines.append(f"| {fact.metric} | {fact.value} | [{fact.evidence_id}] |")
        if self.limitations:
            lines += ["", "Evidence limitations:"] + [f"- {item}" for item in self.limitations]
        return "\n".join(lines).strip()


def numeric_binding_errors(report: ResearchReport, evidence: list[dict]) -> list[str]:
    """Verify numerical values against cited source fields, without a gold answer."""
    records = {row["evidence_id"]: row for row in evidence}
    errors = []
    for fact in report.facts:
        try:
            value = records[fact.evidence_id]["content"]
            for key in fact.path:
                value = value[key]
            if isinstance(value, bool) or Decimal(str(value)) != Decimal(fact.value):
                errors.append(f"numeric_binding_mismatch:{fact.metric}")
        except (KeyError, IndexError, TypeError, ValueError, ArithmeticError):
            errors.append(f"numeric_binding_invalid:{fact.metric}")
    return errors


def fact_identity(fact: ReportFact) -> tuple:
    """Repeated metric names are distinct only with explicit entity/time/unit scope."""
    return fact.metric, fact.entity, fact.period, fact.unit
