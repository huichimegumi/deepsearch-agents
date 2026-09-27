from __future__ import annotations

import argparse
import datetime as dt
import decimal
import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from evals.dabstep.common import HERE, LOCK_PATH, load_json
from evals.dabstep.reference_queries import REFERENCE_QUERIES

EXPECTED_PATH = HERE / "reference_results.json"


def _json_value(value: Any) -> Any:
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


def collect(database_url: str) -> dict[str, Any]:
    engine = create_engine(database_url)
    results: dict[str, Any] = {}
    try:
        with engine.connect() as connection:
            for name, sql in REFERENCE_QUERIES.items():
                query_result = connection.execute(text(sql))
                results[name] = [
                    {key: _json_value(value) for key, value in row._mapping.items()}
                    for row in query_result
                ]
    finally:
        engine.dispose()
    return {
        "dataset_revision": load_json(LOCK_PATH)["revision"],
        "scope": "Deterministic source facts only; exact fee totals are intentionally excluded.",
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify DABStep SQL data against pinned facts.")
    parser.add_argument(
        "--database-url",
        default=os.getenv("DABSTEP_DATABASE_URL", "sqlite:///evals/dabstep/work/dabstep.sqlite"),
    )
    parser.add_argument("--expected", type=Path, default=EXPECTED_PATH)
    parser.add_argument(
        "--update",
        action="store_true",
        help="Regenerate the committed reference snapshot after deliberate source/query review.",
    )
    args = parser.parse_args()

    actual = collect(args.database_url)
    if args.update:
        args.expected.write_text(
            json.dumps(actual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"updated {args.expected}")
        return 0

    expected = load_json(args.expected)
    if actual != expected:
        print("reference verification failed")
        expected_text = json.dumps(expected, ensure_ascii=False, indent=2, sort_keys=True)
        actual_text = json.dumps(actual, ensure_ascii=False, indent=2, sort_keys=True)
        import difflib

        print(
            "".join(
                difflib.unified_diff(
                    expected_text.splitlines(keepends=True),
                    actual_text.splitlines(keepends=True),
                    fromfile="expected",
                    tofile="actual",
                )
            )
        )
        return 1
    print(f"verified {len(REFERENCE_QUERIES)} reference query groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
