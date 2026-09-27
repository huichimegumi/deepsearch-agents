from __future__ import annotations

import hashlib
from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, text

from evals.dabstep.fee_dataset import DABStepFeeDataset, PaymentRecord

MATCH_SQL = """
WITH monthly AS (
    SELECT
        merchant,
        transaction_month,
        SUM(eur_amount) AS monthly_volume,
        SUM(CASE WHEN has_fraudulent_dispute = 1 THEN eur_amount ELSE 0 END)
            / SUM(eur_amount) AS monthly_fraud_rate
    FROM payments
    GROUP BY merchant, transaction_month
)
SELECT
    CAST(p.psp_reference AS TEXT) AS psp_reference,
    f.ID AS fee_id,
    CAST(ROUND((f.fixed_amount + f.rate * p.eur_amount / 10000.0) * 1000000) AS INTEGER)
        AS fee_micros
FROM payments p
JOIN merchants m ON m.merchant = p.merchant
JOIN monthly mm
    ON mm.merchant = p.merchant AND mm.transaction_month = p.transaction_month
JOIN fee_rules f ON f.card_scheme = p.card_scheme
WHERE CAST(p.psp_reference AS TEXT) IN ({placeholders})
  AND (
      NOT EXISTS (SELECT 1 FROM fee_rule_account_types x WHERE x.fee_id = f.ID)
      OR EXISTS (
          SELECT 1 FROM fee_rule_account_types x
          WHERE x.fee_id = f.ID AND x.account_type = m.account_type
      )
  )
  AND (
      f.capture_delay IS NULL
      OR f.capture_delay = m.capture_delay
      OR (
          m.capture_delay NOT IN ('manual', 'immediate')
          AND (
              (f.capture_delay = '<3' AND CAST(m.capture_delay AS REAL) < 3)
              OR (f.capture_delay = '3-5' AND CAST(m.capture_delay AS REAL) >= 3
                  AND CAST(m.capture_delay AS REAL) <= 5)
              OR (f.capture_delay = '>5' AND CAST(m.capture_delay AS REAL) > 5)
          )
      )
  )
  AND (
      f.monthly_fraud_level IS NULL
      OR (f.monthly_fraud_level = '<7.2%' AND mm.monthly_fraud_rate < 0.072)
      OR (f.monthly_fraud_level = '7.2%-7.7%' AND mm.monthly_fraud_rate >= 0.072
          AND mm.monthly_fraud_rate <= 0.077)
      OR (f.monthly_fraud_level = '7.7%-8.3%' AND mm.monthly_fraud_rate >= 0.077
          AND mm.monthly_fraud_rate <= 0.083)
      OR (f.monthly_fraud_level = '>8.3%' AND mm.monthly_fraud_rate > 0.083)
  )
  AND (
      f.monthly_volume IS NULL
      OR (f.monthly_volume = '<100k' AND mm.monthly_volume < 100000)
      OR (f.monthly_volume = '100k-1m' AND mm.monthly_volume >= 100000
          AND mm.monthly_volume <= 1000000)
      OR (f.monthly_volume = '1m-5m' AND mm.monthly_volume >= 1000000
          AND mm.monthly_volume <= 5000000)
      OR (f.monthly_volume = '>5m' AND mm.monthly_volume > 5000000)
  )
  AND (
      NOT EXISTS (SELECT 1 FROM fee_rule_mccs x WHERE x.fee_id = f.ID)
      OR EXISTS (
          SELECT 1 FROM fee_rule_mccs x
          WHERE x.fee_id = f.ID AND x.mcc = m.merchant_category_code
      )
  )
  AND (f.is_credit IS NULL OR f.is_credit = p.is_credit)
  AND (
      NOT EXISTS (SELECT 1 FROM fee_rule_acis x WHERE x.fee_id = f.ID)
      OR EXISTS (
          SELECT 1 FROM fee_rule_acis x
          WHERE x.fee_id = f.ID AND x.aci = p.aci
      )
  )
  AND (
      f.intracountry IS NULL
      OR f.intracountry = CASE
          WHEN p.issuing_country = p.acquirer_country THEN 1 ELSE 0 END
  )
ORDER BY psp_reference, fee_id
"""


def cross_validate_sql(
    dataset: DABStepFeeDataset,
    database_url: str,
    *,
    sample_size: int = 500,
) -> dict[str, Any]:
    if not database_url.startswith("sqlite"):
        return {
            "status": "SKIPPED",
            "reason": "The independent reference query currently targets SQLite semantics.",
        }
    samples = _diverse_samples(dataset, sample_size)
    placeholders = ",".join(f":p{index}" for index in range(len(samples)))
    parameters = {f"p{index}": payment.psp_reference for index, payment in enumerate(samples)}
    query = MATCH_SQL.format(placeholders=placeholders)

    sql_ids: dict[str, set[int]] = defaultdict(set)
    sql_micros: dict[str, int] = defaultdict(int)
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            for row in connection.execute(text(query), parameters):
                reference = str(row.psp_reference)
                sql_ids[reference].add(int(row.fee_id))
                sql_micros[reference] += int(row.fee_micros)
    finally:
        engine.dispose()

    id_mismatches: list[str] = []
    amount_mismatches: list[str] = []
    sample_fingerprint = hashlib.sha256()
    for payment in samples:
        reference = payment.psp_reference
        sample_fingerprint.update(f"{reference}\n".encode())
        rules = dataset.applicable_rules(payment)
        python_ids = {rule.rule_id for rule in rules}
        python_fee = dataset.fast_total_fee(payment)
        python_micros = int(python_fee * Decimal("1000000"))
        if python_ids != sql_ids[reference]:
            id_mismatches.append(reference)
        if python_micros != sql_micros[reference]:
            amount_mismatches.append(reference)

    return {
        "status": "PASSED" if not id_mismatches and not amount_mismatches else "FAILED",
        "sample_count": len(samples),
        "sample_sha256": sample_fingerprint.hexdigest(),
        "rule_id_mismatch_count": len(id_mismatches),
        "fee_amount_mismatch_count": len(amount_mismatches),
        "rule_id_mismatch_examples": id_mismatches[:10],
        "fee_amount_mismatch_examples": amount_mismatches[:10],
    }


def _diverse_samples(
    dataset: DABStepFeeDataset,
    sample_size: int,
) -> list[PaymentRecord]:
    selected: list[PaymentRecord] = []
    seen_contexts = set()
    for payment in dataset.payments:
        context = dataset.context_for(payment)
        if context in seen_contexts:
            continue
        seen_contexts.add(context)
        selected.append(payment)
        if len(selected) >= sample_size:
            break
    return selected
