"""Smoke tests for first-phase eval runners."""

from evals.runners.run_all_evals import run_all
from evals.runners.run_db_eval import run as run_db
from evals.runners.run_rag_local_eval import DEFAULT_DATASET as RAG_LOCAL_DATASET
from evals.runners.run_rag_local_eval import load_jsonl as load_rag_jsonl
from evals.runners.run_report_eval import _score_report_row
from evals.runners.run_report_eval import run as run_report


def test_db_eval_runner_reports_all_samples():
    report = run_db()

    assert report["total"] == 20
    assert sum(report["status_counts"].values()) == 20


def test_report_eval_runner_reports_all_samples():
    report = run_report()

    assert report["total"] == 10
    assert sum(report["status_counts"].values()) == 10
    assert report["baseline"]["trace_coverage"] == 0
    assert report["baseline"]["p95_elapsed_ms"] is None


def test_degraded_report_does_not_receive_execution_completion_credit():
    score = _score_report_row(
        {
            "status": "degraded",
            "final_result_present": True,
            "expected_route": ["network_search", "report_generation"],
            "required_sections": ["a", "b", "c", "d"],
            "artifact_expectation": "markdown",
            "artifacts": ["report.md"],
        }
    )

    assert score["score_components"]["execution_completed"] == 0
    assert score["scored_status"] == "partial"


def test_rag_local_eval_dataset_is_available_for_runner():
    rows = load_rag_jsonl(RAG_LOCAL_DATASET)

    assert len(rows) == 20


def test_all_eval_runner_can_skip_web_for_ci():
    report = run_all(include_web=False, include_rag=False)

    assert set(report["evals"]) == {
        "routing_boundary_zh",
        "db_query_zh",
        "rag_local_zh",
        "end_to_end_report_zh",
        "web_research_zh",
    }
