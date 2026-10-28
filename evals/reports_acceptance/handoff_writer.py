"""Write from verified per-part source handoffs; assisted evaluation, not automatic research."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from evals.reports_acceptance.coverage_review import diagnose_review
from evals.reports_acceptance.extended import DATASET, safe_path
from evals.reports_acceptance.writer_fidelity import (
    OFFICIAL_DOMAINS,
    WRITER_INSTRUCTION,
    StructuredWriter,
    audit_assertions,
    experiment_model,
    prepare_extracts,
)
from evals.runners.common import ROOT, write_json
from evals.runners.experiment import build_manifest, file_sha256, new_run_id

REVIEW_RECORD = ROOT / "evals/reports/e4-4-question-coverage-2026-10-27.json"


def load_handoffs(source_run: Path) -> tuple[list[dict], dict[str, str]]:
    """Bind assisted selections to published hashes and recheck actual source text."""
    record = json.loads(REVIEW_RECORD.read_text(encoding="utf-8"))
    if source_run.name != record["experiment_run"]:
        raise ValueError("source_run_not_bound_to_review_record")
    hashes = {str(REVIEW_RECORD): file_sha256(REVIEW_RECORD)}
    inputs = []
    for case in record["cases"]:
        case_id = case["id"]
        folder = safe_path(source_run / case_id)
        expected = {**case["artifact_sha256"], **case["offline_review_artifact_sha256"]}
        for name in ("inputs.json", "coverage.json", "source_review.json", "diagnostics.json"):
            path = safe_path(folder / name)
            if file_sha256(path) != expected[name]:
                raise ValueError("review_input_hash_mismatch")
            hashes[str(path)] = expected[name]
        original = json.loads((folder / "inputs.json").read_text(encoding="utf-8"))
        review = json.loads((folder / "source_review.json").read_text(encoding="utf-8"))
        if (
            review["inputs_sha256"] != expected["inputs.json"]
            or review["coverage_sha256"] != expected["coverage.json"]
        ):
            raise ValueError("review_not_bound_to_original_inputs")
        diagnosis = diagnose_review(
            original,
            json.loads((folder / "coverage.json").read_text(encoding="utf-8")),
            review["parts"],
        )
        if diagnosis != json.loads((folder / "diagnostics.json").read_text(encoding="utf-8")):
            raise ValueError("review_reproduction_mismatch")
        extracts, parts = [], []
        for part in diagnosis["reviewed_source_handoff"]:
            checked = prepare_extracts(
                part["quotes"], original["records"], OFFICIAL_DOMAINS[case_id]
            )
            if checked["excluded"]:
                raise ValueError("review_contains_non_official_source")
            ids = []
            for extract in checked["extracts"]:
                # Bind identical text used for different question parts independently.
                digest = hashlib.sha256(
                    (part["part_id"] + extract["quote_id"]).encode()
                ).hexdigest()[:24]
                extract = {**extract, "quote_id": "qtx1_" + digest, "part_id": part["part_id"]}
                extracts.append(extract)
                ids.append(extract["quote_id"])
            parts.append({"part_id": part["part_id"], "label": part["label"], "quote_ids": ids})
        inputs.append(
            {"id": case_id, "question": original["question"], "parts": parts, "extracts": extracts}
        )
    if {case["id"] for case in inputs} != set(OFFICIAL_DOMAINS) or len(inputs) != 2:
        raise ValueError("requires_two_bound_cases")
    return inputs, hashes


def audit_handoff(proposal: StructuredWriter, case: dict) -> dict:
    """Check per-part links and preserve all gaps; no entailment or completeness score."""
    audit = audit_assertions(proposal, case["extracts"])
    by_quote = {item["quote_id"]: item["part_id"] for item in case["extracts"]}
    grouped = {part["part_id"]: [] for part in case["parts"]}
    for assertion in audit["accepted"]:
        part_ids = {by_quote[quote_id] for quote_id in assertion["quote_ids"]}
        if len(part_ids) != 1:
            audit["rejected"].append({**assertion, "reason": "cross_part_quote_links"})
        else:
            grouped[next(iter(part_ids))].append(assertion)
    parts = []
    for part in case["parts"]:
        assertions = grouped[part["part_id"]]
        parts.append(
            {
                **part,
                "status": "candidate_answer" if assertions else "unresolved",
                "assertions": assertions,
                "reason": "linked_candidate"
                if assertions
                else "reviewed_evidence_gap"
                if not part["quote_ids"] and case.get("assisted_source_selection", True)
                else "no_valid_selected_quote"
                if not part["quote_ids"]
                else "writer_omission",
                "semantic_support": "pending_review",
            }
        )
    return {
        "assisted_source_selection": case.get("assisted_source_selection", True),
        "parts": parts,
        "rejected": audit["rejected"],
        "model_unanswered_topics": audit["unanswered_topics"],
        "candidate_parts": sum(p["status"] == "candidate_answer" for p in parts),
        "unresolved_parts": sum(p["status"] == "unresolved" for p in parts),
    }


def render_candidate(audit: dict) -> str:
    lines = [
        "# Assisted Writer candidate"
        if audit["assisted_source_selection"]
        else "# Fixed-pool Writer candidate",
        "",
        "关联已核验；选段方式见运行清单，语义与完整性待审阅。",
    ]
    for part in audit["parts"]:
        lines += ["", "## " + part["label"]]
        if not part["assertions"]:
            lines += ["未解决：当前没有通过关联检查的回答；不能据此断言资料不存在。"]
        for assertion in part["assertions"]:
            cites = " ".join(f"[{value}]" for value in assertion["evidence_ids"])
            lines += [assertion["text"] + " " + cites]
    return "\n".join(lines)


async def run(source_run: Path, *, execute: bool = False) -> Path:
    inputs, hashes = load_handoffs(safe_path(source_run))
    return await execute_handoffs(inputs, hashes, execute=execute)


async def execute_handoffs(
    inputs, hashes, *, execute=False, dataset=None, prefix="handoff_writer", selector=None
):
    """Shared bounded execution for reviewed handoffs and automatic fixed-pool selection."""
    dataset = DATASET if dataset is None else dataset
    output = safe_path(Path("evals/results") / new_run_id(prefix))
    output.mkdir(parents=True, exist_ok=False)
    manifest = build_manifest(
        dataset,
        {
            "execute": execute,
            "assisted_source_selection": selector is None,
            "max_logical_calls": len(inputs) * (2 if selector else 1),
            "search_queries": 0,
            "fetched_pages": 0,
            "provider_retries": 0,
            "timeout_seconds_per_call": 90,
            "writer_instruction_sha256": hashlib.sha256(WRITER_INSTRUCTION.encode()).hexdigest(),
            "selector": selector.__name__ if selector else None,
        },
    )
    results = {
        "manifest": manifest,
        "input_sha256": hashes,
        "cases": [],
        "human_accuracy": None,
        "human_claim_support_rate": None,
    }
    write_json(output / "results.json", results)
    model = experiment_model() if execute else None
    if execute:
        from app.config import get_settings

        results["model"] = get_settings().llm_name
    for case in inputs:
        folder = output / case["id"]
        folder.mkdir()
        write_json(folder / "inputs.json", case)
        row = {"id": case["id"], "logical_calls": 0, "status": "offline_template_only"}
        results["cases"].append(row)
        try:
            proposal = StructuredWriter()
            if execute and selector is not None:
                case = await selector(model, case, folder, row)
                write_json(folder / "writer_inputs.json", case)
                row["status"] = "no_valid_selected_quotes"
            if execute and (selector is None or case["extracts"]):
                row["logical_calls"] += 1
                response = await asyncio.wait_for(
                    model.with_structured_output(StructuredWriter, include_raw=True).ainvoke(
                        [
                            ("system", WRITER_INSTRUCTION),
                            ("human", json.dumps(case, ensure_ascii=False)),
                        ]
                    ),
                    timeout=90,
                )
                raw = response.get("raw")
                row["usage"] = getattr(raw, "usage_metadata", None)
                write_json(folder / "raw_response.json", {"content": getattr(raw, "content", None)})
                row["status"] = "parse_failed"
                if response.get("parsed") is not None:
                    proposal = response["parsed"]
                    row["status"] = "generated_pending_semantic_review"
            audit = audit_handoff(proposal, case)
            write_json(folder / "assertions.json", {"proposal": proposal.model_dump(), **audit})
            (folder / "candidate.md").write_text(render_candidate(audit), encoding="utf-8")
            row.update(
                candidate_parts=audit["candidate_parts"],
                unresolved_parts=audit["unresolved_parts"],
                rejected_assertions=len(audit["rejected"]),
            )
        except Exception as exc:  # noqa: BLE001 - retain failure, no retries for success
            row.update(status="failed", error_type=type(exc).__name__)
        finally:
            row["artifact_sha256"] = {p.name: file_sha256(p) for p in sorted(folder.iterdir())}
            write_json(output / "results.json", results)
    results["inputs_unchanged"] = all(file_sha256(Path(p)) == h for p, h in hashes.items())
    results["source_unchanged"] = (
        manifest["source_sha256"] == build_manifest(dataset, {})["source_sha256"]
    )
    write_json(output / "results.json", results)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_run", type=Path)
    parser.add_argument(
        "--execute", action="store_true", help="Two assisted Writer calls, no search"
    )
    args = parser.parse_args()
    print(asyncio.run(run(args.source_run, execute=args.execute)))


if __name__ == "__main__":
    main()
