"""Portable structured research delivery; independent of evaluation labels."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ReportClaim(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=8)


class ReportFact(BaseModel):
    metric: str = Field(min_length=1, max_length=100)
    value: str = Field(max_length=100)
    evidence_id: str
    path: list[str | int] = Field(default_factory=list, max_length=8)

    @field_validator("value")
    @classmethod
    def finite_number(cls, value: str) -> str:
        if not Decimal(value).is_finite():
            raise ValueError("nonfinite_report_fact")
        return value


class ResearchReport(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    answerability: Literal["answered", "partial", "insufficient_evidence"]
    claims: list[ReportClaim] = Field(default_factory=list, max_length=24)
    facts: list[ReportFact] = Field(default_factory=list, max_length=24)
    limitations: list[str] = Field(default_factory=list, max_length=12)

    def render(self) -> str:
        lines = [f"# {self.title}", ""]
        for claim in self.claims:
            lines.append(claim.text + " " + " ".join(f"[{key}]" for key in claim.evidence_ids))
            lines.append("")
        if self.facts:
            lines.extend(["| Metric | Value | Evidence |", "| --- | ---: | --- |"])
            for fact in self.facts:
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
