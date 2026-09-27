from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOCK_PATH = HERE / "dataset.lock.json"
SELECTION_PATH = HERE / "task_selection.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def default_data_dir() -> Path:
    lock = load_json(LOCK_PATH)
    return ROOT / "data" / "benchmarks" / "dabstep_research" / lock["revision"]


def verify_files(data_dir: Path) -> list[str]:
    lock = load_json(LOCK_PATH)
    errors: list[str] = []
    for item in lock["files"]:
        path = data_dir / item["path"]
        if not path.is_file():
            errors.append(f"missing: {item['path']}")
            continue
        if path.stat().st_size != item["bytes"]:
            errors.append(
                f"size mismatch: {item['path']} ({path.stat().st_size} != {item['bytes']})"
            )
            continue
        actual = sha256_file(path)
        if actual != item["sha256"]:
            errors.append(f"sha256 mismatch: {item['path']} ({actual})")
    return errors
