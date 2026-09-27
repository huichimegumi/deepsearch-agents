from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from app.research.fee_engine import RuleCriteria
from evals.dabstep.common import HERE, default_data_dir, load_jsonl
from evals.dabstep.download_adyen_dev import DEFAULT_PATH as DEFAULT_DEV_PATH
from evals.dabstep.download_adyen_dev import download as download_adyen_dev
from evals.dabstep.fee_dataset import DABStepFeeDataset
from evals.dabstep.sql_fee_validation import cross_validate_sql

REFERENCE_PATH = HERE / "fee_reference_results.json"
SIX_PLACES = Decimal("0.000001")
FOURTEEN_PLACES = Decimal("0.00000000000001")


def _rounded(value: Decimal, places: Decimal) -> str:
    return format(value.quantize(places, rounding=ROUND_HALF_UP), "f")


def _id_fingerprint(values: set[int]) -> str:
    payload = ",".join(str(value) for value in sorted(values))
    return hashlib.sha256(payload.encode()).hexdigest()


def _parse_ids(value: str) -> set[int]:
    return {int(item.strip()) for item in value.split(",") if item.strip()}


def _public_dev_checks(
    dataset: DABStepFeeDataset,
    dev_path: Path,
) -> list[dict[str, Any]]:
    tasks = {str(row["task_id"]): row for row in load_jsonl(dev_path)}
    checks: list[dict[str, Any]] = []

    def numeric_average(task_id: str, criteria: RuleCriteria) -> None:
        rules = dataset.engine.matcher.filter_rules(criteria)
        amount = Decimal("10")
        actual_value = sum(
            (rule.fixed_amount + rule.rate * amount / Decimal("10000") for rule in rules),
            Decimal("0"),
        ) / Decimal(len(rules))
        actual = _rounded(actual_value, SIX_PLACES)
        expected = tasks[task_id]["answer"]
        checks.append(
            {
                "task_id": task_id,
                "kind": "average_rule_fee",
                "expected": expected,
                "actual": actual,
                "matched_rule_count": len(rules),
                "passed": actual == expected,
            }
        )

    numeric_average(
        "1273",
        RuleCriteria(card_scheme="GlobalCard", is_credit=True),
    )
    numeric_average(
        "1305",
        RuleCriteria(
            card_scheme="GlobalCard",
            account_type="H",
            merchant_category_code=5812,
        ),
    )

    partial_ids = {
        rule.rule_id
        for rule in dataset.engine.matcher.filter_rules(RuleCriteria(account_type="R", aci="B"))
    }
    expected_partial_ids = _parse_ids(tasks["1464"]["answer"])
    checks.append(_id_check("1464", "partial_rule_filter", partial_ids, expected_partial_ids))

    day_payments = [
        payment
        for payment in dataset.payments
        if payment.merchant == "Belles_cookbook_store"
        and payment.year == 2023
        and payment.day_of_year == 10
    ]
    day_ids = {
        rule.rule_id for payment in day_payments for rule in dataset.applicable_rules(payment)
    }
    expected_day_ids = _parse_ids(tasks["1681"]["answer"])
    day_check = _id_check("1681", "transaction_day_rule_union", day_ids, expected_day_ids)
    day_check["transaction_count"] = len(day_payments)
    checks.append(day_check)

    march_payments = [
        payment
        for payment in dataset.payments
        if payment.merchant == "Belles_cookbook_store"
        and payment.year == 2023
        and payment.month == 3
    ]
    march_ids = {
        rule.rule_id for payment in march_payments for rule in dataset.applicable_rules(payment)
    }
    expected_march_ids = _parse_ids(tasks["1753"]["answer"])
    march_check = _id_check("1753", "merchant_month_rule_union", march_ids, expected_march_ids)
    march_check["transaction_count"] = len(march_payments)
    checks.append(march_check)

    rule_384 = next(rule for rule in dataset.rules if rule.rule_id == 384)
    january_payments = [
        payment
        for payment in dataset.payments
        if payment.merchant == "Belles_cookbook_store"
        and payment.year == 2023
        and payment.month == 1
    ]
    applicable_384 = [
        payment for payment in january_payments if rule_384 in dataset.applicable_rules(payment)
    ]
    delta = sum(
        (
            (Decimal("1") - rule_384.rate) * payment.eur_amount / Decimal("10000")
            for payment in applicable_384
        ),
        Decimal("0"),
    )
    expected_delta = Decimal(tasks["1871"]["answer"])
    checks.append(
        {
            "task_id": "1871",
            "kind": "rate_change_delta",
            "expected": tasks["1871"]["answer"],
            "actual": _rounded(delta, FOURTEEN_PLACES),
            "applicable_transaction_count": len(applicable_384),
            "absolute_error": str(abs(delta - expected_delta)),
            "passed": abs(delta - expected_delta) <= Decimal("0.000000000001"),
        }
    )

    fraudulent_january = [payment for payment in january_payments if payment.has_fraudulent_dispute]
    candidate_costs = {
        aci: sum(
            (dataset.fast_total_fee(payment, aci=aci) for payment in fraudulent_january),
            Decimal("0"),
        )
        for aci in "ABCDEFG"
    }
    best_aci, best_cost = min(candidate_costs.items(), key=lambda item: (item[1], item[0]))
    counterfactual_actual = f"{best_aci}:{_rounded(best_cost, Decimal('0.01'))}"
    counterfactual_expected = tasks["2697"]["answer"]
    checks.append(
        {
            "task_id": "2697",
            "kind": "fraudulent_transaction_aci_counterfactual",
            "validation_role": "known_upstream_inconsistency",
            "upstream_discussion": "https://huggingface.co/datasets/adyen/DABstep/discussions/2",
            "note": (
                "The official answer is not reproducible from the documented per-transaction "
                "formula. This case is reported but excluded from hard validation."
            ),
            "expected": counterfactual_expected,
            "actual": counterfactual_actual,
            "fraudulent_transaction_count": len(fraudulent_january),
            "candidate_costs": {
                key: _rounded(value, Decimal("0.01"))
                for key, value in sorted(candidate_costs.items())
            },
            "matches_upstream_answer": counterfactual_actual == counterfactual_expected,
            "passed": True,
        }
    )
    return checks


