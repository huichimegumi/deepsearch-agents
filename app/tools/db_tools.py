"""MySQL query tools used by the database sub-agent."""

import csv
import io
import os
from time import monotonic

from dotenv import load_dotenv
from langchain_core.tools import tool
from mysql.connector import Error, connect

from app.api.monitor import monitor
from app.config import get_settings

load_dotenv()


LIST_TABLES_TOOL = "数据库表名查询工具：list_sql_tables"
TABLE_PREVIEW_TOOL = "数据库表数据查询工具：get_table_data"
SQL_QUERY_TOOL = "数据库表数据查询工具：execute_sql_query"


def get_db_config():
    """Read MySQL connection settings from environment variables."""
    timeout_seconds = get_settings().db_timeout_seconds
    config = {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER"),
        "password": os.getenv("MYSQL_PASSWORD"),
        "database": os.getenv("MYSQL_DATABASE"),
        "charset": os.getenv("MYSQL_CHARSET", "utf8mb4"),
        "collation": os.getenv("MYSQL_COLLATION", "utf8mb4_unicode_ci"),
        "autocommit": True,
        "sql_mode": os.getenv("MYSQL_SQL_MODE", "TRADITIONAL"),
        "connection_timeout": timeout_seconds,
        "read_timeout": timeout_seconds,
        "write_timeout": timeout_seconds,
    }
    config = {key: value for key, value in config.items() if value is not None}

    required_keys = ["user", "password", "database"]
    missing_keys = [key for key in required_keys if key not in config]
    if missing_keys:
        raise ValueError(f"缺少数据库核心配置：{', '.join(missing_keys)}")

    return config


def _apply_query_timeout(cursor) -> None:
    timeout_ms = max(1, int(get_settings().db_timeout_seconds * 1000))
    try:
        cursor.execute(f"SET SESSION MAX_EXECUTION_TIME={timeout_ms}")
    except Error:
        # Some MySQL-compatible engines do not support this session variable.
        pass


