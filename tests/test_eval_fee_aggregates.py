"""The fee evidence is a validated, bounded aggregate of public data."""

import json
from decimal import Decimal

import pytest

from evals.benchmark_preflight import DABSTEP_DATABASE
from evals.dabstep.common import default_data_dir
from evals.dabstep.fee_aggregates import DIMENSIONS, OUTPUT, REFERENCE
from evals.simple_sql_baseline import collect_public_evidence


def test_committed_aggregates_reconcile_and_preserve_unpriced_scope():
    value = json.loads(OUTPUT.read_text(encoding="utf-8"))
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    assert value["dataset_revision"] == default_data_dir().name
    assert set(value["groups"]) == set(DIMENSIONS)
    for dimension in DIMENSIONS:
        rows = value["groups"][dimension]
        assert sum(Decimal(row["matched_fee_eur"]) for row in rows) == Decimal(
            reference["totals"]["matched_fee_total_eur"]
        )
        assert (
            sum(row["transactions"] for row in rows) == reference["coverage"]["transaction_count"]
        )
        assert (
            sum(row["unpriced_transactions"] for row in rows)
            == reference["coverage"]["unpriced_transaction_count"]
        )


@pytest.mark.skipif(
    not DABSTEP_DATABASE.is_file(), reason="Optional public DABStep SQLite snapshot not prepared"
)
def test_writer_receives_citable_fee_breakdowns():
    evidence = collect_public_evidence()
    fee_records = [row for row in evidence if row["source"] == "fee_engine"]
    assert len(fee_records) == len(DIMENSIONS)
    assert len({row["evidence_id"] for row in evidence}) == len(evidence)
    assert {row["content"]["group_by"] for row in fee_records} == set(DIMENSIONS)
    assert all("unpriced transactions" in row["content"]["scope"] for row in fee_records)