def _id_check(
    task_id: str,
    kind: str,
    actual: set[int],
    expected: set[int],
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "kind": kind,
        "expected_count": len(expected),
        "actual_count": len(actual),
        "expected_sha256": _id_fingerprint(expected),
        "actual_sha256": _id_fingerprint(actual),
        "missing_ids": sorted(expected - actual),
        "unexpected_ids": sorted(actual - expected),
        "passed": actual == expected,
    }


def build_reference(
    data_dir: Path,
    dev_path: Path,
    *,
    database_url: str | None = None,
) -> dict[str, Any]:
    dataset = DABStepFeeDataset.from_directory(data_dir)
    public_checks = _public_dev_checks(dataset, dev_path)

    status_counts: Counter[str] = Counter()
    match_count_distribution: Counter[int] = Counter()
    merchant_totals: dict[str, Decimal] = defaultdict(Decimal)
    month_totals: dict[tuple[str, int, int], Decimal] = defaultdict(Decimal)
    total_fee = Decimal("0")
    for payment in dataset.payments:
        rules = dataset.applicable_rules(payment)
        status = "MATCHED" if rules else "NO_MATCH"
        status_counts[status] += 1
        match_count_distribution[len(rules)] += 1
        fee = sum(
            (
                rule.fixed_amount + rule.rate * payment.eur_amount / Decimal("10000")
                for rule in rules
            ),
            Decimal("0"),
        )
        total_fee += fee
        merchant_totals[payment.merchant] += fee
        month_totals[(payment.merchant, payment.year, payment.month)] += fee

    result = {
        "schema_version": 1,
        "dataset_revision": data_dir.name,
        "engine_policy": {
            "empty_lists": "wildcard",
            "range_intervals": "written a-b bounds are inclusive; literal < and > are strict",
            "monthly_fraud_rate": "fraudulent EUR volume / total EUR volume",
            "fee_formula": "fixed_amount + rate * transaction_amount / 10000 per transaction",
            "arithmetic": "decimal",
        },
        "coverage": {
            "transaction_count": len(dataset.payments),
            "status_counts": dict(sorted(status_counts.items())),
            "unpriced_transaction_count": status_counts["NO_MATCH"],
            "match_count_distribution": {
                str(key): value for key, value in sorted(match_count_distribution.items())
            },
            "all_transactions_have_status": sum(status_counts.values()) == len(dataset.payments),
        },
        "totals": {
            "matched_fee_total_eur": _rounded(total_fee, SIX_PLACES),
            "by_merchant": {
                key: {"matched_fee_total_eur": _rounded(value, SIX_PLACES)}
                for key, value in sorted(merchant_totals.items())
            },
            "by_merchant_month": [
                {
                    "merchant": key[0],
                    "year": key[1],
                    "month": key[2],
                    "matched_fee_total_eur": _rounded(value, SIX_PLACES),
                }
                for key, value in sorted(month_totals.items())
            ],
        },
        "public_dev_validation": {
            "source": "adyen/DABstep",
            "passed": all(check["passed"] for check in public_checks),
            "hard_check_count": sum(
                check.get("validation_role") != "known_upstream_inconsistency"
                for check in public_checks
            ),
            "known_upstream_inconsistency_count": sum(
                check.get("validation_role") == "known_upstream_inconsistency"
                for check in public_checks
            ),
            "checks": public_checks,
        },
    }
    if database_url is not None:
        result["sql_cross_validation"] = cross_validate_sql(dataset, database_url)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the deterministic DABStep fee engine.")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    parser.add_argument("--dev-path", type=Path, default=DEFAULT_DEV_PATH)
    parser.add_argument("--reference", type=Path, default=REFERENCE_PATH)
    parser.add_argument("--database-url", default="sqlite:///evals/dabstep/work/dabstep.sqlite")
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--no-download", action="store_true")
    args = parser.parse_args()

    if not args.no_download:
        download_adyen_dev(args.dev_path)
    actual = build_reference(
        args.data_dir,
        args.dev_path,
        database_url=args.database_url,
    )
    print(json.dumps(actual["public_dev_validation"], ensure_ascii=False, indent=2))
    if not actual["public_dev_validation"]["passed"]:
        print("public DABstep fee validation failed; reference was not updated")
        return 1
    if actual.get("sql_cross_validation", {}).get("status") == "FAILED":
        print("independent SQL cross-validation failed; reference was not updated")
        return 1
    if args.update:
        args.reference.write_text(
            json.dumps(actual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"updated {args.reference}")
        return 0
    expected = json.loads(args.reference.read_text(encoding="utf-8"))
    if actual != expected:
        print("fee reference verification failed")
        return 1
    print("fee reference verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
