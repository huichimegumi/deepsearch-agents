"""Offline source and split preflight. Default execution never opens sealed files."""

import argparse
import hashlib
import json
import re
from pathlib import Path

from app.research.rfc_demo import DEMO_DIGESTS, HEADING, index_text

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SEALED = ROOT / "evals/results/rfc-demo-v1-sealed"
CORPUS = ROOT / "data/benchmarks/standards_v4"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def norm(text):
    return " ".join(text.split())


def sections(lock):
    upstream = json.loads((ROOT / "evals/standards/sources.lock.json").read_bytes())
    official = {row["name"]: row["sha256"] for row in upstream["files"]}
    found = {}
    if set(lock) != {name.replace(".md", ".txt") for name in DEMO_DIGESTS}:
        raise ValueError("unexpected_corpus_members")
    for name, digest in lock.items():
        raw = (CORPUS / name).read_bytes()
        text = raw.decode("utf-8").replace("\r\n", "\n")
        if sha(raw) != digest or official[name] != digest:
            raise ValueError(f"corpus_changed:{name}")
        if sha(index_text(text).encode()) != DEMO_DIGESTS[name.replace(".txt", ".md")]:
            raise ValueError(f"demo_index_input_changed:{name}")
        body = re.split(r"^Appendix [A-Z]\. {2,}", text, maxsplit=1, flags=re.M)[0]
        headings = list(HEADING.finditer(body))
        for i, heading in enumerate(headings):
            end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
            found[(int(name[3:-4]), heading[1])] = norm(body[heading.end() : end])
    return found


def check_split(directory, spec, expected_prefix, source_sections):
    if set(spec["sha256"]) != {"questions.json", "references.json"}:
        raise ValueError("unexpected_split_files")
    loaded = {}
    for name, expected in spec["sha256"].items():
        raw = (directory / name).read_bytes()
        if sha(raw) != expected:
            raise ValueError(f"split_hash_mismatch:{expected_prefix}:{name}")
        loaded[name] = json.loads(raw)

    questions, refs = loaded["questions.json"], loaded["references.json"]
    expected_ids = [f"{expected_prefix}{i:02d}" for i in range(1, spec["count"] + 1)]
    if [q["id"] for q in questions] != expected_ids or [r["id"] for r in refs] != expected_ids:
        raise ValueError(f"split_ids_mismatch:{expected_prefix}")
    prompts = {norm(q["question"]).casefold() for q in questions}
    if len(prompts) != len(expected_ids) or "" in prompts:
        raise ValueError(f"duplicate_or_empty_questions:{expected_prefix}")
    if any(set(q) != {"id", "question"} for q in questions):
        raise ValueError(f"reference_field_in_question_packet:{expected_prefix}")

    count = 0
    for ref in refs:
        outside = ref["category"] == "out_of_scope"
        if (
            not ref["points"]
            or not ref["critical_errors"]
            or not all(e.strip() for e in ref["critical_errors"])
        ):
            raise ValueError(f"incomplete_rubric:{ref['id']}")
        for point in ref["points"]:
            if not point["expected"].strip() or bool(point["anchors"]) == outside:
                raise ValueError(f"invalid_point:{ref['id']}")
            for anchor in point["anchors"]:
                key = (anchor["rfc"], anchor["section"])
                term = norm(anchor["text"])
                if not term or term not in source_sections.get(key, ""):
                    raise ValueError(f"unverified_anchor:{ref['id']}:{key}")
                count += 1
    return prompts, count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sealed", action="store_true", help="Also verify the private split offline"
    )
    args = parser.parse_args()
    lock = json.loads((HERE / "suite.lock.json").read_bytes())
    corpus = sections(lock["corpus_sha256"])
    dev, anchors = check_split(HERE, lock["splits"]["development"], "D", corpus)
    summary = {"development": len(dev), "development_anchors": anchors}
    if args.sealed:
        sealed, private_anchors = check_split(SEALED, lock["splits"]["sealed"], "H", corpus)
        if dev & sealed:
            raise ValueError("overlapping_question_text")
        summary.update(sealed=len(sealed), sealed_anchors=private_anchors)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