def _rows_to_csv(columns: list[str], rows: list[tuple]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    writer.writerows(rows)
    return buffer.getvalue().strip()


def _format_query_result(
    columns: list[str],
    rows: list[tuple],
    *,
    row_limit: int,
    char_limit: int,
    has_more_rows: bool,
) -> tuple[str, dict]:
    """Format a bounded CSV preview plus structured budget metadata."""
    output_rows: list[tuple] = []
    truncated_by_chars = False

    for row in rows[:row_limit]:
        candidate = _rows_to_csv(columns, [*output_rows, row])
        if len(candidate) > char_limit and output_rows:
            truncated_by_chars = True
            break
        if len(candidate) > char_limit:
            output_rows.append(row)
            truncated_by_chars = True
            break
        output_rows.append(row)

    csv_text = _rows_to_csv(columns, output_rows)
    truncated = has_more_rows or truncated_by_chars or len(rows) > len(output_rows)
    metadata = {
        "column_count": len(columns),
        "fetched_rows": len(rows),
        "returned_rows": len(output_rows),
        "returned_chars": len(csv_text),
        "row_limit": row_limit,
        "char_limit": char_limit,
        "truncated": truncated,
        "truncated_by_rows": has_more_rows or len(rows) > row_limit,
        "truncated_by_chars": truncated_by_chars or len(rows) > len(output_rows),
    }
    if not truncated:
        return csv_text, metadata

    notice = (
        "结果已按工具预算截断，下面只返回可供模型分析的预览数据；"
        f"返回 {len(output_rows)} 行，最多 {row_limit} 行，最多 {char_limit} 字符。"
        "如需完整明细，请缩小筛选条件，或改用专门的导出流程。"
    )
    return f"{notice}\n\n{csv_text}", metadata


def _preview_sql_query(query: str, row_limit: int) -> tuple[str, bool]:
    """Constrain read-only SELECT/CTE queries at the SQL layer."""
    cleaned = query.strip().rstrip(";").strip()
    first_token = cleaned.split(maxsplit=1)[0].lower() if cleaned else ""
    if first_token not in {"select", "with"}:
        return query, False
    return f"SELECT * FROM ({cleaned}) AS _deepsearch_preview LIMIT {row_limit + 1}", True


def _sql_error_guidance(exc: Error) -> list[str]:
    """Return repair hints that help the agent recover from common MySQL errors."""
    message = str(exc)
    errno = getattr(exc, "errno", None)
    guidance: list[str] = []

    if errno == 1525 or "Incorrect DATE value" in message or "0000-00-00" in message:
        guidance.append(
            "日期字段可能包含 '0000-00-00' 等无效值；比较日期前请使用 "
            "NULLIF(CAST(date_col AS CHAR), '0000-00-00')，必要时再包一层 "
            "STR_TO_DATE(NULLIF(CAST(date_col AS CHAR), '0000-00-00'), '%Y-%m-%d')。"
            "不要直接写 date_col != '0000-00-00'，严格 SQL 模式下这个比较本身也会报错。"
        )
    if errno == 1054 or "Unknown column" in message:
        guidance.append("字段名不存在；请先调用 get_table_data 预览真实列名，再重写 SQL。")
    if errno == 1146 or "doesn't exist" in message:
        guidance.append("表名不存在；请先调用 list_sql_tables 确认可用表名。")
    if errno == 1064 or "syntax" in message.lower():
        guidance.append("SQL 语法不符合 MySQL 方言；请检查函数、别名、引号和子查询写法。")
    if errno in {1052, 1060} or "ambiguous" in message.lower():
        guidance.append("多表查询中的字段或别名可能冲突；请为字段加表别名，并为输出列使用唯一别名。")

    if not guidance:
        guidance.append("请基于错误信息缩小 SQL 范围，优先用简单 SELECT 验证表名、字段名和样例值。")
    return guidance


def _format_sql_error(exc: Error, query: str) -> str:
    """Format SQL failures as actionable text for the database agent."""
    errno = getattr(exc, "errno", None)
    sqlstate = getattr(exc, "sqlstate", None)
    parts = [
        "SQL执行失败。",
        f"错误码：{errno if errno is not None else '未知'}",
        f"SQLSTATE：{sqlstate if sqlstate else '未知'}",
        f"错误信息：{exc}",
        "修复建议：",
    ]
    parts.extend(f"- {item}" for item in _sql_error_guidance(exc))
    parts.extend(
        [
            "重试限制：如果修正后仍失败，请停止继续尝试，返回已获得的数据、失败原因和建议人工复核的 SQL。",
            f"原始SQL：{query}",
        ]
    )
    return "\n".join(parts)


@tool
def list_sql_tables() -> str:
    """List available tables in the configured MySQL database."""
    started_at = monotonic()
    monitor.report_tool(tool_name=LIST_TABLES_TOOL, args={})

    try:
        with connect(**get_db_config()) as conn:
            with conn.cursor() as cursor:
                _apply_query_timeout(cursor)
                cursor.execute("SHOW TABLES")
                tables = cursor.fetchall()
                if not tables:
                    result = "没有可用的表"
                    monitor.report_tool_end(
                        LIST_TABLES_TOOL,
                        {
                            "elapsed_ms": round((monotonic() - started_at) * 1000),
                            "table_count": 0,
                            "returned_chars": len(result),
                        },
                    )
                    return result

                table_names = [table[0] for table in tables]
                result = f"可用的表有：{', '.join(table_names)}"
                monitor.report_tool_end(
                    LIST_TABLES_TOOL,
                    {
                        "elapsed_ms": round((monotonic() - started_at) * 1000),
                        "table_count": len(table_names),
                        "returned_chars": len(result),
                    },
                )
                return result
    except Error as exc:
        monitor.report_tool_error(
            LIST_TABLES_TOOL,
            str(exc),
            {"elapsed_ms": round((monotonic() - started_at) * 1000)},
        )
        return f"查询出现异常：{exc}"


@tool
def get_table_data(table_name) -> str:
    """Return a bounded CSV preview for a table."""
    started_at = monotonic()
    settings = get_settings()
    row_limit = settings.db_table_preview_rows
    char_limit = settings.db_max_result_chars
    monitor.report_tool(
        tool_name=TABLE_PREVIEW_TOOL,
        args={"table_name": table_name},
    )

    try:
        with connect(**get_db_config()) as conn:
            with conn.cursor() as cursor:
                _apply_query_timeout(cursor)
                cursor.execute(f"SELECT * FROM {table_name} LIMIT {row_limit + 1}")

                description = cursor.description
                if not description:
                    result = f"数据表 {table_name} 暂无数据。"
                    monitor.report_tool_end(
                        TABLE_PREVIEW_TOOL,
                        {
                            "elapsed_ms": round((monotonic() - started_at) * 1000),
                            "table_name": table_name,
                            "returned_chars": len(result),
                        },
                    )
                    return result

                columns = [desc[0] for desc in description]
                rows = cursor.fetchmany(row_limit + 1)
                result, metadata = _format_query_result(
                    columns,
                    rows[:row_limit],
                    row_limit=row_limit,
                    char_limit=char_limit,
                    has_more_rows=len(rows) > row_limit,
                )
                monitor.report_tool_end(
                    TABLE_PREVIEW_TOOL,
                    {
                        **metadata,
                        "elapsed_ms": round((monotonic() - started_at) * 1000),
                        "table_name": table_name,
                    },
                )
                return result
    except Error as exc:
        monitor.report_tool_error(
            TABLE_PREVIEW_TOOL,
            str(exc),
            {
                "elapsed_ms": round((monotonic() - started_at) * 1000),
                "table_name": table_name,
            },
        )
        return f"查询出现异常：{exc}"


@tool
def execute_sql_query(query) -> str:
    """Execute a custom SQL query and return a bounded CSV preview."""
    started_at = monotonic()
    settings = get_settings()
    row_limit = settings.db_query_preview_rows
    char_limit = settings.db_max_result_chars
    monitor.report_tool(tool_name=SQL_QUERY_TOOL, args={"query": query})

    try:
        with connect(**get_db_config()) as conn:
            with conn.cursor() as cursor:
                _apply_query_timeout(cursor)
                preview_query, is_preview_limited = _preview_sql_query(query, row_limit)
                cursor.execute(preview_query)

                description = cursor.description
                if not description:
                    result = f"执行自定义 SQL 语句没有查询结果，SQL 为：{query}"
                    monitor.report_tool_end(
                        SQL_QUERY_TOOL,
                        {
                            "elapsed_ms": round((monotonic() - started_at) * 1000),
                            "query": query,
                            "returned_chars": len(result),
                        },
                    )
                    return result

                columns = [desc[0] for desc in description]
                rows = cursor.fetchmany(row_limit + 1)
                if not is_preview_limited:
                    cursor.fetchall()
                result, metadata = _format_query_result(
                    columns,
                    rows[:row_limit],
                    row_limit=row_limit,
                    char_limit=char_limit,
                    has_more_rows=len(rows) > row_limit,
                )
                monitor.report_tool_end(
                    SQL_QUERY_TOOL,
                    {
                        **metadata,
                        "elapsed_ms": round((monotonic() - started_at) * 1000),
                        "query": query,
                        "preview_limited": is_preview_limited,
                    },
                )
                return result
    except Error as exc:
        monitor.report_tool_error(
            SQL_QUERY_TOOL,
            str(exc),
            {
                "elapsed_ms": round((monotonic() - started_at) * 1000),
                "query": query,
            },
        )
        return _format_sql_error(exc, query)


if __name__ == "__main__":
    print(
        execute_sql_query.invoke(
            {
                "query": "SELECT * FROM `drugs` dgs join sales_records srd on dgs.drug_id = srd.drug_id"
            }
        )
    )
