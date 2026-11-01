"""Download unmodified official RFC sources and lock reproducible metadata tables."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "benchmarks" / "standards_v4"
LOCK = Path(__file__).with_name("sources.lock.json")
SPLITS = {
    "dev": {
        "local_document": [9110, 9111, 8259, 8446, 4627],
        "web": [9309, 3986, 6265, 6455, 2396],
    },
    "holdout": {
        "local_document": [8288, 6901, 7396, 6585, 3339, 9112],
        "web": [5861, 6797, 7617, 7239, 6266, 9421],
    },
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(*, initialize: bool = False) -> dict:
    DATA.mkdir(parents=True, exist_ok=True)
    frozen = json.loads(LOCK.read_text()) if LOCK.exists() else None
    if frozen is None and not initialize:
        raise ValueError("missing_source_lock")
    requests = [
        (rfc, extension)
        for groups in SPLITS.values()
        for ids in groups.values()
        for rfc in ids
        for extension in ("txt", "json")
    ]

    def download(item):
        rfc, extension = item
        path = DATA / f"rfc{rfc}.{extension}"
        url = f"https://www.rfc-editor.org/rfc/{path.name}"
        expected = (
            next((row for row in frozen["files"] if row["name"] == path.name), None)
            if frozen
            else None
        )
        if not path.exists() or (expected and sha(path) != expected["sha256"]):
            with urllib.request.urlopen(url, timeout=45) as response:
                content = response.read(3_000_000)
            if expected and hashlib.sha256(content).hexdigest() != expected["sha256"]:
                raise ValueError(f"source_changed:{path.name}")
            path.write_bytes(content)
        return {"name": path.name, "url": url, "sha256": sha(path), "bytes": path.stat().st_size}

    with ThreadPoolExecutor(max_workers=3) as executor:
        files = list(executor.map(download, requests))
    lock = {
        "version": 1,
        "publisher": "RFC Editor / IETF",
        "files": files,
        "rights": "Unmodified RFC sources retain their copyright notices and IETF Trust terms; raw texts are not redistributed in Git.",
        "splits": SPLITS,
    }
    if initialize:
        LOCK.write_text(json.dumps(lock, indent=2) + "\n")
    elif lock != frozen:
        raise ValueError("source_lock_mismatch")
    for split, groups in SPLITS.items():
        database = DATA / f"{split}.sqlite"
        database.unlink(missing_ok=True)
        with sqlite3.connect(database) as conn:
            conn.execute(
                "CREATE TABLE standards (rfc INTEGER PRIMARY KEY, title TEXT, year INTEGER, page_count INTEGER, source_role TEXT, url TEXT)"
            )
            conn.execute("CREATE TABLE authors (rfc INTEGER, author TEXT)")
            for role, ids in groups.items():
                for rfc in ids:
                    metadata = json.loads((DATA / f"rfc{rfc}.json").read_text())
                    conn.execute(
                        "INSERT INTO standards VALUES (?,?,?,?,?,?)",
                        (
                            rfc,
                            metadata["title"],
                            int(metadata["pub_date"].split()[-1]),
                            int(metadata["page_count"]),
                            role,
                            f"https://www.rfc-editor.org/rfc/rfc{rfc}.txt",
                        ),
                    )
                    conn.executemany(
                        "INSERT INTO authors VALUES (?,?)",
                        [(rfc, author) for author in metadata["authors"]],
                    )
    return {
        "file_count": len(files),
        "sources_sha256": sha(LOCK),
        "databases": {split: sha(DATA / f"{split}.sqlite") for split in SPLITS},
    }


def catalog(split: str, sources: list[str]):
    from app.research.sources import SourceCatalog

    def pages(role):
        return [
            {
                "title": f"RFC {rfc}: "
                + json.loads((DATA / f"rfc{rfc}.json").read_text())["title"],
                "locator": f"https://www.rfc-editor.org/rfc/rfc{rfc}.txt"
                if role == "web"
                else f"document://rfc/{rfc}",
                "text": (DATA / f"rfc{rfc}.txt").read_text(),
            }
            for rfc in SPLITS[split][role]
        ]

    return SourceCatalog(
        sqlite_path=DATA / f"{split}.sqlite",
        documents=pages("local_document"),
        web_pages=pages("web"),
        allowed_sources=tuple(sources),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initialize-lock", action="store_true")
    args = parser.parse_args()
    print(json.dumps(prepare(initialize=args.initialize_lock), indent=2))


if __name__ == "__main__":
    main()
