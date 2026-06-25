"""Run DB query evals using gold SQL against the configured MySQL database."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from mysql.connector import Error, connect

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.tools.db_tools import get_db_config
from evals.runners.common import DATASET_DIR, RESULTS_DIR, load_jsonl, now_utc, status_counts, write_json


DEFAULT_DATASET = DATASET_DIR / "db_query_zh.jsonl"


def _db_available() -> tuple[bool, str]:
    try:
        config = get_db_config()
        with connect(**config) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        return True, ""
    except Exception as exc:  # noqa: BLE001 - record dependency failures in eval output
        return False, repr(exc)


def _execute(query: str) -> tuple[list[str], list[tuple[Any, ...]]]:
    config = get_db_config()
    with connect(**config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            columns = [item[0] for item in cursor.description or []]
            rows = cursor.fetchall()
    return columns, rows


def _json_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "__float__") and value.__class__.__name__ == "Decimal":
        return float(value)
    return value


def _json_row(row: tuple[Any, ...]) -> list[Any]:
    return [_json_value(value) for value in row]


def run(dataset: Path = DEFAULT_DATASET) -> dict[str, Any]:
    samples = load_jsonl(dataset)
    available, reason = _db_available()
    results: list[dict[str, Any]] = []

    for sample in samples:
        if not available:
            results.append(
                {
                    "id": sample["id"],
                    "status": "blocked",
                    "reason": f"MySQL unavailable: {reason}",
                    "route": sample["expected_route"],
                }
            )
            continue
        try:
            columns, rows = _execute(sample["gold_sql"])
            results.append(
                {
                    "id": sample["id"],
                    "status": "passed" if columns else "failed",
                    "columns": columns,
                    "row_count": len(rows),
                    "preview_rows": [_json_row(row) for row in rows[:5]],
                }
            )
        except Error as exc:
            results.append({"id": sample["id"], "status": "failed", "reason": str(exc)})

    counts = status_counts(results)
    return {
        "name": "db_query_zh",
        "dataset": str(dataset),
        "generated_at": now_utc(),
        "total": len(samples),
        "status_counts": counts,
        "pass_rate": counts.get("passed", 0) / len(samples) if samples else 0.0,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run DB query evals.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=RESULTS_DIR / "db_query_eval.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run(args.dataset)
    write_json(args.output, report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Dataset: {report['dataset']}")
        print(f"Total: {report['total']}")
        print(f"Status counts: {report['status_counts']}")
        print(f"Pass rate: {report['pass_rate']:.1%}")
        print(f"Wrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
