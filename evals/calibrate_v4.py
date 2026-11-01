"""Twenty-four source-controlled correct and corrupted candidates for scorer calibration."""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sqlite3
from pathlib import Path

from app.research.evidence.models import EvidenceRecord, EvidenceSource
from evals.scoring_v4 import score
from evals.worker_supervisor import atomic_json


def fixtures() -> tuple[list[dict], list[dict]]:
    cases, results = [], []
    # Source evidence counts come from literal event records; a separate SQL reduction
    # produces reference values. Neither the oracle nor its checks reach the executor.
    with sqlite3.connect(":memory:") as conn:
        conn.execute("CREATE TABLE events (site TEXT, visitor TEXT)")
        for index, city in enumerate(("Oslo", "Lima", "Accra", "Kyoto")):
            site = f"site_{index}"
            events = [(site, str(n)) for n in range(11 + index * 3)]
            conn.executemany("INSERT INTO events VALUES (?, ?)", events)
            expected = conn.execute("SELECT COUNT(*) FROM events WHERE site=?", (site,)).fetchone()[
                0
            ]
            evidence = EvidenceRecord.create(
                source=EvidenceSource.SQL,
                locator=f"sql://calibration/{site}",
                content={"site": site, "city": city, "visits": len(events)},
            ).to_dict()
            for variant in (
                "correct",
                "wrong_number",
                "wrong_citation",
                "uncited",
                "contradiction",
                "truncated",
            ):
                case_id = f"calibration_{index}_{variant}"
                report = {
                    "title": "Site observations",
                    "answerability": "answered",
                    "limitations": [],
                    "claims": [
                        {"text": f"{site} is in {city}.", "evidence_ids": [evidence["evidence_id"]]}
                    ],
                    "facts": [
                        {
                            "metric": "visits",
                            "value": str(len(events)),
                            "evidence_id": evidence["evidence_id"],
                            "path": ["visits"],
                        }
                    ],
                }
                candidate = {
                    "id": case_id,
                    "status": "completed",
                    "report": report,
                    "evidence": [copy.deepcopy(evidence)],
                    "response_metadata": {"finish_reason": "stop"},
                }
                if variant == "wrong_number":
                    report["facts"][0]["value"] = str(expected + 1)
                elif variant == "wrong_citation":
                    report["claims"][0]["evidence_ids"] = ["ev1_sql_fabricated"]
                    report["facts"][0]["evidence_id"] = "ev1_sql_fabricated"
                elif variant == "uncited":
                    report["claims"][0]["evidence_ids"] = []
                elif variant == "contradiction":
                    report["claims"][0]["text"] = f"{site} is in Paris."
                elif variant == "truncated":
                    candidate["response_metadata"]["finish_reason"] = "length"
                cases.append(
                    {
                        "id": case_id,
                        "question": f"Report visits and city for {site}.",
                        "required_sources": ["sql"],
                        "oracle": {
                            "answerable": True,
                            "checklist": ["Give the correct visit count", "Give the correct city"],
                            "facts": [{"metric": "visits", "value": str(expected)}],
                        },
                    }
                )
                results.append(candidate)
    return cases, results


async def run(output: Path) -> dict:
    cases, results = fixtures()
    summary = await score(cases, results, output, max_requests=30, max_reserved_tokens=150000)
    rows = json.loads((output / "scores.json").read_text())["rows"]
    accepted = [row["id"] for row in rows if row["pass"]]
    expected = [row["id"] for row in cases if row["id"].endswith("_correct")]
    calibration = {
        "summary": summary,
        "expected_accepted": expected,
        "accepted": accepted,
        "false_accepts": sorted(set(accepted) - set(expected)),
        "false_rejects": sorted(set(expected) - set(accepted)),
    }
    atomic_json(output / "calibration.json", calibration)
    return calibration


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.output)), indent=2))


if __name__ == "__main__":
    main()
