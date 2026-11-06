import sqlite3

import pytest

from app.research.metric_selection import MetricSelection, execute_selection, plan_for
from app.research.metrics import MetricBuilder, MetricRegistry
from app.research.query_plan import BoundValue, compile_plan


def fixture(tmp_path):
    db = tmp_path / "metrics.sqlite"
    with sqlite3.connect(db) as conn:
        conn.executescript("""
        CREATE TABLE measurements(name TEXT, region TEXT, period TEXT, amount REAL, loss REAL);
        INSERT INTO measurements VALUES ('Alpha', 'N', 'Jan', 10, 20),
            ('Beta', 'N', 'Jan', 20, 10), ('Gamma', 'S', 'Jan', 100, 0),
            ('Alpha', 'N', 'Feb', 1000, 0);
        """)
    entries = [
        {
            "id": 1,
            "type": "calculation_knowledge",
            "definition": r"Net: $\text{net} = \text{amount} \times (1 - \frac{\text{loss}}{100})$.",
            "children_knowledge": -1,
        },
        {
            "id": 2,
            "type": "calculation_knowledge",
            "definition": r"Adjusted: $\text{adjusted} = \text{net} \times (\text{loss} < 15 ? 2 : 1)$.",
            "children_knowledge": [1],
        },
    ]
    registry = MetricRegistry(db, entries)
    fields = {ref.split(".")[1]: key for key, ref in registry.columns.items()}
    return registry, fields


def test_public_formulas_expand_dependencies_and_source_hashes_without_model_dag(tmp_path):
    registry, fields = fixture(tmp_path)
    selection = MetricSelection(
        table="measurements",
        outputs=f"{fields['name']},m1,m2",
        filter_1_field=fields["period"],
        filter_1_op="eq",
        filter_1_value="period",
        sort_field="m2",
        descending=True,
    )
    rows, _, _, observation, _ = execute_selection(
        registry, selection, {"period": BoundValue(value="Jan", source_ref="question")}
    )
    assert [list(row["content"].values()) for row in rows] == [
        ["Gamma", 100, 200],
        ["Beta", 18, 36],
        ["Alpha", 8, 8],
    ]
    assert set(observation["metric_sources"]) == {"m1", "m2"}
    assert all(len(value) == 64 for value in observation["metric_sources"].values())
    assert registry.catalog("measurements")[-1]["id"] == "m2"


def test_unique_anchor_resolves_actual_values_and_preserves_peer_period(tmp_path):
    registry, fields = fixture(tmp_path)
    selection = MetricSelection(
        table="measurements",
        outputs=f"{fields['name']},m1",
        anchor_field=fields["name"],
        anchor_value="who",
        peer_fields=f"{fields['region']},{fields['period']}",
        exclude_anchor=True,
        filter_1_field="m1",
        filter_1_op="gt",
        filter_1_value="anchor:m1",
        sort_field="m1",
    )
    # One exact entity has two periods, so the backend refuses to guess one.
    with pytest.raises(ValueError, match="anchor_not_unique"):
        execute_selection(registry, selection, {"who": BoundValue(value="Alpha", source_ref="web")})
    with sqlite3.connect(registry.database) as conn:
        conn.execute("DELETE FROM measurements WHERE period='Feb'")
    rows, _, _, observation, _ = execute_selection(
        registry,
        selection,
        {"who": BoundValue(value="%Al%", mode="pattern", source_ref="web-pattern")},
    )
    assert [list(r["content"].values()) for r in rows] == [["Beta", 18]]
    assert observation["anchor_records"][0]["content"][fields["period"]] == "Jan"
    with pytest.raises(ValueError, match="anchor_not_unique"):
        execute_selection(
            registry, selection, {"who": BoundValue(value="missing", source_ref="web")}
        )


def test_bands_aggregate_actual_metric_and_keep_bound_labels(tmp_path):
    registry, fields = fixture(tmp_path)
    values = {
        "low": BoundValue(value="small", source_ref="public-definition"),
        "high": BoundValue(value="large", source_ref="public-definition"),
        "period": BoundValue(value="Jan", source_ref="question"),
    }
    selection = MetricSelection(
        table="measurements",
        outputs="band,count,avg:m1",
        group_field="m1",
        band_cutoffs="18",
        band_values="low,high",
        filter_1_field=fields["period"],
        filter_1_op="eq",
        filter_1_value="period",
        sort_field="band",
        round_digits=4,
    )
    rows, _, _, _, _ = execute_selection(registry, selection, values)
    assert sorted([[r["content"][key] for key in ("band", "count", "avg_m1")] for r in rows]) == [
        ["large", 2, 59],
        ["small", 1, 8],
    ]
    selection.band_cutoffs = "18,10"
    selection.band_values = "low,high,period"
    with pytest.raises(ValueError, match="unordered_bands"):
        execute_selection(registry, selection, values)


def test_unsupported_or_untrusted_formulas_cannot_execute_python(tmp_path):
    registry, _ = fixture(tmp_path)
    entries = registry.entries + [
        {
            "id": 3,
            "type": "calculation_knowledge",
            "definition": r"$\text{bad} = __import__('os').system('false')$",
        },
        {
            "id": 4,
            "type": "calculation_knowledge",
            "definition": r"$\text{cycle} = \text{cycle} + 1$",
        },
        {
            "id": 5,
            "type": "calculation_knowledge",
            "definition": r"$\text{unknown} = \sqrt{\text{amount}}$",
        },
    ]
    registry = MetricRegistry(registry.database, entries)
    assert {row["id"] for row in registry.catalog("measurements")} & {"m3", "m4", "m5"} == set()
    for key in ("m3", "m4", "m5"):
        with pytest.raises(ValueError):
            MetricBuilder(registry).field(key)


def test_selection_never_accepts_formula_or_unbound_text_as_a_filter(tmp_path):
    registry, fields = fixture(tmp_path)
    for field, value in [("amount * 2", "10"), (fields["name"], "invented-entity")]:
        candidate = MetricSelection(
            table="measurements",
            outputs="m1",
            filter_1_field=field,
            filter_1_op="eq",
            filter_1_value=value,
        )
        with pytest.raises(ValueError):
            plan_for(registry, candidate, {})
    candidate = MetricSelection(table="measurements", outputs=f"{fields['name']},sum:m1")
    plan, values, _ = plan_for(registry, candidate, {})
    with pytest.raises(ValueError, match="ungrouped"):
        compile_plan(registry.database, plan, values)
