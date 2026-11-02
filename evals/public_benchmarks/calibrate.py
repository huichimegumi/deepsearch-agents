"""Controlled semantic corruption checks for both configured model judges."""

from __future__ import annotations

import argparse
import asyncio
import copy
from pathlib import Path

from app.research.request_budget import RequestBudget, usage
from evals.public_benchmarks.score import judge, model_for, read
from evals.scoring_v4 import digest, mechanical
from evals.worker_supervisor import atomic_json


def fixtures():
    evidence = [
        {
            "evidence_id": "ev1_fixture_city",
            "source": "local_document",
            "locator": "fixture:lab",
            "content": "The lab is in Kyoto. It opened in 2020. It has 2 rooms.",
        },
        {
            "evidence_id": "ev1_fixture_other",
            "source": "local_document",
            "locator": "fixture:other",
            "content": "A different lab is in Osaka. It opened in 2022.",
        },
    ]
    case = {
        "id": "controlled",
        "question": "State this lab's city and opening year.",
        "oracle": {
            "answerable": True,
            "checklist": ["The lab is in Kyoto.", "The lab opened in 2020."],
        },
    }
    result = {
        "status": "completed",
        "report": {
            "title": "Lab findings",
            "answerability": "answered",
            "claims": [
                {
                    "text": "The lab is in Kyoto and opened in 2020.",
                    "evidence_ids": ["ev1_fixture_city"],
                }
            ],
            "facts": [],
            "limitations": [],
        },
        "evidence": evidence,
    }
    rows = []

    def add(name, c, r, accepted):
        rows.append(
            {
                "id": name,
                "case": copy.deepcopy(c),
                "result": copy.deepcopy(r),
                "expected_accept": accepted,
            }
        )

    add("correct", case, result, True)
    wrong = copy.deepcopy(result)
    wrong["report"]["claims"][0]["text"] = "The lab is in Osaka and opened in 2022."
    add("wrong_facts", case, wrong, False)
    wrong = copy.deepcopy(result)
    wrong["report"]["claims"][0]["evidence_ids"] = ["ev1_fixture_other"]
    add("known_but_wrong_citation", case, wrong, False)
    wrong = copy.deepcopy(result)
    wrong["report"]["claims"][0]["evidence_ids"] = []
    add("missing_citation", case, wrong, False)
    wrong = copy.deepcopy(result)
    wrong["report"]["claims"][0]["text"] = "The lab is in Kyoto."
    add("missing_year", case, wrong, False)
    wrong = copy.deepcopy(result)
    wrong["report"]["claims"] = []
    wrong["report"]["limitations"] = ["The lab is in Osaka and opened in 2022."]
    add("facts_hidden_in_limitations", case, wrong, False)
    refusal = copy.deepcopy(result)
    refusal["report"].update(
        answerability="insufficient_evidence",
        claims=[],
        limitations=["The supplied lab records do not establish a deployment CPU limit."],
    )
    noanswer = copy.deepcopy(case)
    noanswer.update(question="What is the production deployment CPU limit?")
    noanswer["oracle"] = {
        "answerable": False,
        "checklist": [
            "Correctly state that the supplied records do not establish a deployment CPU limit; do not invent one."
        ],
    }
    add("correct_scoped_refusal", noanswer, refusal, True)
    add("wrong_refusal", case, refusal, False)
    return rows


async def run(output):
    output.mkdir(parents=True, exist_ok=True)
    cases = fixtures()
    manifest = {
        "cases_sha256": digest(cases),
        "scorer_sha256": __import__("hashlib")
        .sha256(Path(__file__).with_name("score.py").read_bytes())
        .hexdigest(),
        "providers": ["deepseek", "qwen"],
    }
    if (output / "manifest.json").exists() and read(output / "manifest.json") != manifest:
        raise ValueError("calibration_resume_mismatch")
    atomic_json(output / "manifest.json", manifest)
    rows = []
    for provider in manifest["providers"]:
        model = model_for(provider)
        budget = RequestBudget(
            output / f"{provider}-requests.jsonl",
            max_requests=12,
            max_reserved_tokens=250000,
            finalizing=True,
        )
        with budget.activate():
            for item in cases:
                checkpoint = output / f"{provider}-{item['id']}.json"
                if checkpoint.exists():
                    graded = read(checkpoint)
                else:
                    try:
                        graded = await judge(item["case"], item["result"], model)
                    except Exception as exc:
                        graded = {"error": f"{type(exc).__name__}:{exc}"}
                    atomic_json(checkpoint, graded)
                checks = mechanical(item["case"], item["result"])
                accepted = (
                    not checks["issues"]
                    and not graded.get("error")
                    and graded.get("checklist_coverage", 0) >= 0.8
                    and (graded.get("claim_support") is None or graded["claim_support"] >= 0.9)
                )
                rows.append(
                    {
                        "provider": provider,
                        "id": item["id"],
                        "expected_accept": item["expected_accept"],
                        "actual_accept": bool(accepted),
                        "matched": not graded.get("error")
                        and bool(accepted) == item["expected_accept"],
                        "issues": checks["issues"],
                        "coverage": graded.get("checklist_coverage"),
                        "support": graded.get("claim_support"),
                        "error": graded.get("error"),
                    }
                )
    summary = {
        "scope": "Controlled authored calibration, not human review or natural-report accuracy",
        "cases": rows,
        "matched": sum(r["matched"] for r in rows),
        "scheduled": len(rows),
        "judge_errors": sum(bool(row.get("error")) for row in rows),
        "reservations": {
            provider: usage(output / f"{provider}-requests.jsonl")
            for provider in manifest["providers"]
        },
    }
    atomic_json(output / "summary.json", summary)
    print(__import__("json").dumps(summary, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    asyncio.run(run(p.parse_args().output))
