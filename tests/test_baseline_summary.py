import json
from copy import deepcopy

import pytest

from evals.reports_acceptance import baseline_summary as baseline
from evals.reports_acceptance.scoring import audit_report
from evals.runners.experiment import file_sha256


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(baseline, "ROOT", tmp_path)
    dataset = write(tmp_path / "dataset.json", {})
    monkeypatch.setattr(baseline, "DEFAULT_DATASET", dataset)
    cases = [
        {"id": "positive", "answerable": True, "evidence_units": []},
        {"id": "negative", "answerable": False, "evidence_units": []},
    ]
    monkeypatch.setattr(baseline, "load_cases", lambda _: ({}, cases))
    rows, reviews = [], []
    for case in cases:
        directory = tmp_path / "evals/results/original" / case["id"]
        directory.mkdir(parents=True)
        (directory / "report.md").write_text("Insufficient evidence", encoding="utf-8")
        snapshot = {"records": []}
        write(directory / "evidence.json", snapshot)
        trace = {
            "metrics": {"llm_calls": 3, "search_queries": 0, "fetched_pages": 0},
            "status": "degraded",
            "failure_reasons": ["timeout"],
            "local_retrieval": {"record_count": 0},
        }
        write(directory / "trace.json", trace)
        hashes = {
            key + "_sha256": file_sha256(directory / name)
            for key, name in [
                ("report", "report.md"),
                ("evidence", "evidence.json"),
                ("trace", "trace.json"),
            ]
        }
        rows.append(
            {
                "id": case["id"],
                "review_directory": directory.relative_to(tmp_path).as_posix(),
                "report_sha256": hashes["report_sha256"],
                "evidence_sha256": hashes["evidence_sha256"],
                "execution_status": "degraded",
                "failure_reasons": ["timeout"],
                "error_type": None,
                "elapsed_seconds": 60,
                "trace_metrics": trace["metrics"],
                "artifact_paths": ["report.md"],
                "audit": audit_report("Insufficient evidence", snapshot, case),
            }
        )
        reviews.append(
            {
                "id": case["id"],
                **hashes,
                "keypoints": [],
                "findings": [],
                "answer_status": "no_answer",
                "summary": "No answer was delivered",
                "abstention": "not_applicable"
                if case["answerable"]
                else "insufficient_evidence_notice",
                "abstention_report_quote": "Insufficient evidence",
            }
        )
    result_path = write(
        tmp_path / "evals/results/original/results.json",
        {
            "run_id": "original",
            "inputs_unchanged": True,
            "corpus_sha256": "corpus",
            "manifest": {
                "dataset_sha256": file_sha256(dataset),
                "configuration": {
                    "execution_enabled": True,
                    "indexed_local_research_enabled": False,
                    "selected_cases": ["positive", "negative"],
                },
            },
            "results": rows,
        },
    )
    review_path = write(
        tmp_path / "review.json",
        {
            "reviewer_type": "ai_assistant_preliminary",
            "human_review": "pending",
            "review_scope": baseline.REVIEW_SCOPE,
            "execution_results_sha256": file_sha256(result_path),
            "items": reviews,
        },
    )
    return result_path, review_path


def test_all_failures_are_retained_without_publishing_accuracy(inputs):
    summary = baseline.summarize(*inputs)
    assert len(summary["rows"]) == 2
    assert summary["execution_status_counts"] == {"degraded": 2}
    assert summary["delivery_counts"] == {"no_evidence_notice": 2}
    assert summary["human_accuracy"] is None and summary["claim_support_rate"] is None
    assert "human review pending" in baseline.render(summary)


@pytest.mark.parametrize(
    "failure",
    [
        "human_flag",
        "binding",
        "duplicate",
        "missing",
        "quote",
        "evidence",
        "claim",
        "abstention_quote",
        "artifact",
        "trace",
    ],
)
def test_invalid_triage_or_artifacts_cannot_be_summarized(inputs, failure):
    results_path, review_path = inputs
    review = json.loads(review_path.read_text())
    if failure == "human_flag":
        review["human_review"] = "approved"
    elif failure == "binding":
        review["execution_results_sha256"] = "changed"
    elif failure == "duplicate":
        review["items"].append(deepcopy(review["items"][0]))
    elif failure == "missing":
        review["items"].pop()
    elif failure in {"quote", "evidence", "claim"}:
        finding = {
            "category": "evidence_misread",
            "stage": "compression",
            "reason": "Test finding",
            "report_quote": "Insufficient evidence",
            "evidence_quotes": [],
        }
        if failure == "quote":
            finding["report_quote"] = "invented quotation"
        elif failure == "evidence":
            finding["evidence_quotes"] = [{"evidence_id": "unknown", "quote": "invented"}]
        else:
            finding["claim_quote"] = "invented Claim"
        review["items"][0]["findings"] = [finding]
    elif failure == "abstention_quote":
        review["items"][1]["abstention_report_quote"] = "invented"
    elif failure == "artifact":
        (results_path.parent / "positive/report.md").write_text("changed")
    elif failure == "trace":
        path = results_path.parent / "positive/trace.json"
        trace = json.loads(path.read_text())
        trace["metrics"]["llm_calls"] = 99
        write(path, trace)
        review["items"][0]["trace_sha256"] = file_sha256(path)
    write(review_path, review)
    with pytest.raises(ValueError):
        baseline.summarize(results_path, review_path)


def test_saved_result_cannot_be_reduced_to_only_successes(inputs):
    results_path, review_path = inputs
    result = json.loads(results_path.read_text())
    result["results"].pop()
    write(results_path, result)
    review = json.loads(review_path.read_text())
    review["execution_results_sha256"] = file_sha256(results_path)
    write(review_path, review)
    with pytest.raises(ValueError, match="every frozen case"):
        baseline.summarize(results_path, review_path)
