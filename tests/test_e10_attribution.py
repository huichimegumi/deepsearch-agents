from evals.diagnostics.attribute_e10 import clause_signals, missing_dependencies


def test_clause_signals_ignore_literals_and_comments_and_export_no_values():
    signals = clause_signals(
        "SELECT AVG(amount * .5), 'JOIN SUM(x)' FROM private_table "
        "WHERE name=:v1 AND other != :v2 /* JOIN secret */ -- SUM(x)\n",
        {"v1": "%private%", "v2": "%other%"},
    )
    assert signals["aggregate_calls"] == 1
    assert signals["joins"] == 0
    assert signals["wildcard_values_used_in_equality"] == 1
    assert all(isinstance(value, int) for value in signals.values())


def test_definition_dependencies_handle_leaf_sentinel_and_shared_children():
    assert (
        missing_dependencies(
            [
                {"id": 1, "children_knowledge": [2, 3]},
                {"id": 2, "children_knowledge": -1},
                {"id": 4, "children_knowledge": [3]},
            ]
        )
        == 1
    )
