import json

import pytest

from evals.scoring_v4 import digest
from scripts.report_v4 import load


def test_error_retry_preserves_original_and_rejects_successful_case_retry(tmp_path):
    cases = [{"id": "one", "category": "web"}]
    results = [{"id": "one", "status": "completed", "elapsed_seconds": 2}]
    (tmp_path / "manifest.json").write_text(json.dumps({"case_ids": ["one"]}))
    (tmp_path / "results.json").write_text(json.dumps(results))
    directory = tmp_path / "score-v4"
    directory.mkdir()
    row = {
        "id": "one",
        "status": "completed",
        "pass": False,
        "issues": [],
        "reference_checks": [],
        "judge_errors": ["bad index"],
        "judge_responses": [],
        "checklist_coverage": None,
        "claim_support": None,
    }
    original = {"rows": [row]}
    manifest = {
        "version": "4.1",
        "scorer_sha256": "code",
        "instruction_sha256": "prompt",
        "replicates": 1,
    }
    (directory / "scores.json").write_text(json.dumps(original))
    (directory / "manifest.json").write_text(json.dumps(manifest))
    recovered = {
        **row,
        "pass": True,
        "judge_errors": [],
        "judge_responses": [{}],
        "checklist_coverage": 1,
        "claim_support": 1,
    }
    recovery = {
        "original_scores_sha256": digest(original),
        "original_manifest_sha256": digest(manifest),
        "retry_manifest": {
            **manifest,
            "cases_sha256": digest(cases),
            "results_sha256": digest(results),
        },
        "retry_scores": [recovered],
    }
    (directory / "error_retries.json").write_text(json.dumps(recovery))
    summary = load(tmp_path, cases)["summary"]
    assert summary["passes"] == 1
    assert summary["primary_passes"] == 0
    assert json.loads((directory / "scores.json").read_text()) == original
    row["judge_errors"] = []
    original["rows"] = [row]
    (directory / "scores.json").write_text(json.dumps(original))
    recovery["original_scores_sha256"] = digest(original)
    (directory / "error_retries.json").write_text(json.dumps(recovery))
    with pytest.raises(ValueError, match="judge_retry_ineligible_case"):
        load(tmp_path, cases)
