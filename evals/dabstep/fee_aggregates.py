"""Deterministic fee breakdowns for the bounded public DABStep writer."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from app.research.fee_engine.dataset import FeeDataset
from evals.dabstep.common import HERE, default_data_dir

OUTPUT = HERE / "fee_aggregates.json"
REFERENCE = HERE / "fee_reference_results.json"
DIMENSIONS = ("merchant", "aci", "card_scheme", "intracountry", "merchant_aci")


def build(data_dir: Path) -> dict:
    dataset = FeeDataset.from_directory(data_dir)
    groups: dict[str, dict[str, dict]] = {name: defaultdict(_empty) for name in DIMENSIONS}
    for payment in dataset.payments:
        rules = dataset.applicable_rules(payment)
        fee = sum(
            (
                rule.fixed_amount + rule.rate * payment.eur_amount / Decimal("10000")
                for rule in rules
            ),
            Decimal("0"),
        )
        keys = {
            "merchant": payment.merchant,
            "aci": payment.aci,
            "card_scheme": payment.card_scheme,
            "intracountry": str(payment.intracountry).lower(),
            "merchant_aci": f"{payment.merchant}|{payment.aci}",
        }
        for dimension, key in keys.items():
            group = groups[dimension][key]
            group["transactions"] += 1
            group["volume_eur"] += payment.eur_amount
            group["matched_fee_eur"] += fee
            group["matched_transactions"] += bool(rules)
            group["unpriced_transactions"] += not rules
            group["fraudulent_disputes"] += payment.has_fraudulent_dispute
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    if reference["dataset_revision"] != data_dir.name:
        raise ValueError("fee_reference_revision_mismatch")
    expected = Decimal(reference["totals"]["matched_fee_total_eur"])
    observed = sum((row["matched_fee_eur"] for row in groups["merchant"].values()), Decimal("0"))
    if abs(expected - observed) > Decimal("0.000001"):
        raise ValueError("fee_reference_total_mismatch")
    return {
        "schema_version": 1,
        "dataset_revision": data_dir.name,
        "dataset_fingerprint": dataset.fingerprint,
        "scope": "matched fee rules only; unpriced transactions are excluded from fee totals",
        "fee_formula": reference["engine_policy"]["fee_formula"],
        "reference_matched_fee_total_eur": str(expected),
        "groups": {
            dimension: [{"key": key, **_serialize(row)} for key, row in sorted(values.items())]
            for dimension, values in groups.items()
        },
    }


def _empty() -> dict:
    return {
        "transactions": 0,
        "matched_transactions": 0,
        "unpriced_transactions": 0,
        "fraudulent_disputes": 0,
        "volume_eur": Decimal("0"),
        "matched_fee_eur": Decimal("0"),
    }


def _serialize(row: dict) -> dict:
    return {key: str(value) if isinstance(value, Decimal) else value for key, value in row.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = build(default_data_dir())
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
