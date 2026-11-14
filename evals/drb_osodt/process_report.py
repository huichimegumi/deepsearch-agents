"""Aggregate archived DRB runtime measurements without reading source bodies."""

import argparse
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from evals.public_benchmarks.run import read
from evals.worker_supervisor import atomic_json

ANCILLARY = {"write_todos", "ls", "glob", "grep", "read_file", "read_file_content"}


def aggregate(arm, ids=None):
    statuses, failures, totals, tools, supervisor = (Counter() for _ in range(5))
    phases = defaultdict(list)
    seconds, input_tokens, output_tokens, per_case = [], [], [], []
    for path in sorted(arm.glob("*/attempt-0001/worker_result.json")):
        worker = read(path)
        case_id = int(worker["case_id"].split(":")[1])
        if ids is not None and case_id not in ids:
            continue
        tracefile = path.with_name("research_trace.json")
        state = read(path.with_name("research_result.json"))["status"]
        statuses[state] += 1
        seconds.append(worker["seconds"])
        failures.update(worker.get("failure_reasons", []))
        if not tracefile.exists():
            usage = worker.get("usage")
            if isinstance(usage, list):
                totals["llm_calls"] += len(usage)
                if all(usage):
                    input_tokens.append(sum(x["input_tokens"] for x in usage))
                    output_tokens.append(sum(x["output_tokens"] for x in usage))
            continue
        trace = read(tracefile)
        metrics = trace["metrics"]
        input_tokens.append(metrics["input_tokens"])
        output_tokens.append(metrics["output_tokens"])
        for key in (
            "llm_calls",
            "subagent_calls",
            "evidence_records",
            "claim_evidence_records",
            "search_queries",
            "fetched_pages",
            "report_cited_evidence_records",
        ):
            totals[key] += metrics[key]
        totals["duplicate_queries"] += trace["waste"]["duplicate_queries"]
        totals["duplicate_sources"] += trace["waste"]["duplicate_sources"]
        totals["withheld"] += trace["report_citation_withheld"]
        totals["zero_search"] += not trace["budget"]["usage"]["search_queries"]
        # Count unique citation IDs in the delivered text independently of the validation trace.
        report = path.with_name("report.md").read_text()
        totals["delivered_citation_ids"] += len(set(re.findall(r"\[(ev\d+_[\w-]+)\]", report)))
        tools.update(metrics["tool_calls_by_name"])
        for phase in trace["phases"]:
            phases[phase["phase_key"]].append(phase)
            if phase["phase_key"] == "supervisor_research":
                supervisor.update(phase.get("tool_calls_by_name", {}))
        per_case.append(
            {
                "id": case_id,
                "status": state,
                "seconds": worker["seconds"],
                "mode": trace["research_tool_mode"],
                "budget_usage": trace["budget"]["usage"],
                "reasons": trace["failure_reasons"],
            }
        )
    phase_summary = {
        key: {
            "calls": sum(r["llm_calls"] for r in rows),
            "median_seconds": median(r["elapsed_ms"] / 1000 for r in rows),
            "artifacts": Counter(r["artifact_status"] for r in rows),
            "statuses": Counter(r["status"] for r in rows),
        }
        for key, rows in phases.items()
    }
    if ids is not None and sum(statuses.values()) != len(ids):
        raise ValueError(f"Incomplete paired runtime archive: {arm.name}")
    return {
        "n": sum(statuses.values()),
        "statuses": statuses,
        "median_seconds": median(seconds),
        "input_tokens_median": median(input_tokens) if input_tokens else None,
        "output_tokens_median": median(output_tokens) if output_tokens else None,
        "usage_cases": len(input_tokens),
        "totals": totals,
        "phases": phase_summary,
        "tools": tools,
        "supervisor_tools": supervisor,
        "ancillary_supervisor_calls": sum(supervisor[name] for name in ANCILLARY),
        "failures": failures,
        "trace_cases": per_case,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--parallel", type=Path)
    args = parser.parse_args()
    root = args.archive
    ids = {int(q) for q in read(root / "score/summary.json")["tasks"]}
    output = {
        "all_original": {arm: aggregate(root / arm) for arm in "ACD"},
        "paired": {arm: aggregate(root / arm, ids) for arm in "ACD"},
    }
    if args.parallel:
        output["paired"]["P"] = aggregate(args.parallel, ids)
    atomic_json(args.output, output)


if __name__ == "__main__":
    main()
