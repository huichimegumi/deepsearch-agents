"""Sample cited prose from A/C/D and judge it against the saved source excerpts."""

import argparse
import asyncio
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from app.research.request_budget import RequestBudget, usage
from evals.e6_claim_audit import PROMPT, Judgment
from evals.public_benchmarks.run import read
from evals.public_benchmarks.score import model_for
from evals.worker_supervisor import atomic_json

CITATION = re.compile(r"\[((?:ev\d+_[\w-]+)|\d+)\]")
MODEL = "qwen3.8-max-0902"


def select(root):
    """Pick up to two distinct cited spans per report, without looking at scores."""
    samples = []
    skipped = Counter()
    for arm in "ACD":
        for report in sorted((root / arm).glob("*/attempt-0001/report.md")):
            directory = report.parent
            case = directory.parent.name
            if arm == "A":
                records = {str(r["n"]): r["text"] for r in read(directory / "sources.json")}
            else:
                records = {
                    r["evidence_id"]: r["content"]
                    for r in read(directory / "evaluation_evidence.json")["records"]
                }
            text = report.read_text(encoding="utf-8").split("\n## Sources\n", 1)[0]
            candidates = {}
            for line in text.splitlines():
                if line.lstrip().startswith(("#", "|", ">", "```")):
                    continue
                start = 0
                for match in re.finditer(r"(?:\[(?:ev\d+_[\w-]+|\d+)\]\s*)+", line):
                    span = line[start : match.start()].strip(" .;:-*")
                    start = match.end()
                    ids = list(dict.fromkeys(CITATION.findall(match[0])))
                    if len(span) < 20:
                        continue
                    key = hashlib.sha256(
                        ("drb-citation-v1" + arm + case + span + str(ids)).encode()
                    ).hexdigest()[:24]
                    candidates[key] = {
                        "id": key,
                        "arm": arm,
                        "case": case,
                        "claim": span,
                        "evidence": [records.get(i) for i in ids],
                    }
            if not candidates:
                skipped[arm] += 1
            samples.extend(candidates[k] for k in sorted(candidates)[:2])
    return samples, dict(skipped)


async def run(root, output):
    samples, skipped = select(root)
    output.mkdir(parents=True, exist_ok=True)
    packet = {"model": MODEL, "samples": samples, "reports_without_sample": skipped}
    manifest = output / "sample.json"
    if manifest.exists() and read(manifest) != packet:
        raise ValueError("Citation sample changed")
    atomic_json(manifest, packet)
    limit = asyncio.Semaphore(4)
    budget = RequestBudget(output / "requests.jsonl", len(samples), 1_000_000, finalizing=True)
    model = (
        model_for("qwen")
        .model_copy(
            update={
                "model_name": MODEL,
                "extra_body": {"enable_thinking": False},
            }
        )
        .with_structured_output(Judgment, include_raw=True)
        .bind(max_tokens=400)
    )

    async def audit(item):
        path = output / "judgments" / f"{item['id']}.json"
        if path.exists():
            return read(path)
        row = {"id": item["id"], "arm": item["arm"]}
        if not all(item["evidence"]):
            row["error"] = "unresolved_citation"
        else:
            payload = {
                "claim": item["claim"],
                "evidence": [
                    {"number": i, "text": text} for i, text in enumerate(item["evidence"], 1)
                ],
            }
            async with limit:
                try:
                    with budget.activate():
                        result = await model.ainvoke(
                            [
                                ("system", PROMPT),
                                ("human", json.dumps(payload, ensure_ascii=False)),
                            ]
                        )
                    row["usage"] = result["raw"].usage_metadata
                    parsed = result["parsed"]
                    if (
                        not isinstance(parsed, Judgment)
                        or any(not 1 <= n <= len(item["evidence"]) for n in parsed.evidence_numbers)
                        or (
                            parsed.verdict in {"supported", "partial"}
                            and not parsed.evidence_numbers
                        )
                    ):
                        row["error"] = "invalid_response"
                    else:
                        row["judgment"] = parsed.model_dump()
                except Exception as error:
                    row["error"] = type(error).__name__
        atomic_json(path, row)
        return row

    rows = await asyncio.gather(*(audit(item) for item in samples))
    summary = {"model": MODEL, "reports_without_sample": skipped, **usage(budget.path), "arms": {}}
    for arm in "ACD":
        subset = [row for row in rows if row["arm"] == arm]
        verdicts = Counter(row["judgment"]["verdict"] for row in subset if "judgment" in row)
        errors = Counter(row["error"] for row in subset if "error" in row)
        summary["arms"][arm] = {
            "sampled": len(subset),
            "valid": sum(verdicts.values()),
            "verdicts": verdicts,
            "errors": errors,
            "reports_sampled": len({item["case"] for item in samples if item["arm"] == arm}),
        }
    atomic_json(output / "summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    asyncio.run(run(args.run, args.output))
