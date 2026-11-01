"""Paired reports require identical case order and fixed evidence."""

import json
from pathlib import Path

import pytest

from scripts.compare_v3 import compare


def _run(tmp_path: Path, profile: str, workflow: str, evidence_value: int = 1) -> Path:
    run = tmp_path / f"{profile}_{workflow}"
    attempt = run / "cases" / "dabstep_research_002" / "attempt-0001"
    attempt.mkdir(parents=True)
    manifest = {
        "profile": profile,
        "workflow": workflow,
        "case_ids": ["dabstep_research_002"],
        "suite_sha256": "suite",
        "preflight_input_sha256": {"source": "same"},
        "timeout_seconds": 330,
        "cleanup_seconds": 5,
        "max_batch_reserved_tokens": 1500000,
        "source_sha256": "source",
    }
    (run / "manifest.json").write_text(json.dumps(manifest))
    (run / "results.jsonl").write_text(
        json.dumps(
            {
                "id": "dabstep_research_002",
                "status": "completed",
                "elapsed_seconds": 20,
                "attempt": "cases/dabstep_research_002/attempt-0001",
                "model_request_count": 1,
                "model_reserved_tokens": 100,
            }
        )
        + "\n"
    )
    (run / "scores.jsonl").write_text(
        json.dumps({"id": "dabstep_research_002", "checklist_coverage": 0.8, "pass": True}) + "\n"
    )
    (attempt / "worker_result.json").write_text(
        json.dumps({"evidence": [{"evidence_id": "ev1_sql_one", "content": evidence_value}]})
    )
    return run


def test_pairing_requires_same_simple_evidence(tmp_path: Path) -> None:
    runs = [
        _run(tmp_path, "deepseek", "simple_sql"),
        _run(tmp_path, "qwen", "simple_sql"),
        _run(tmp_path, "deepseek", "agent"),
        _run(tmp_path, "qwen", "agent"),
    ]
    assert compare(runs)["fixed_evidence_identical"] == {"dabstep_research_002": True}
    (runs[1] / "cases" / "dabstep_research_002" / "attempt-0001" / "worker_result.json").write_text(
        json.dumps({"evidence": [{"evidence_id": "ev1_sql_one", "content": 2}]})
    )
    with pytest.raises(ValueError, match="fixed_evidence_mismatch"):
        compare(runs)
