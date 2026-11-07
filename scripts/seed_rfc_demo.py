"""Verify and import the two pinned HTTP documents into the demo knowledge base."""

import json
import tempfile
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

from app.rag.bootstrap import import_directory
from app.research.rfc_demo import DEMO_DIGESTS, KB_NAME, RFC_NUMBERS, index_text

ROOT = Path(__file__).resolve().parents[1]


def main():
    lock = json.loads((ROOT / "evals/standards/sources.lock.json").read_text())
    sources = {row["name"]: row for row in lock["files"]}
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary) / KB_NAME
        directory.mkdir()
        for number in RFC_NUMBERS:
            name = f"rfc{number}.txt"
            source = sources[name]
            snapshot = ROOT / "data/benchmarks/standards_v4" / name
            if snapshot.is_file():
                raw = snapshot.read_bytes()
            else:
                with urlopen(source["url"], timeout=30) as response:
                    raw = response.read(source["bytes"] + 1)
            if sha256(raw).hexdigest() != source["sha256"]:
                raise ValueError(f"RFC source checksum mismatch: {name}")
            target = f"rfc{number}.md"
            marked = index_text(raw.decode("utf-8").replace("\r\n", "\n")).encode("utf-8")
            if sha256(marked).hexdigest() != DEMO_DIGESTS[target]:
                raise ValueError(f"RFC index input checksum mismatch: {target}")
            (directory / target).write_bytes(marked)
        _, count = import_directory(Path(temporary))
        print(f"{KB_NAME}：提交 {count} 份文档索引。请等待知识库显示就绪。")


if __name__ == "__main__":
    main()
