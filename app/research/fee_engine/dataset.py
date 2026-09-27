from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from app.research.fee_engine.calculator import FeeEngine
from app.research.fee_engine.models import (
    FeeCalculation,
    FeeRule,
    MerchantProfile,
    MonthlyMetrics,
    TransactionContext,
)


@dataclass(frozen=True)
class PaymentRecord:
    psp_reference: str
    merchant: str
    card_scheme: str
    year: int
    month: int
    day_of_year: int
    is_credit: bool
    eur_amount: Decimal
    issuing_country: str
    has_fraudulent_dispute: bool
    is_refused_by_adyen: bool
    aci: str
    acquirer_country: str

    @property
    def intracountry(self) -> bool:
        return self.issuing_country == self.acquirer_country


class FeeDataset:
    """Load the transaction context required by the deterministic fee engine."""

    def __init__(
        self,
        *,
        payments: Iterable[PaymentRecord],
        profiles: dict[str, MerchantProfile],
        rules: Iterable[FeeRule],
        fingerprint: str = "unversioned",
    ) -> None:
        self.payments = tuple(payments)
        self.payments_by_reference = {item.psp_reference: item for item in self.payments}
        if len(self.payments_by_reference) != len(self.payments):
            raise ValueError("psp_reference must be unique")
        self.profiles = profiles
        self.rules = tuple(rules)
        self.engine = FeeEngine(self.rules)
        self.monthly_metrics = _build_monthly_metrics(self.payments)
        self.fingerprint = fingerprint

    @classmethod
    def from_directory(cls, data_dir: Path) -> FeeDataset:
        context = data_dir / "context"
        merchant_path = context / "merchant_data.json"
        fee_path = context / "fees.json"
        payment_path = context / "payments.csv"
        for path in (merchant_path, fee_path, payment_path):
            if not path.is_file():
                raise FileNotFoundError(f"fee dataset file not found: {path}")
        profiles = {
            item["merchant"]: MerchantProfile(
                merchant=item["merchant"],
                capture_delay=str(item["capture_delay"]),
                merchant_category_code=int(item["merchant_category_code"]),
                account_type=str(item["account_type"]),
            )
            for item in json.loads(merchant_path.read_text(encoding="utf-8"))
        }
        rules = tuple(
            FeeRule.from_mapping(item) for item in json.loads(fee_path.read_text(encoding="utf-8"))
        )
        return cls(
            payments=_read_payments(payment_path),
            profiles=profiles,
            rules=rules,
            fingerprint=_dataset_fingerprint((merchant_path, fee_path, payment_path)),
        )

    def context_for(self, payment: PaymentRecord, *, aci: str | None = None) -> TransactionContext:
        profile = self.profiles[payment.merchant]
        metrics = self.monthly_metrics[(payment.merchant, payment.year, payment.month)]
        return TransactionContext(
            merchant=payment.merchant,
            year=payment.year,
            month=payment.month,
            card_scheme=payment.card_scheme,
            account_type=profile.account_type,
            capture_delay=profile.capture_delay,
            monthly_fraud_rate=metrics.fraud_rate,
            monthly_volume=metrics.total_volume,
            merchant_category_code=profile.merchant_category_code,
            is_credit=payment.is_credit,
            aci=aci or payment.aci,
            intracountry=payment.intracountry,
        )

    def calculate(self, psp_reference: str, *, aci: str | None = None) -> FeeCalculation:
        try:
            payment = self.payments_by_reference[psp_reference]
        except KeyError as exc:
            raise KeyError(f"unknown psp_reference: {psp_reference}") from exc
        return self.engine.calculate(
            psp_reference=payment.psp_reference,
            amount=payment.eur_amount,
            context=self.context_for(payment, aci=aci),
        )

    def applicable_rules(self, payment: PaymentRecord, *, aci: str | None = None):
        return self.engine.matcher.applicable_rules(self.context_for(payment, aci=aci))

    def fast_total_fee(self, payment: PaymentRecord, *, aci: str | None = None) -> Decimal:
        return sum(
            (
                rule.fixed_amount + rule.rate * payment.eur_amount / Decimal("10000")
                for rule in self.applicable_rules(payment, aci=aci)
            ),
            Decimal("0"),
        )


def _dataset_fingerprint(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        digest.update(path.name.encode("utf-8"))
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()[:24]


def _read_payments(path: Path) -> Iterable[PaymentRecord]:
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            date = datetime(int(row["year"]), 1, 1) + timedelta(days=int(row["day_of_year"]) - 1)
            yield PaymentRecord(
                psp_reference=row["psp_reference"],
                merchant=row["merchant"],
                card_scheme=row["card_scheme"],
                year=int(row["year"]),
                month=date.month,
                day_of_year=int(row["day_of_year"]),
                is_credit=_parse_bool(row["is_credit"]),
                eur_amount=Decimal(row["eur_amount"]),
                issuing_country=row["issuing_country"],
                has_fraudulent_dispute=_parse_bool(row["has_fraudulent_dispute"]),
                is_refused_by_adyen=_parse_bool(row["is_refused_by_adyen"]),
                aci=row["aci"],
                acquirer_country=row["acquirer_country"],
            )


def _build_monthly_metrics(
    payments: Iterable[PaymentRecord],
) -> dict[tuple[str, int, int], MonthlyMetrics]:
    totals: dict[tuple[str, int, int], Decimal] = defaultdict(Decimal)
    fraud: dict[tuple[str, int, int], Decimal] = defaultdict(Decimal)
    for payment in payments:
        key = (payment.merchant, payment.year, payment.month)
        totals[key] += payment.eur_amount
        if payment.has_fraudulent_dispute:
            fraud[key] += payment.eur_amount
    return {
        key: MonthlyMetrics(
            merchant=key[0],
            year=key[1],
            month=key[2],
            total_volume=total,
            fraudulent_volume=fraud[key],
        )
        for key, total in totals.items()
    }


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"invalid boolean value in payments.csv: {value!r}")
