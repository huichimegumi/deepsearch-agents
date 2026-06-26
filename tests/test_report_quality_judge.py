"""Tests for lightweight report quality judge helpers."""

from evals.runners.run_report_quality_judge import (
    _extract_json_object,
    _normalize_judge_result,
    run,
)


def test_extract_json_object_from_fenced_response():
    payload = _extract_json_object(
        """```json
{"task_completion": 28, "required_sections": 18}
```"""
    )

    assert payload["task_completion"] == 28
    assert payload["required_sections"] == 18


def test_normalize_judge_result_bounds_scores():
    result = _normalize_judge_result(
        {
            "task_completion": 40,
            "required_sections": 18,
            "actionability": -1,
            "writing_quality": 20,
            "major_issues": ["a"],
        }
    )

    assert result["task_completion"] == 30
    assert result["actionability"] == 0
    assert result["total"] == 68
    assert result["grade"] == "fair"


def test_run_marks_missing_artifact(tmp_path):
    dataset = tmp_path / "reports.jsonl"
    dataset.write_text(
        '{"id":"missing_report","task":"生成报告","required_sections":["结论"]}\n',
        encoding="utf-8",
    )

    report = run(dataset)

    assert report["total"] == 1
    assert report["status_counts"] == {"missing_artifact": 1}
    assert report["results"][0]["score"] == 0
