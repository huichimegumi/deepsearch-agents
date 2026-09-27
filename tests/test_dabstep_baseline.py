import json
import re
from pathlib import Path

from evals.dabstep.reference_queries import REFERENCE_QUERIES

ROOT = Path(__file__).resolve().parents[1]
DABSTEP = ROOT / "evals" / "dabstep"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_dataset_lock_is_immutable_and_complete():
    lock = _load(DABSTEP / "dataset.lock.json")
    assert re.fullmatch(r"[0-9a-f]{40}", lock["revision"])
    assert len(lock["files"]) == 8
    assert len({item["path"] for item in lock["files"]}) == 8
    assert all(item["bytes"] > 0 for item in lock["files"])
    assert all(re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) for item in lock["files"])
    assert lock["license"]["status"] == "not_declared_in_repository"

    adyen_lock = _load(DABSTEP / "adyen_dev.lock.json")
    assert re.fullmatch(r"[0-9a-f]{40}", adyen_lock["revision"])
    assert re.fullmatch(r"[0-9a-f]{64}", adyen_lock["sha256"])
    assert adyen_lock["license"] == "cc-by-4.0"


def test_selected_task_subset_has_frozen_splits_and_original_ids():
    rows = [
        json.loads(line)
        for line in (DABSTEP / "selected_tasks.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 8
    assert {row["source_id"] for row in rows} == {0, 2, 3, 20, 41, 47, 84, 85}
    assert sum(row["split"] == "dev" for row in rows) == 2
    assert sum(row["split"] == "holdout" for row in rows) == 6
    assert all(row["checklist"].strip() for row in rows)
    assert all(row["known_limitations"] is not None for row in rows)


def test_reference_queries_are_read_only_and_snapshot_is_complete():
    expected = _load(DABSTEP / "reference_results.json")
    assert set(expected["results"]) == set(REFERENCE_QUERIES)
    for sql in REFERENCE_QUERIES.values():
        assert sql.lstrip().upper().startswith("SELECT")
        assert not re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE)\b", sql, re.I)


def test_audit_snapshot_records_known_answerability_gaps():
    audit = _load(DABSTEP / "audit_snapshot.json")
    assert audit["tasks"]["total"] == 100
    assert len(audit["tasks"]["empty_checklist_ids"]) == 20
    assert audit["payments"]["rows"] == 138236
    assert audit["cross_source"]["transaction_merchants"] == 5
    assert audit["fee_rules"]["rows"] == 1000
    assert audit["answerability_gaps"]


def test_fee_reference_covers_every_transaction_and_independent_checks_pass():
    reference = _load(DABSTEP / "fee_reference_results.json")
    coverage = reference["coverage"]
    assert coverage["transaction_count"] == 138236
    assert sum(coverage["status_counts"].values()) == coverage["transaction_count"]
    assert coverage["all_transactions_have_status"]
    assert reference["public_dev_validation"]["passed"]
    assert reference["public_dev_validation"]["hard_check_count"] == 6
    assert reference["public_dev_validation"]["known_upstream_inconsistency_count"] == 1
    assert reference["sql_cross_validation"]["status"] == "PASSED"
    assert reference["sql_cross_validation"]["sample_count"] == 500
