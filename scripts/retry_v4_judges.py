"""Retry only failed judge replies once, preserving original research and scores."""

import argparse
import asyncio
import json
from pathlib import Path

from evals.scoring_v4 import digest, score
from evals.worker_supervisor import atomic_json


async def retry(run: Path, cases_file: Path) -> dict:
    original = json.loads((run / "score-v4/scores.json").read_text())
    manifest = json.loads((run / "score-v4/manifest.json").read_text())
    cases = json.loads(cases_file.read_text())
    results = json.loads((run / "results.json").read_text())
    if digest(cases) != manifest["cases_sha256"] or digest(results) != manifest["results_sha256"]:
        raise ValueError("judge_retry_input_mismatch")
    ids = {
        row["id"] for row in original["rows"] if row["judge_errors"] and not row["judge_responses"]
    }
    subset = [row for row in cases if row["id"] in ids]
    candidates = [row for row in results if row["id"] in ids]
    output = run / "score-v4-error-retry"
    await score(
        subset,
        candidates,
        output,
        max_requests=max(1, len(ids)),
        max_reserved_tokens=max(50000, len(ids) * 50000),
    )
    retried = json.loads((output / "scores.json").read_text())
    payload = {
        "original_scores_sha256": digest(original),
        "original_manifest_sha256": digest(manifest),
        "retry_manifest": json.loads((output / "manifest.json").read_text()),
        "retry_scores": retried["rows"],
    }
    atomic_json(run / "score-v4/error_retries.json", payload)
    return {
        "retried": len(ids),
        "recovered": sum(not row["judge_errors"] for row in retried["rows"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    args = parser.parse_args()
    print(asyncio.run(retry(args.run, args.cases)))


if __name__ == "__main__":
    main()
