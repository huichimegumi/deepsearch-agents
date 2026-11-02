"""Checkpointed public-task scoring with independent SQL audits and optional second judge."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sqlite3
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.research.report import ResearchReport
from app.research.request_budget import RequestBudget, usage
from evals.scoring_v4 import INSTRUCTION, Judgement, _indexes, digest, mechanical
from evals.worker_supervisor import atomic_json

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cell(value):
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return ["bool", value]
    try:
        number = Decimal(str(value))
        if number.is_finite():
            return ["number", str(number.normalize())]
    except InvalidOperation:
        pass
    return ["text", " ".join(str(value).casefold().split())]


def canonical(rows):
    return sorted(json.dumps([cell(v) for v in row], ensure_ascii=False) for row in rows)


def query(database, sql):
    import time

    start = time.monotonic()
    with sqlite3.connect(f"{Path(database).resolve().as_uri()}?mode=ro", uri=True) as conn:
        conn.execute("PRAGMA query_only=ON")
        conn.set_progress_handler(lambda: int(time.monotonic() - start > 5), 10000)
        # Independent evaluator: SQLite authorizer avoids lexical false positives
        # on quoted values such as a literal containing "update".
        allowed = {
            sqlite3.SQLITE_SELECT,
            sqlite3.SQLITE_READ,
            sqlite3.SQLITE_FUNCTION,
            sqlite3.SQLITE_RECURSIVE,
        }
        conn.set_authorizer(
            lambda action, *args: sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY
        )
        cursor = conn.execute(sql)
        rows = cursor.fetchmany(1001)
        if len(rows) > 1000:
            raise ValueError("reference_audit_row_limit")
    return rows


def reference_audit(case, result, database):
    oracle = case["oracle"]
    try:
        expected = query(database, oracle["reference_sql"])
        published = oracle["sql_reference"]["rows"]
        if canonical(expected) != canonical(published):
            return {"available": False, "error": "published_reference_disagrees_with_database"}
    except (ValueError, sqlite3.Error, KeyError, TypeError) as exc:
        return {"available": False, "error": type(exc).__name__}
    matches = []
    operations = result.get("operations", [])
    for operation in operations:
        if operation["source"] == "sql" and operation.get("record_count", 0) > 0:
            try:
                if canonical(query(database, operation["query"])) == canonical(expected):
                    matches.append(operation["id"])
            except (ValueError, sqlite3.Error):
                continue
    web = {op["id"] for op in operations if op["source"] == "web" and op.get("record_count", 0) > 0}
    sql = {op["id"] for op in operations if op["source"] == "sql" and op.get("record_count", 0) > 0}
    direction = oracle["direction"]
    if direction == "search_to_sql":
        dependency = any(
            op["id"] in matches
            and web.intersection(op.get("depends_on", []))
            and op.get("bindings")
            for op in operations
        )
    elif direction == "sql_to_search":
        dependency = any(
            op["source"] == "web"
            and set(matches).intersection(op.get("depends_on", []))
            and op.get("record_count", 0) > 0
            for op in operations
        )
    else:
        dependency = bool(sql and web)
    return {
        "available": True,
        "reference_rows": len(expected),
        "sql_result_match": bool(matches),
        "executed_direction": bool(dependency),
        "matching_steps": matches,
        "comparison": "row multiset; positional columns; aliases ignored; case/whitespace and decimal normalization",
    }


def model_for(provider):
    from dotenv import load_dotenv

    from app.agent.llm import DashScopeChatOpenAI, DeepSeekChatOpenAI

    load_dotenv(ROOT / ".env")
    if provider == "deepseek":
        key = os.getenv("DEEPSEEK_API_KEY")
        if not key:
            raise ValueError("missing_deepseek_judge_key")
        return DeepSeekChatOpenAI(
            model="deepseek-flash",
            api_key=key,
            base_url="https://api.deepseek.com",
            max_retries=0,
            timeout=90,
            temperature=0,
            extra_body={"thinking": {"type": "disabled"}},
        )
    key = os.getenv("DASHSCOPE_API_KEY")
    if not key:
        raise ValueError("missing_independent_judge_key")
    return DashScopeChatOpenAI(
        model="qwen-flash",
        api_key=key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        max_retries=0,
        timeout=90,
        temperature=0,
    )


def weighted_rubric(case, judgement):
    rubric = case["oracle"].get("published_rubric")
    if rubric is None:
        return None
    values = iter(row["score"] for row in judgement["criteria"])
    total = 0.0
    for dimension, criteria in rubric["criterions"].items():
        score = sum(next(values) * float(item["weight"]) for item in criteria)
        total += float(rubric["dimension_weight"][dimension]) * score
    return total


async def judge(case, result, model):
    report = ResearchReport.model_validate(result["report"])
    async with asyncio.timeout(100):
        response = (
            await model.with_structured_output(
                Judgement, include_raw=True, method="function_calling"
            )
            .bind(max_tokens=6000)
            .ainvoke(
                [
                    {
                        "role": "system",
                        "content": INSTRUCTION
                        + " Keep every reason short (under 180 characters). Candidate claims are indexed objects: evaluate exactly one support verdict per whole claim object, never split a compound claim into several indexes. Return claims=[] when candidate_claims_indexed is empty. Check candidate limitations too; they must not hide unsupported factual answers. For open research, assess substantive coverage, not merely mentioning a topic.",
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "question": case["question"],
                                "checklist": case["oracle"]["checklist"],
                                "answerable": case["oracle"]["answerable"],
                                "reference": case["oracle"].get("reference", ""),
                                "candidate": report.model_dump(),
                                "candidate_claims_indexed": [
                                    {"index": i, **claim.model_dump()}
                                    for i, claim in enumerate(report.claims, 1)
                                ],
                                "required_claim_indexes": list(range(1, len(report.claims) + 1)),
                                "evidence": result.get("evidence", []),
                            },
                            ensure_ascii=False,
                        ),
                    },
                ]
            )
        )
    parsed = response.get("parsed")
    raw = response.get("raw")
    if not isinstance(parsed, Judgement):
        return {
            "error": "judge_parse_error",
            "usage": getattr(raw, "usage_metadata", None),
            "raw_tool_calls": getattr(raw, "tool_calls", None),
        }
    try:
        _indexes(parsed.criteria, len(case["oracle"]["checklist"]))
        _indexes(parsed.claims, len(report.claims))
    except ValueError:
        return {
            "error": "judge_index_mismatch",
            "judgement": parsed.model_dump(),
            "usage": getattr(raw, "usage_metadata", None),
        }
    return {
        "judgement": parsed.model_dump(),
        "published_weighted_coverage": weighted_rubric(case, parsed.model_dump()),
        "checklist_coverage": sum(r.score for r in parsed.criteria) / len(parsed.criteria),
        "claim_support": sum(r.supported for r in parsed.claims) / len(parsed.claims)
        if parsed.claims
        else None,
        "usage": getattr(raw, "usage_metadata", None),
        "model": (getattr(raw, "response_metadata", None) or {}).get("model_name"),
    }


async def score(run, inputs, output, provider="deepseek", audit_subset=False):
    cases = read(inputs / "references.json")
    public = {row["id"]: row for row in read(inputs / "public.json")}
    results = read(run / "results.json")
    if [r["id"] for r in results] != [r["id"] for r in cases]:
        raise ValueError("incomplete_or_reordered_results")
    if audit_subset:
        selected = set()
        for suite in ("dabstep", "hybrid", "drb"):
            rows = sorted(
                [c for c in cases if c["suite"] == suite],
                key=lambda c: digest(["e7-independent-audit", c["id"]]),
            )
            selected.update(c["id"] for c in rows[:2])
        cases = [c for c in cases if c["id"] in selected]
        results = [r for r in results if r["id"] in selected]
    model = model_for(provider)
    config = {
        "version": "e7.1",
        "provider": provider,
        "model": model.model_name,
        "cases_sha256": digest(cases),
        "results_sha256": digest(results),
        "scorer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "v4_sha256": hashlib.sha256((ROOT / "evals/scoring_v4.py").read_bytes()).hexdigest(),
        "budget": {"requests": 60, "reserved_tokens": 1500000},
        "subset": audit_subset,
    }
    output.mkdir(parents=True, exist_ok=True)
    if (output / "manifest.json").exists() and read(output / "manifest.json") != config:
        raise ValueError("scoring_resume_mismatch")
    atomic_json(output / "manifest.json", config)
    budget = RequestBudget(
        output / "judge_requests.jsonl",
        max_requests=60,
        max_reserved_tokens=1500000,
        finalizing=True,
    )
    rows = []
    with budget.activate():
        for case, result in zip(cases, results, strict=True):
            checkpoint = (
                output
                / "checkpoints"
                / (hashlib.sha256(case["id"].encode()).hexdigest()[:20] + ".json")
            )
            if checkpoint.exists():
                graded = read(checkpoint)
            else:
                try:
                    graded = await judge(case, result, model)
                except Exception as exc:
                    graded = {"error": f"{type(exc).__name__}:{exc}"}
                atomic_json(checkpoint, graded)
            try:
                checks = mechanical(case, result)
            except Exception as exc:
                checks = {"issues": [f"invalid_result:{type(exc).__name__}"]}
            audit = (
                reference_audit(case, result, public[case["id"]]["catalog"]["sqlite_path"])
                if case["suite"] == "hybrid"
                else None
            )
            if audit is not None and (
                not audit.get("available")
                or not audit.get("sql_result_match")
                or not audit.get("executed_direction")
            ):
                checks["issues"].append("independent_sql_or_direction_check_failed")
            support = graded.get("claim_support")
            passed = (
                not checks["issues"]
                and not graded.get("error")
                and graded.get("checklist_coverage", 0) >= 0.8
                and support is not None
                and support >= 0.9
            )
            row = {
                "id": case["id"],
                "suite": case["suite"],
                "status": result["status"],
                **checks,
                "reference_audit": audit,
                **graded,
                "pass": bool(passed) if case["suite"] != "drb" else None,
            }
            rows.append(row)
            atomic_json(output / "scores.json", {"rows": rows})
            print(
                f"scored {len(rows)}/{len(cases)} {case['suite']}: {row['pass']} error={bool(graded.get('error'))}",
                flush=True,
            )
    summary = {
        "provider": provider,
        "scheduled": len(cases),
        "judge_errors": sum(bool(r.get("error")) for r in rows),
        "scope": "Custom provisional judge; DRB has continuous scores, not official RACE/FACT",
        "reservations": usage(budget.path),
        "suites": {},
    }
    for suite in sorted({c["suite"] for c in cases}):
        group = [r for r in rows if r["suite"] == suite]
        coverage = [r["checklist_coverage"] for r in group if "checklist_coverage" in r]
        support = [r["claim_support"] for r in group if r.get("claim_support") is not None]
        summary["suites"][suite] = {
            "scheduled": len(group),
            "completed": sum(r["status"] == "completed" for r in group),
            "passes": sum(r["pass"] is True for r in group) if suite != "drb" else None,
            "judged": len(coverage),
            "mean_coverage": sum(coverage) / len(coverage) if coverage else None,
            "mean_support": sum(support) / len(support) if support else None,
            "statuses": dict(Counter(r["status"] for r in group)),
        }
    atomic_json(output / "summary.json", summary)
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--provider", choices=("deepseek", "qwen"), default="deepseek")
    p.add_argument("--audit-subset", action="store_true")
    args = p.parse_args()
    print(
        json.dumps(
            asyncio.run(
                score(args.run, args.inputs, args.output, args.provider, args.audit_subset)
            ),
            indent=2,
        )
    )
