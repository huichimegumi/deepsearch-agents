"""Recompile archived OSODT responses offline into a new output directory."""

import argparse
from pathlib import Path

from aeollm2_osodt.artifacts import load_jsonl_by_request_id
from aeollm2_osodt.dataset import discover_documents
from aeollm2_osodt.pipeline import _load_rubrics, build_requests, compile_artifacts
from aeollm2_osodt.prompting import load_prompt_scales

from evals.drb_osodt.score_compat import REVISION, parse_score_object, strict_parse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("score", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--scales", required=True, type=Path)
    args = parser.parse_args()
    root = args.score
    docs = discover_documents(root / "inputs/reports")
    rubrics = _load_rubrics(root / "inputs/rubrics", {doc.question_id for doc in docs})
    requests = {
        r.request_id: r
        for r in build_requests("osodt", docs, rubrics, load_prompt_scales(args.scales))
    }
    responses = load_jsonl_by_request_id(root / "osodt/responses.jsonl")
    if responses.keys() != requests.keys():
        raise ValueError("Incomplete archived response set")
    recovered = []
    for key, record in responses.items():
        request = requests[key]
        if request.prompt_sha256 != record["prompt_sha256"]:
            raise ValueError(f"Archived prompt differs: {key}")
        if record["parse_valid"]:
            if strict_parse(record["raw_response"], request.expected_counts) != record["scores"]:
                raise ValueError(f"Archived scores differ: {key}")
        else:
            scores = parse_score_object(record["raw_response"], request.expected_counts)
            responses[key] = {**record, "parse_valid": True, "scores": scores}
            recovered.append(key)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "inputs").symlink_to((root / "inputs").resolve(), target_is_directory=True)
    compile_artifacts("osodt", docs, rubrics, responses, args.output / "osodt")
    print(REVISION, "recovered", recovered)


if __name__ == "__main__":
    main()
