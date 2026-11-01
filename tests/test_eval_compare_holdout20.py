"""The holdout comparison preserves every scheduled case and freezes configuration."""

import json

import pytest

from scripts import compare_holdout20


def _write_run(root, workflow, ids, *, source="same"):
    root.mkdir()
    manifest = {
        "case_ids": ids,
        "workflow": workflow,
        "source_sha256": source,
        "suite_sha256": "suite",
        "preflight_input_sha256": {"selection": "frozen"},
        "profile": "deepseek",
        "timeout_seconds": 330,
        "cleanup_seconds": 5,
        "max_batch_reserved_tokens": 1_500_000,
    }
    (root / "manifest.json").write_text(json.dumps(manifest))
    (root / "results.jsonl").write_text(
        "\n".join(
            json.dumps(
                {
                    "id": case_id,
                    "status": "completed",
                    "elapsed_seconds": 2,
                    "attempt": f"cases/{case_id}/attempt-0001",
                }
            )
            for case_id in ids
        )
    )
    for case_id in ids:
        attempt = root / "cases" / case_id / "attempt-0001"
        attempt.mkdir(parents=True)
        evidence = [{"source": "sql", "evidence_id": "same"}]
        if workflow == "simple_sql":
            evidence += [{"source": "fee_engine", "evidence_id": str(i)} for i in range(5)]
        (attempt / "worker_result.json").write_text(json.dumps({"evidence": evidence}))
    (root / "scores.jsonl").write_text(
        "\n".join(
            json.dumps(
                {
                    "id": case_id,
                    "pass": workflow == "simple_sql",
                    "checklist_coverage": 0.9 if workflow == "simple_sql" else 0.5,
                    "supported_coverage": 0.9 if workflow == "simple_sql" else 0.5,
                    "citation_id_validity": 1.0,
                }
            )
            for case_id in ids
        )
    )


def test_comparison_keeps_full_denominator_and_rejects_source_mismatch(tmp_path, monkeypatch):
    ids = [f"dabstep_research_{index:03d}" for index in range(20)]
    monkeypatch.setattr(
        compare_holdout20,
        "validate_selection",
        lambda: {"cases": [{"id": case_id, "type": "Data Analysis"} for case_id in ids]},
    )
    baseline, final = tmp_path / "baseline", tmp_path / "final"
    _write_run(baseline, "simple_sql_no_fee", ids)
    _write_run(final, "simple_sql", ids)
    result = compare_holdout20.compare(baseline, final)
    assert result["task_count"] == 20
    assert result["baseline"]["passes"] == 0
    assert result["final"]["passes"] == 20
    manifest = json.loads((final / "manifest.json").read_text())
    manifest["source_sha256"] = "changed"
    (final / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="configuration_mismatch:source_sha256"):
        compare_holdout20.compare(baseline, final)
