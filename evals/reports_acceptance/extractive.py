"""Opt-in, retrieval-free Web compression experiment; not a production Claim policy."""

import argparse
import asyncio
import json
from pathlib import Path

from pydantic import BaseModel, Field

from app.research.claims import validate_report_citations
from evals.reports_acceptance.extended import DATASET, safe_path
from evals.runners.common import write_json
from evals.runners.experiment import build_manifest, file_sha256, new_run_id


class SourceQuote(BaseModel):
    evidence_id: str
    quote: str = Field(min_length=20, max_length=1200)


class ExtractiveCompression(BaseModel):
    quotes: list[SourceQuote] = Field(default_factory=list, max_length=12)


def validate_quotes(proposal: ExtractiveCompression, records: list[dict]) -> dict:
    """Require literal contiguous text in a fetched Web record; no fuzzy repair.

    This verifies extract provenance only, not relevance, completeness or entailment.
    """
    eligible = {
        record["evidence_id"]: record
        for record in records
        if record.get("source") == "web"
        and record.get("metadata", {}).get("content_kind") == "fetched_page_text"
        and isinstance(record.get("content"), str)
    }
    accepted, rejected = [], []
    seen = set()
    for item in proposal.quotes:
        record = eligible.get(item.evidence_id)
        reason = (
            "ineligible_evidence"
            if record is None
            else "not_exact_substring"
            if item.quote not in record["content"]
            else None
        )
        if reason:
            rejected.append({**item.model_dump(), "reason": reason})
        elif (item.evidence_id, item.quote) not in seen:
            seen.add((item.evidence_id, item.quote))
            accepted.append(item.model_dump())
    return {"accepted": accepted, "rejected": rejected}


def render_quotes(validation: dict) -> str:
    lines = [
        "# Exact source extracts",
        "These are verbatim extracts, not verified answers. Missing text cannot prove absence.",
    ]
    for item in validation["accepted"]:
        lines.extend([f"\n[{item['evidence_id']}]", item["quote"]])
    return "\n".join(lines)


async def run(source_run: Path, *, execute: bool = False) -> Path:
    """Run once on the two frozen Web cases; never expose answer keys to the model."""
    source_run = safe_path(source_run)
    suite = json.loads(DATASET.read_text(encoding="utf-8"))
    cases = [case for case in suite["cases"] if case["id"] in {"report_web_001", "report_web_002"}]
    run_id = new_run_id("extractive_compression")
    output = safe_path(Path("evals/results") / run_id)
    output.mkdir(parents=True, exist_ok=False)
    snapshots = {case["id"]: source_run / case["id"] / "evidence.json" for case in cases}
    input_hashes = {key: file_sha256(path) for key, path in snapshots.items()}
    manifest = build_manifest(
        DATASET, {"execute": execute, "search_queries": 0, "fetched_pages": 0}
    )
    results = {
        "run_id": run_id,
        "manifest": manifest,
        "source_run": source_run.name,
        "snapshot_sha256": input_hashes,
        "cases": [],
        "human_accuracy": None,
    }
    write_json(output / "results.json", results)
    if not execute:
        return output
    from app.agent.llm import get_model
    from app.config import get_settings

    model = get_model().model_copy(update={"max_retries": 0})
    results["model"] = get_settings().llm_name
    for case in cases:
        case_dir = output / case["id"]
        case_dir.mkdir()
        records = json.loads(snapshots[case["id"]].read_text(encoding="utf-8"))["records"]
        # The only source input is the saved actual Evidence, not evaluator reference pages.
        inputs = {"question": case["question"], "records": records}
        write_json(case_dir / "inputs.json", inputs)
        row = {"id": case["id"], "logical_calls": 0, "status": "pending", "usage": []}
        results["cases"].append(row)
        try:
            row["logical_calls"] += 1
            response = await asyncio.wait_for(
                model.with_structured_output(ExtractiveCompression, include_raw=True).ainvoke(
                    [
                        (
                            "system",
                            "Select only verbatim contiguous source passages relevant to the question. "
                            "Return their exact evidence_id and quote. Never paraphrase, infer, invent a "
                            "cutoff date, or treat missing text as proof of absence. Do not use tools.",
                        ),
                        ("human", json.dumps(inputs, ensure_ascii=False)),
                    ]
                ),
                timeout=90,
            )
            raw = response.get("raw")
            row["usage"].append(getattr(raw, "usage_metadata", None))
            if response.get("parsed") is None:
                row["status"] = "compression_parse_failed"
                continue
            proposal = response["parsed"]
            checked = validate_quotes(proposal, records)
            write_json(case_dir / "quotes.json", {"proposal": proposal.model_dump(), **checked})
            row.update(
                accepted_quotes=len(checked["accepted"]), rejected_quotes=len(checked["rejected"])
            )
            if not checked["accepted"]:
                row["status"] = "no_accepted_quotes"
                continue
            handoff = render_quotes(checked)
            (case_dir / "handoff.md").write_text(handoff, encoding="utf-8")
            row["logical_calls"] += 1
            report = await asyncio.wait_for(
                model.ainvoke(
                    [
                        (
                            "system",
                            "Write a short Markdown report in Chinese from the supplied source extracts "
                            "only. Cite exact supplied evidence IDs. Distinguish known facts from missing "
                            "details. Do not infer global absence from bounded text, invent cutoff dates, "
                            "or use external knowledge or tools.",
                        ),
                        ("human", case["question"] + "\n\n" + handoff),
                    ]
                ),
                timeout=90,
            )
            row["usage"].append(getattr(report, "usage_metadata", None))
            if not isinstance(report.content, str):
                raise ValueError("non_text_writer_output")
            (case_dir / "report.md").write_text(report.content, encoding="utf-8")
            validation = validate_report_citations(
                report.content,
                allowed_evidence_ids=[item["evidence_id"] for item in checked["accepted"]],
                citations_required=True,
            )
            row["citation_valid"] = validation.valid
            row["status"] = "generated_pending_content_review"
        except Exception as exc:  # noqa: BLE001 - retain failed experiments, never retry for success
            row["status"] = "failed"
            row["error_type"] = type(exc).__name__
        finally:
            row["artifact_sha256"] = {
                path.name: file_sha256(path)
                for path in sorted(case_dir.iterdir())
                if path.is_file()
            }
            write_json(output / "results.json", results)
    results["inputs_unchanged"] = input_hashes == {
        key: file_sha256(path) for key, path in snapshots.items()
    }
    results["source_unchanged"] = (
        manifest["source_sha256"] == build_manifest(DATASET, {})["source_sha256"]
    )
    write_json(output / "results.json", results)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_run", type=Path)
    parser.add_argument(
        "--execute", action="store_true", help="Allow four logical LLM calls; no retrieval"
    )
    args = parser.parse_args()
    print(asyncio.run(run(args.source_run, execute=args.execute)))


if __name__ == "__main__":
    main()
