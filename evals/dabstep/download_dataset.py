from __future__ import annotations

import argparse
import shutil
import urllib.request
from pathlib import Path

from evals.dabstep.common import LOCK_PATH, default_data_dir, load_json, sha256_file, verify_files


def download(data_dir: Path) -> None:
    lock = load_json(LOCK_PATH)
    base = f"{lock['repository_url']}/resolve/{lock['revision']}"
    for item in lock["files"]:
        destination = data_dir / item["path"]
        if (
            destination.is_file()
            and destination.stat().st_size == item["bytes"]
            and sha256_file(destination) == item["sha256"]
        ):
            print(f"verified {item['path']}")
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(destination.suffix + ".part")
        url = f"{base}/{item['path']}?download=true"
        print(f"downloading {item['path']} ({item['bytes']} bytes)")
        with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output)

        if partial.stat().st_size != item["bytes"] or sha256_file(partial) != item["sha256"]:
            partial.unlink(missing_ok=True)
            raise RuntimeError(f"downloaded file failed lock verification: {item['path']}")
        partial.replace(destination)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download the pinned DABStep-Research snapshot.")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir())
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    if not args.verify_only:
        download(args.data_dir)
    errors = verify_files(args.data_dir)
    if errors:
        for error in errors:
            print(error)
        return 1
    print(f"all locked files verified in {args.data_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
