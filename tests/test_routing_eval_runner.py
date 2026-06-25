"""Tests for the lightweight routing eval runner."""

from evals.runners.run_routing_eval import DEFAULT_DATASET, run


def test_routing_eval_runner_executes_and_scores_rows():
    report = run(DEFAULT_DATASET)

    assert report["total"] == 20
    assert 0 <= report["route_accuracy"] <= 1
    assert "failures" in report
