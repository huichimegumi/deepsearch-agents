"""Tests for database tool result budgeting."""

from mysql.connector import Error

from app.tools.db_tools import _format_query_result, _format_sql_error, _preview_sql_query


def test_format_query_result_marks_row_truncation():
    result, metadata = _format_query_result(
        ["id", "name"],
        [(1, "one"), (2, "two")],
        row_limit=2,
        char_limit=1000,
        has_more_rows=True,
    )

    assert "结果已按工具预算截断" in result
    assert "id,name" in result
    assert metadata["returned_rows"] == 2
    assert metadata["truncated"] is True
    assert metadata["truncated_by_rows"] is True


def test_format_query_result_marks_char_truncation():
    result, metadata = _format_query_result(
        ["id", "description"],
        [(1, "x" * 200), (2, "y" * 200)],
        row_limit=10,
        char_limit=80,
        has_more_rows=False,
    )

    assert "结果已按工具预算截断" in result
    assert metadata["returned_rows"] == 1
    assert metadata["truncated"] is True
    assert metadata["truncated_by_chars"] is True


def test_preview_sql_query_wraps_select_with_limit():
    query, limited = _preview_sql_query(
        "SELECT id, name FROM drugs ORDER BY name;",
        row_limit=80,
    )

    assert limited is True
    assert query == (
        "SELECT * FROM (SELECT id, name FROM drugs ORDER BY name) "
        "AS _deepsearch_preview LIMIT 81"
    )


def test_preview_sql_query_leaves_non_select_query_unchanged():
    query, limited = _preview_sql_query("SHOW TABLES", row_limit=80)

    assert limited is False
    assert query == "SHOW TABLES"


def test_format_sql_error_adds_date_repair_guidance():
    error = Error(
        msg="Incorrect DATE value: '0000-00-00'",
        errno=1525,
        sqlstate="HY000",
    )

    result = _format_sql_error(error, "SELECT * FROM inventory WHERE expiry_date < '2027-06-30'")

    assert "错误码：1525" in result
    assert "SQLSTATE：HY000" in result
    assert "NULLIF(CAST(date_col AS CHAR), '0000-00-00')" in result
    assert "原始SQL：SELECT * FROM inventory" in result
