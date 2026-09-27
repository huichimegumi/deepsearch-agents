from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any, Mapping


class FeeMatchStatus(StrEnum):
    MATCHED = "MATCHED"
    NO_MATCH = "NO_MATCH"
    AMBIGUOUS_SEMANTICS = "AMBIGUOUS_SEMANTICS"
    INVALID_SOURCE_DATA = "INVALID_SOURCE_DATA"
    UNSUPPORTED_RULE = "UNSUPPORTED_RULE"


@dataclass(frozen=True)
class FeeRule:
    rule_id: int
    card_scheme: str
    account_types: tuple[str, ...]
    capture_delay: str | None
    monthly_fraud_level: str | None
    monthly_volume: str | None
    merchant_category_codes: tuple[int, ...]
    is_credit: bool | None
    acis: tuple[str, ...]
    fixed_amount: Decimal
    rate: Decimal
    intracountry: bool | None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> FeeRule:
        return cls(
            rule_id=int(value["ID"]),
            card_scheme=str(value["card_scheme"]),
            account_types=tuple(str(item) for item in value.get("account_type") or ()),
            capture_delay=_optional_string(value.get("capture_delay")),
            monthly_fraud_level=_optional_string(value.get("monthly_fraud_level")),
            monthly_volume=_optional_string(value.get("monthly_volume")),
            merchant_category_codes=tuple(
                int(item) for item in value.get("merchant_category_code") or ()
            ),
            is_credit=_optional_bool(value.get("is_credit")),
            acis=tuple(str(item) for item in value.get("aci") or ()),
            fixed_amount=Decimal(str(value["fixed_amount"])),
            rate=Decimal(str(value["rate"])),
            intracountry=_optional_bool(value.get("intracountry")),
        )


@dataclass(frozen=True)
class MerchantProfile:
    merchant: str
    capture_delay: str
    merchant_category_code: int
    account_type: str


@dataclass(frozen=True)
class MonthlyMetrics:
    merchant: str
    year: int
    month: int
    total_volume: Decimal
    fraudulent_volume: Decimal

    @property
    def fraud_rate(self) -> Decimal:
        if self.total_volume == 0:
            return Decimal("0")
        return self.fraudulent_volume / self.total_volume


@dataclass(frozen=True)
class TransactionContext:
    merchant: str
    year: int
    month: int
    card_scheme: str
    account_type: str
    capture_delay: str
    monthly_fraud_rate: Decimal
    monthly_volume: Decimal
    merchant_category_code: int
    is_credit: bool
    aci: str
    intracountry: bool


@dataclass(frozen=True)
class RuleCriteria:
    card_scheme: str | None = None
    account_type: str | None = None
    capture_delay: str | None = None
    monthly_fraud_rate: Decimal | None = None
    monthly_volume: Decimal | None = None
    merchant_category_code: int | None = None
    is_credit: bool | None = None
    aci: str | None = None
    intracountry: bool | None = None


@dataclass(frozen=True)
class FeeRuleProvenance:
    fee_rule_id: int
    source_locator: str
    matched_conditions: Mapping[str, Any]
    wildcard_conditions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fee_rule_id": self.fee_rule_id,
            "source_locator": self.source_locator,
            "matched_conditions": dict(self.matched_conditions),
            "wildcard_conditions": list(self.wildcard_conditions),
        }


@dataclass(frozen=True)
class FeeComponent:
    fee_rule_id: int
    fixed_amount: Decimal
    rate: Decimal
    variable_amount: Decimal
    total: Decimal
    provenance: FeeRuleProvenance

    def to_dict(self) -> dict[str, Any]:
        return {
            "fee_rule_id": self.fee_rule_id,
            "fixed_amount": str(self.fixed_amount),
            "rate": str(self.rate),
            "variable_amount": str(self.variable_amount),
            "total": str(self.total),
            "provenance": self.provenance.to_dict(),
        }


@dataclass(frozen=True)
class FeeCalculation:
    psp_reference: str
    status: FeeMatchStatus
    transaction_amount: Decimal
    components: tuple[FeeComponent, ...]
    total_fee: Decimal
    assumptions: tuple[str, ...] = field(default_factory=tuple)
    error: str | None = None

    @property
    def matched_fee_rule_ids(self) -> tuple[int, ...]:
        return tuple(component.fee_rule_id for component in self.components)

    def to_dict(self) -> dict[str, Any]:
        return {
            "psp_reference": self.psp_reference,
            "status": self.status.value,
            "transaction_amount": str(self.transaction_amount),
            "matched_fee_rule_ids": list(self.matched_fee_rule_ids),
            "components": [component.to_dict() for component in self.components],
            "total_fee": str(self.total_fee),
            "assumptions": list(self.assumptions),
            "error": self.error,
        }


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if value in (0, 0.0, "0", "false", "False"):
        return False
    if value in (1, 1.0, "1", "true", "True"):
        return True
    raise ValueError(f"unsupported boolean value: {value!r}")
