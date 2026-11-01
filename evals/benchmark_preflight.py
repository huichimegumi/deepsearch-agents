"""Verify the pinned public benchmark assets without exposing hidden answers."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from evals.dabstep.common import default_data_dir as dabstep_data_dir
from evals.dabstep.common import verify_files as verify_dabstep_files
from evals.dabstep.download_adyen_dev import DEFAULT_PATH as ADYEN_DEV_PATH
from evals.dabstep.download_adyen_dev import verify as verify_adyen_dev
from evals.dabstep.verify_reference import EXPECTED_PATH, collect
from evals.hybrid.common import default_data_dir as hybrid_data_dir
from evals.hybrid.common import load_selected_tasks
from evals.hybrid.common import verify_files as verify_hybrid_files
from evals.runners.experiment import file_sha256

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "evals" / "benchmark_v3.json"
DABSTEP_DATABASE = ROOT / "evals" / "dabstep" / "work" / "dabstep.sqlite"


def _selected_dabstep_ids() -> list[str]:
    selected = ROOT / "evals" / "dabstep" / "selected_tasks.jsonl"
    return [json.loads(line)["benchmark_id"] for line in selected.read_text().splitlines() if line]


def preflight() -> dict:
    """Return a content-free status; gold facts remain inside the scorer."""
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    sources = {entry["name"]: entry for entry in suite["source_sets"]}
    problems: list[str] = []
    hashes = {"suite": file_sha256(SUITE)}
    for name, entry in sources.items():
        for key in ("lock", "selection"):
            path = (ROOT / entry[key]).resolve()
            if not path.is_relative_to(ROOT / "evals") or not path.is_file():
                problems.append(f"invalid_{name}_{key}")
            else:
                hashes[f"{name}_{key}"] = file_sha256(path)
                if hashes[f"{name}_{key}"] != entry[f"{key}_sha256"]:
                    problems.append(f"{name}_{key}_hash_mismatch")

    problems += [f"dabstep_asset:{error}" for error in verify_dabstep_files(dabstep_data_dir())]
    problems += [f"adyen_dev:{error}" for error in verify_adyen_dev(ADYEN_DEV_PATH)]
    problems += [f"hybrid_asset:{error}" for error in verify_hybrid_files(hybrid_data_dir())]

    if _selected_dabstep_ids() != sources["dabstep_research"]["case_ids"]:
        problems.append("dabstep_selection_changed")
    if not any(problem.startswith("hybrid_asset:") for problem in problems):
        try:
            task_ids = [row["id"] for row in load_selected_tasks(hybrid_data_dir())]
            if task_ids != sources["hybrid_deep_research"]["case_ids"]:
                problems.append("hybrid_selection_changed")
        except (ValueError, KeyError, OSError, json.JSONDecodeError):
            problems.append("hybrid_selected_task_validation_failed")

    if not DABSTEP_DATABASE.is_file():
        problems.append("dabstep_sqlite_missing")
    elif not any(problem.startswith("dabstep_asset:") for problem in problems):
        try:
            actual = collect(f"sqlite:///{DABSTEP_DATABASE}")
            expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
            if actual != expected:
                problems.append("dabstep_sqlite_reference_mismatch")
        except (OSError, ValueError, sqlite3.Error):
            problems.append("dabstep_sqlite_reference_error")

    alien_db = hybrid_data_dir() / "alien" / "alien_template.sqlite"
    if alien_db.is_file():
        try:
            with sqlite3.connect(f"{alien_db.resolve().as_uri()}?mode=ro", uri=True) as conn:
                conn.execute("PRAGMA query_only = ON")
                if not conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone():
                    problems.append("hybrid_sqlite_empty_schema")
        except sqlite3.Error:
            problems.append("hybrid_sqlite_unreadable")

    return {
        "suite": suite["version"],
        "checked_at": datetime.now(UTC).isoformat(),
        "ready": not problems,
        "case_count": sum(len(entry["case_ids"]) for entry in sources.values()),
        "source_case_counts": {name: len(entry["case_ids"]) for name, entry in sources.items()},
        "input_sha256": hashes,
        "problems": problems,
        "privacy_note": "No decrypted task, answer, reference SQL, or raw benchmark text is emitted.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = preflight()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
