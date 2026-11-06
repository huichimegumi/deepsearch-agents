import sqlite3

import pytest

from app.research.metric_selection import MetricSelection, execute_selection
from app.research.metrics import MetricRegistry
from app.research.observed_values import observe_values


def fixture(tmp_path):
    db = tmp_path / "observed.sqlite"
    with sqlite3.connect(db) as conn:
        conn.executescript("CREATE TABLE items(name TEXT, region TEXT, status TEXT, amount REAL);")
        conn.executemany(
            "INSERT INTO items VALUES(?,?,?,?)",
            [(f"item-{i:02}", "North", "North" if i == 0 else "Active", i) for i in range(20)],
        )
    registry = MetricRegistry(db, [])
    keys = {ref.split(".")[1]: key for key, ref in registry.columns.items()}
    return registry, keys


def test_values_are_real_field_scoped_and_prefer_question_mentions(tmp_path):
    registry, keys = fixture(tmp_path)
    observed = observe_values(registry, "Find item-19", per_field=3)
    names = next(f for f in observed.fields if f["field"] == keys["name"])
    assert names["values"][0]["value"] == "item-19"
    assert not names["complete"] and observed.incomplete
    assert all(
        v.source_ref in {r["evidence_id"] for r in observed.evidence}
        for v in observed.values.values()
    )
    choice = MetricSelection(
        table="items",
        outputs=keys["name"],
        filter_1_field=keys["region"],
        filter_1_op="eq",
        filter_1_value="North",
        limit=1,
    )
    rows, _, _, _, _ = execute_selection(registry, choice, observed.values)
    assert len(rows) == 1  # Identical text in another field does not create ambiguity.
    status_key = next(
        k
        for k, v in observed.values.items()
        if v.field_ref == "items.status" and v.value == "North"
    )
    choice.filter_1_value = status_key
    with pytest.raises(ValueError, match="value_bound_to_other_field"):
        execute_selection(registry, choice, observed.values)


def test_missing_preview_value_is_not_claimed_absent_and_total_budget_is_bounded(tmp_path):
    registry, keys = fixture(tmp_path)
    observed = observe_values(registry, "unrelated", per_field=2, total=2)
    assert len(observed.values) == 2 and observed.incomplete
    candidate = MetricSelection(
        table="items",
        outputs=keys["name"],
        filter_1_field=keys["name"],
        filter_1_op="eq",
        filter_1_value="invented",
    )
    with pytest.raises(ValueError, match="unresolved_selection_value"):
        execute_selection(registry, candidate, observed.values)
    with pytest.raises(ValueError, match="invalid_observation_budget"):
        observe_values(registry, "anything", per_field=0)
