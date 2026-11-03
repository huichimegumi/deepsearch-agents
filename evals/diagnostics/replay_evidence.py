"""No-model handoff replay from full tool artifacts; not a research quality score."""

import hashlib

from app.research.evidence_store import EvidenceStore, count_tokens
from evals.diagnostics.e8 import INPUTS, ROOT, read
from evals.worker_supervisor import atomic_json


def run():
    baseline = ROOT / "evals/results/e8-0-baseline"
    cases = read(INPUTS / "public.json")
    rows = []
    for case in cases:
        key = hashlib.sha256(case["id"].encode()).hexdigest()[:16]
        attempt = baseline / key / "attempt-0001"
        result = read(attempt / "research_result.json")
        store = EvidenceStore(ROOT / "evals/results/e8-1-replay" / key)
        for path in sorted((attempt / "trace").glob("tool-*.json")):
            tool = read(path)
            store.add(tool["records"], tool["operation"]["id"])
        context = store.select(case["question"])
        rows.append(
            {
                "id": case["id"],
                "original_delivered_records": len(result["evidence"]),
                "complete_unique_records": len(store.records),
                "selected_records": len(context["evidence"]),
                "view_tokens": count_tokens(context),
                "view_limit": 12000,
                "all_raw_records_persisted": len(read(store.directory / "index.json")["records"])
                == len(store.records),
            }
        )
    summary = {
        "scope": "Replay of actual development tool responses; no model/API calls, no oracle-driven selection; count is not semantic recall",
        "cases": rows,
    }
    atomic_json(ROOT / "evals/reports/e8-1-handoff-replay.json", summary)
    print(summary)


if __name__ == "__main__":
    run()
