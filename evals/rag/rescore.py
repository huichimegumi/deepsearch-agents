"""Regrade stored Top-5 passages under new labels without repeating retrieval or inference."""

import argparse
import json
from copy import deepcopy
from pathlib import Path

from evals.rag.protocol import canonical_sha256
from evals.rag.run_retrieval import paired_summary, summarize, summary_markdown
from evals.rag.scoring import normalized, score_retrieval, validate_cases
from evals.runners.common import RESULTS_DIR, load_jsonl, now_utc, write_json, write_markdown
from evals.runners.experiment import build_manifest, new_run_id


def rescore(original: dict, cases: list[dict]) -> dict:
    validate_cases(cases)
    by_id = {case["id"]: case for case in cases}
    old_cases = {case["id"]: case for case in original["annotation_snapshot"]}
    rows = deepcopy(original["results"])
    used = {row["case_id"] for row in rows}
    if used - by_id.keys():
        raise ValueError("New annotations omit a previously evaluated case")
    for case_id in used:
        if normalized(by_id[case_id]["question"]) != normalized(old_cases[case_id]["question"]):
            raise ValueError("Cannot rescore a changed question")
    for row in rows:
        if row["status"] == "ok":
            if "top_hits" not in row:
                raise ValueError("Rescoring requires stored original passage text")
            row["metrics"] = score_retrieval(by_id[row["case_id"]], row["top_hits"])
    report = deepcopy(original)
    report.update(
        run_id=new_run_id("rag_rescore"),
        generated_at=now_utc(),
        evaluation_kind="annotation_rescore_only_no_retrieval_or_model_calls",
        original_run_id=original["run_id"],
        original_summary=original["summary"],
        annotation_snapshot=[by_id[i] for i in sorted(used)],
        annotation_case_ids_not_executed=sorted(by_id.keys() - used),
        results=rows,
        summary=summarize(rows),
        paired=paired_summary(rows),
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    args = parser.parse_args()
    original = json.loads(args.results.read_text(encoding="utf-8"))
    cases = load_jsonl(args.dataset)
    report = rescore(original, cases)
    report["rescoring_manifest"] = build_manifest(args.dataset, {})
    report["new_annotation_canonical_sha256"] = canonical_sha256(cases)
    output = RESULTS_DIR / report["run_id"]
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "results.json", report)
    write_markdown(output / "summary.md", summary_markdown(report))
    print(
        json.dumps(
            {
                "output": str(output),
                "original": report["original_summary"],
                "rescored": report["summary"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
