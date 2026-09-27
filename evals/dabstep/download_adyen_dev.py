from __future__ import annotations

import argparse
import shutil
import urllib.request
from pathlib import Path

from evals.dabstep.common import HERE, load_json, sha256_file

LOCK_PATH = HERE / "adyen_dev.lock.json"
DEFAULT_PATH = HERE / "work" / "adyen_dev.jsonl"


def verify(path: Path) -> list[str]:
    lock = load_json(LOCK_PATH)
    errors: list[str] = []
    if not path.is_file():
        return [f"missing: {path}"]
    if path.stat().st_size != lock["bytes"]:
        errors.append(f"size mismatch: {path.stat().st_size} != {lock['bytes']}")
    elif sha256_file(path) != lock["sha256"]:
        errors.append(f"sha256 mismatch: {sha256_file(path)}")
    return errors


def download(path: Path) -> None:
    if not verify(path):
        print(f"verified {path}")
        return
    lock = load_json(LOCK_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    url = f"{lock['repository_url']}/resolve/{lock['revision']}/{lock['path']}?download=true"
    with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as output:
        shutil.copyfileobj(response, output)
    errors = verify(partial)
    if errors:
        partial.unlink(missing_ok=True)
        raise RuntimeError("public dev download failed verification: " + "; ".join(errors))
    partial.replace(path)
    print(f"downloaded and verified {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download pinned public Adyen DABstep dev cases.")
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if not args.verify_only:
        download(args.path)
    errors = verify(args.path)
    if errors:
        print("\n".join(errors))
        return 1
    print(f"public dev file verified: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
