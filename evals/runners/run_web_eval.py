"""Run web-search QA evals against the configured SearchService."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.search.models import SearchRequest
from app.search.service import get_search_service
from evals.runners.common import DATASET_DIR, RESULTS_DIR, load_jsonl, now_utc, status_counts, write_json


DEFAULT_DATASET = DATASET_DIR / "web_research_zh.jsonl"


def _run_search(task: str, max_results: int) -> dict[str, Any]:
    response = get_search_service().search(
        SearchRequest(
            queries=[task],
            backend="auto",
            max_results=max_results,
            fetch_full_page=False,
        )
    )
    payload = response.to_dict()
    results = payload.get("results", [])
    return {
        "backend": payload.get("backend"),
        "result_count": len(results),
        "answer_present": bool(payload.get("answer")),
        "notices": payload.get("notices", []),
        "top_results": [
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "published_date": item.get("published_date"),
                "source_backend": item.get("source_backend"),
            }
            for item in results[:5]
        ],
    }


def run(dataset: Path = DEFAULT_DATASET, max_results: int = 5) -> dict[str, Any]:
    samples = load_jsonl(dataset)
    results: list[dict[str, Any]] = []

    for sample in samples:
        try:
            search = _run_search(sample["task"], max_results=max_results)
            status = "passed" if search["result_count"] > 0 else "failed"
            results.append(
                {
                    "id": sample["id"],
                    "status": status,
                    "route": sample["expected_route"],
                    **search,
                }
            )
        except Exception as exc:  # noqa: BLE001 - external provider failures are eval data
            results.append({"id": sample["id"], "status": "blocked", "reason": repr(exc)})

    counts = status_counts(results)
    return {
        "name": "web_research_zh",
        "dataset": str(dataset),
        "generated_at": now_utc(),
        "total": len(samples),
        "status_counts": counts,
        "pass_rate": counts.get("passed", 0) / len(samples) if samples else 0.0,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run web-search QA evals.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=RESULTS_DIR / "web_research_eval.json")
    parser.add_argument("--max-results", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run(args.dataset, max_results=args.max_results)
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
