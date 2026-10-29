"""Offline literal and structural audit of paired PBC Writer candidates."""

import argparse
import json
import re
from pathlib import Path

from evals.rag.scoring import normalized
from evals.reports_acceptance.extended import safe_path
from evals.reports_acceptance.pbc_clarity import DATASET, load_retrieved, load_suite
from evals.runners.common import ROOT, write_json
from evals.runners.experiment import build_manifest, file_sha256, new_run_id


def index_titles(content):
    """Extract only the four numbered, printed-page column index entries."""
    if "专栏" not in [line.strip() for line in content.splitlines()]:
        raise ValueError("column_index_header_missing")
    titles = {}
    for line in content.splitlines():
        match = re.fullmatch(r"专栏\s+([1-4])\s+(.+?)\s+\.{3,}\s*\d{1,4}", line.strip())
        if match:
            number = int(match.group(1))
            if number in titles:
                raise ValueError("duplicate_column_index_number")
            titles[number] = match.group(2).strip()
    if set(titles) != {1, 2, 3, 4}:
        raise ValueError("four_column_titles_not_found")
    return titles


def check_titles(assertions, titles, toc_evidence_id):
    rows = []
    for assertion in assertions:
        numbers = re.findall(r"专栏\s*([1-4])", assertion["text"])
        number = int(numbers[0]) if len(numbers) == 1 else None
        rows.append(
            {
                "assertion_id": assertion["assertion_id"],
                "column_number": number,
                "exact_title_present": bool(
                    number is not None
                    and normalized(titles[number]) in normalized(assertion["text"])
                ),
                "cites_index_passage": toc_evidence_id in assertion["evidence_ids"]
                if toc_evidence_id
                else False,
            }
        )
    return {
        "assertions": rows,
        "matched_numbers": sorted({r["column_number"] for r in rows if r["exact_title_present"]}),
        "complete_index_bound": (
            len(rows) == 4
            and {r["column_number"] for r in rows} == {1, 2, 3, 4}
            and all(r["exact_title_present"] and r["cites_index_passage"] for r in rows)
        ),
    }


def check_methods(assertions, records):
    by_id = {item["evidence_id"]: item["content"] for item in records}
    rows = []
    for assertion in assertions:
        text = normalized(assertion["text"])
        linked = assertion["evidence_ids"]
        if not linked or any(i not in by_id for i in linked):
            raise ValueError("method_assertion_has_unbound_evidence")
        in_cited = any(text in normalized(by_id[i]) for i in linked)
        rows.append(
            {
                "assertion_id": assertion["assertion_id"],
                "literal_in_cited_passage": in_cited,
                "literal_in_other_delivered_passage": not in_cited
                and any(
                    text in normalized(content) for i, content in by_id.items() if i not in linked
                ),
            }
        )
    return {
        "assertions": rows,
        "all_three_literal_in_cited": len(rows) == 3
        and all(r["literal_in_cited_passage"] for r in rows),
    }


def run(retrieval_run, generation_run):
    source = safe_path(retrieval_run)
    generation = safe_path(generation_run)
    inputs, input_hashes = load_retrieved(source)
    suite = load_suite()
    generator_path = generation / "results.json"
    generated = json.loads(generator_path.read_text(encoding="utf-8"))
    if (
        generated.get("inputs_unchanged") is not True
        or generated.get("source_unchanged") is not True
        or generated["manifest"]["dataset_sha256"] != file_sha256(DATASET)
        or generated["input_sha256"] != input_hashes
        or [row["id"] for row in generated["cases"]] != [case["id"] for case in inputs]
    ):
        raise ValueError("paired_generation_provenance_invalid")
    corpus = json.loads((source / "corpus.json").read_text(encoding="utf-8"))
    reference = suite["cases"][0]["reference_chunk_id"]
    toc = next(row for row in corpus if row["chunk_id"] == reference)
    titles = index_titles(toc["content"])
    hashes = {**input_hashes, str(generator_path): file_sha256(generator_path)}
    rows = []
    for case, result in zip(inputs, generated["cases"], strict=True):
        if result["status"] != "generated_pending_semantic_review":
            raise ValueError("paired_writer_case_not_generated")
        folder = safe_path(generation / case["id"])
        for name, digest in result["artifact_sha256"].items():
            path = safe_path(folder / name)
            if file_sha256(path) != digest:
                raise ValueError("paired_writer_artifact_changed")
            hashes[str(path)] = digest
        audit = json.loads((folder / "assertions.json").read_text(encoding="utf-8"))
        records = case["records"]
        by_chunk = {r["metadata"]["chunk_id"]: r["evidence_id"] for r in records}
        if len(audit["parts"]) != 1 or audit["rejected"]:
            raise ValueError("paired_writer_audit_invalid")
        assertions = audit["parts"][0]["assertions"]
        item = {
            "id": case["id"],
            "candidate_assertions": len(assertions),
            "audit": (
                check_titles(assertions, titles, by_chunk.get(reference))
                if case["id"].startswith("pbc_column_headings")
                else check_methods(assertions, records)
            ),
        }
        rows.append(item)
    output = ROOT / "evals/results" / new_run_id("pbc_clarity_review")
    output.mkdir(parents=True, exist_ok=False)
    result = {
        "manifest": build_manifest(DATASET, {"mode": "offline_literal_structural_review"}),
        "input_sha256": hashes,
        "status": "audited",
        "cases": rows,
        "literal_match_is_not_semantic_entailment": True,
        "human_accuracy": None,
        "retrieval_queries": 0,
        "generator_calls": 0,
        "web_queries": 0,
    }
    result["source_unchanged"] = (
        result["manifest"]["source_sha256"] == build_manifest(DATASET, {})["source_sha256"]
    )
    result["inputs_unchanged"] = all(
        file_sha256(Path(path)) == digest for path, digest in hashes.items()
    )
    if not result["source_unchanged"] or not result["inputs_unchanged"]:
        result["status"] = "invalid"
    write_json(output / "results.json", result)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("retrieval_run", type=Path)
    parser.add_argument("generation_run", type=Path)
    args = parser.parse_args()
    print(run(args.retrieval_run, args.generation_run))


if __name__ == "__main__":
    main()
