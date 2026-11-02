"""Small free-backend live retrieval probe, separate from snapshot quality grades."""

import argparse
import json
import os
from pathlib import Path
from time import monotonic


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.environ["SEARCH_BACKEND_LOCK"] = "duckduckgo"
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    from app.research.sources import SourceCatalog
    from app.research.storage import write_json

    catalog = SourceCatalog(allowed_sources=("web",))
    rows = []
    for query in (
        "RFC 9309 robots allow disallow",
        "RFC 8259 JSON parsers limits",
        "RFC 6455 normal closure 1000",
        "RFC 3986 reserved characters",
    ):
        started = monotonic()
        try:
            records, warnings = catalog.collect("web", query)
            row = {
                "query": query,
                "fetched_evidence": len(records),
                "locators": [record["locator"] for record in records],
                "warnings": warnings,
            }
        except Exception as exc:
            row = {"query": query, "fetched_evidence": 0, "error": f"{type(exc).__name__}:{exc}"}
        row["seconds"] = round(monotonic() - started, 2)
        rows.append(row)
        write_json(
            args.output,
            {
                "backend": "duckduckgo",
                "paid_search": False,
                "model_calls": 0,
                "queries": rows,
                "successful_queries": sum(row["fetched_evidence"] > 0 for row in rows),
                "scope": "Live retrieval availability only; not an answer-quality score.",
            },
        )
    print(
        json.dumps(
            {"queries": len(rows), "successful": sum(row["fetched_evidence"] > 0 for row in rows)}
        )
    )


if __name__ == "__main__":
    main()
