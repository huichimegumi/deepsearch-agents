"""Freeze and load 20 previously unused public Research tasks without redistributing text."""

from __future__ import annotations

import hashlib
import json

from evals.dabstep.common import HERE, default_data_dir, load_jsonl

SELECTION = HERE / "holdout20.json"
SEED = "deepsearch-e5-2026-11-01"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def source_tasks() -> dict[str, dict]:
    path = default_data_dir() / "dabstep_research.jsonl"
    return {str(row["id"]): row for row in load_jsonl(path)}


def select() -> dict:
    tasks = source_tasks()
    exposed = {str(row["source_id"]) for row in load_jsonl(HERE / "selected_tasks.jsonl")}
    # The scorer requires explicit checklist bullets; upstream Open tasks lack them.
    types = sorted({row["type"] for row in tasks.values()} - {"Open"})
    cases = []
    for task_type in types:
        eligible = [
            row
            for row in tasks.values()
            if row["type"] == task_type and str(row["id"]) not in exposed
        ]
        ranked = sorted(eligible, key=lambda row: _digest(f"{SEED}:{row['id']}"))
        for row in ranked[:5]:
            cases.append(
                {
                    "id": f"dabstep_research_{int(row['id']):03d}",
                    "source_id": row["id"],
                    "type": task_type,
                    "question_sha256": _digest(row["question"]),
                    "checklist_sha256": _digest(row["checklist"]),
                }
            )
    if len(cases) != 20:
        raise ValueError("holdout_case_count_mismatch")
    return {"version": 1, "seed": SEED, "dataset_revision": default_data_dir().name, "cases": cases}


def validate_selection() -> dict:
    frozen = json.loads(SELECTION.read_text(encoding="utf-8"))
    if frozen != select():
        raise ValueError("holdout_selection_or_source_changed")
    return frozen


def task_for(case_id: str) -> dict | None:
    frozen = validate_selection()
    item = next((row for row in frozen["cases"] if row["id"] == case_id), None)
    return source_tasks()[str(item["source_id"])] if item else None


def main() -> int:
    SELECTION.write_text(
        json.dumps(select(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(SELECTION)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
