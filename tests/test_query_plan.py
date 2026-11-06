import sqlite3

import pytest

from app.research.query_plan import BoundValue, QueryPlan, compile_plan, execute_plan
from app.research.semantic_context import definition_context


def database(tmp_path):
    db = tmp_path / "plan.sqlite"
    with sqlite3.connect(db) as conn:
        conn.executescript("""
            CREATE TABLE clients(id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE charges(client_id INTEGER, period TEXT, amount REAL, adjustment REAL);
            INSERT INTO clients VALUES (1, 'Alpha'), (2, 'Beta');
            INSERT INTO charges VALUES
                (1, '2026-01', 10, 2), (1, '2026-01', 20, 1),
                (1, '2026-02', 50, 3), (2, '2026-01', 1000, 0);
        """)
    return db


def plan():
    return QueryPlan.model_validate(
        {
            "table": "charges",
            "grain": "groups",
            "joins": [
                {
                    "table": "clients",
                    "source_column": "charges.client_id",
                    "target_column": "clients.id",
                }
            ],
            "expressions": [
                {"key": "name", "op": "column", "ref": "clients.name"},
                {"key": "period", "op": "column", "ref": "charges.period"},
                {"key": "amount", "op": "column", "ref": "charges.amount"},
                {"key": "adjustment", "op": "column", "ref": "charges.adjustment"},
                {"key": "net", "op": "subtract", "args": ["amount", "adjustment"]},
                {"key": "total", "op": "sum", "args": ["net"]},
                {"key": "entity", "op": "parameter", "ref": "entity"},
                {"key": "selected", "op": "eq", "args": ["name", "entity"]},
            ],
            "filters": ["selected"],
            "group_by": ["name", "period"],
            "outputs": [
                {"expression": "name", "alias": "entity"},
                {"expression": "period", "alias": "period"},
                {"expression": "total", "alias": "total"},
            ],
            "order_by": [{"expression": "period"}],
        }
    )


def test_compiled_metric_preserves_entity_period_grain_and_actual_values(tmp_path):
    db = database(tmp_path)
    values = {"entity": BoundValue(value="Alpha", source_ref="observed-client")}
    records, _, parameters, _ = execute_plan(db, plan(), values)
    assert [r["content"] for r in records] == [
        {"entity": "Alpha", "period": "2026-01", "total": 27},
        {"entity": "Alpha", "period": "2026-02", "total": 47},
    ]
    assert parameters == {"entity": "Alpha"}
    # Parameter text is never part of SQL syntax.
    query, params = compile_plan(
        db, plan(), {"entity": BoundValue(value="x' OR 1=1 --", source_ref="input")}
    )
    assert "OR 1=1" not in query
    with sqlite3.connect(db) as conn:
        assert conn.execute(query, params).fetchall() == []


@pytest.mark.parametrize(
    "mutation,reason",
    [
        (lambda p: p.group_by.remove("period"), "ungrouped"),
        (lambda p: setattr(p, "grain", "rows"), "grain_mismatch"),
        (lambda p: setattr(p.joins[0], "target_column", "clients.name"), "not_unique"),
        (lambda p: setattr(p.expressions[2], "ref", "charges.invented"), "unknown_plan_column"),
        (lambda p: p.filters.append("total"), "invalid_where"),
        (lambda p: setattr(p.expressions[4], "args", ["total", "amount"]), "forward_expression"),
        (lambda p: setattr(p.outputs[1], "alias", "ENTITY"), "duplicate_projection"),
    ],
)
def test_invalid_semantics_are_rejected_before_execution(tmp_path, mutation, reason):
    candidate = plan()
    mutation(candidate)
    with pytest.raises(ValueError, match=reason):
        compile_plan(
            database(tmp_path), candidate, {"entity": BoundValue(value="Alpha", source_ref="input")}
        )


def test_patterns_require_explicit_like_and_do_not_trigger_automatic_filter_changes(tmp_path):
    candidate = plan()
    db = database(tmp_path)
    values = {"entity": BoundValue(value="%Al%", mode="pattern", source_ref="observed-pattern")}
    with pytest.raises(ValueError, match="pattern_requires_like"):
        compile_plan(db, candidate, values)
    candidate.expressions[-1].op = "like"
    records, _, _, _ = execute_plan(db, candidate, values)
    assert len(records) == 2


def test_division_is_real_and_zero_is_unknown_not_a_fabricated_number(tmp_path):
    candidate = QueryPlan.model_validate(
        {
            "table": "clients",
            "grain": "rows",
            "expressions": [
                {"key": "one", "op": "number", "number": 1},
                {"key": "two", "op": "number", "number": 2},
                {"key": "zero", "op": "number", "number": 0},
                {"key": "half", "op": "divide", "args": ["one", "two"]},
                {"key": "unknown", "op": "divide", "args": ["one", "zero"]},
            ],
            "outputs": [
                {"expression": "half", "alias": "ratio"},
                {"expression": "unknown", "alias": "unknown"},
            ],
        }
    )
    rows, _, _, _ = execute_plan(database(tmp_path), candidate, {})
    assert rows[0]["content"] == {"ratio": 0.5, "unknown": None}


def test_semantic_context_adds_transitive_dependencies_without_dangling_roots():
    ranked = [
        {"id": 3, "children_knowledge": [2], "definition": "outer"},
        {"id": 2, "children_knowledge": [1], "definition": "inner"},
        {"id": 1, "children_knowledge": -1, "definition": "leaf"},
    ]
    selected, errors = definition_context(ranked, max_roots=1)
    assert [r["id"] for r in selected] == [1, 2, 3]
    assert not errors
    assert definition_context(ranked, max_tokens=1)[0] == []
    assert definition_context([{"id": 1, "children_knowledge": [2]}])[1][0]["reason"].endswith(
        "missing"
    )
    assert definition_context([{"id": 1, "children_knowledge": [1]}])[1][0]["reason"].endswith(
        "cycle"
    )
