"""Authored development fixtures: delivery diagnostics, not an independent benchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from app.research.bounded import execute
from app.research.sources import SourceCatalog
from evals.worker_supervisor import atomic_json

CASES = [
    (
        "positive",
        "What is the lab's documented support email?",
        "answered",
        "The lab support email is support@example.org.",
    ),
    (
        "missing",
        "What is the lab's production CPU limit?",
        "insufficient_evidence",
        "The lab support email is support@example.org.",
    ),
    ("empty", "What is the documented production CPU limit?", "insufficient_evidence", ""),
    (
        "partial",
        "State the lab support email and its production CPU limit.",
        "partial",
        "The lab support email is support@example.org.",
    ),
    (
        "scope",
        "Does the provided lab policy establish that no production CPU limit exists anywhere?",
        "insufficient_evidence",
        "This policy documents the support email only.",
    ),
    (
        "conflict",
        "Give the current CPU limit, resolving the two undated documents if possible.",
        "partial",
        "Undated policy A: the CPU limit is 2. Undated policy B: the CPU limit is 4. Neither has a precedence rule.",
    ),
]


async def run(output):
    os.environ["LLM_PROVIDER"] = "deepseek"
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    from app.agent.llm import get_model
    from app.config import get_settings

    get_settings.cache_clear()
    get_model.cache_clear()
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for case_id, question, expected, text in CASES:
        target = output / case_id / "research_result.json"
        catalog = SourceCatalog(
            documents=[{"title": "Lab policy", "locator": "fixture:lab", "text": text}]
            if text
            else [],
            allowed_sources=("local_document",),
        )
        result = (
            json.loads(target.read_text())
            if target.exists()
            else await execute(question, catalog, target.parent)
        )
        rows.append(
            {
                "id": case_id,
                "status": result["status"],
                "expected_answerability": expected,
                "actual_answerability": result["report"]["answerability"],
                "protocol_ok": result["status"] == "completed"
                and result["report"]["answerability"] == expected,
                "model_reservations": result["model_reservations"],
            }
        )
    atomic_json(
        output / "summary.json",
        {
            "scope": "Authored development delivery checks; no semantic judge",
            "cases": rows,
            "protocol_ok": sum(row["protocol_ok"] for row in rows),
            "scheduled": len(rows),
        },
    )
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(run(parser.parse_args().output))
