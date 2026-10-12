from app.research.sql_semantics import compile_semantic_sql_expressions


def test_compiler_expands_formula_dependencies_to_physical_columns():
    compiled = compile_semantic_sql_expressions(
        (
            {
                "knowledge": "Observation Quality Factor (OQF)",
                "definition": (
                    "$\\text{OQF} = \\text{AOI} \\times (1 - \\text{LIF}) "
                    "\\times (\\text{PointAccArc} < 2 ? 1 : "
                    "\\frac{2}{\\text{PointAccArc}})$"
                ),
                "resolved_columns": [
                    {
                        "formula_identifier": "PointAccArc",
                        "table_name": "telescopes",
                        "column_name": "pointaccarc",
                    }
                ],
            },
            {
                "knowledge": "Atmospheric Observability Index (AOI)",
                "definition": (
                    "$\\text{AOI} = \\text{AtmosTransparency} \\times "
                    "(1 - \\frac{\\text{HumidityRate}}{100})$"
                ),
                "resolved_columns": [
                    {
                        "formula_identifier": "AtmosTransparency",
                        "table_name": "observatories",
                        "column_name": "atmostransparency",
                    },
                    {
                        "formula_identifier": "HumidityRate",
                        "table_name": "observatories",
                        "column_name": "humidityrate",
                    },
                ],
            },
            {
                "knowledge": "Lunar Interference Factor (LIF)",
                "definition": (
                    "$\\text{LIF} = (1 - \\frac{\\text{LunarDistDeg}}{180}) "
                    "\\times (1 - \\text{AtmosTransparency})$"
                ),
                "resolved_columns": [
                    {
                        "formula_identifier": "LunarDistDeg",
                        "table_name": "observatories",
                        "column_name": "lunardistdeg",
                    },
                    {
                        "formula_identifier": "AtmosTransparency",
                        "table_name": "observatories",
                        "column_name": "atmostransparency",
                    },
                ],
            },
        )
    )

    oqf = compiled[0]
    expression = oqf["compiled_sql_expression"]
    assert '"telescopes"."pointaccarc"' in expression
    assert '"observatories"."atmostransparency"' in expression
    assert '"observatories"."humidityrate"' in expression
    assert '"observatories"."lunardistdeg"' in expression
    assert "CASE WHEN" in expression
    assert "OQF" not in expression
    assert "AOI" not in expression
    assert "LIF" not in expression
    assert oqf["required_tables"] == ["observatories", "telescopes"]


def test_compiler_leaves_unsupported_or_unresolved_formula_non_executable():
    compiled = compile_semantic_sql_expressions(
        (
            {
                "knowledge": "Unsupported Score",
                "definition": "$\\text{Score} = \\sqrt{\\text{MissingValue}}$",
            },
        )
    )

    assert "compiled_sql_expression" not in compiled[0]
    assert "required_tables" not in compiled[0]
