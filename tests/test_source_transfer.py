import json
from pathlib import Path

import pytest

from evals.reports_acceptance import source_transfer as transfer
from evals.runners.experiment import file_sha256


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return file_sha256(path)


@pytest.fixture
def saved(monkeypatch, tmp_path):
    suite_path = tmp_path / "source_transfer_v1.json"
    report_path = tmp_path / "e4-16.json"
    source = tmp_path / "evals/results/frozen_run"
    cases = [
        {"id": name, "question": f"question {name}", "parts": {"part": "label"}}
        for name in (
            "toc_new_chapters",
            "toc_polite_negative",
            "pbc_attested_title",
            "excluded_named_source",
        )
    ]
    write(suite_path, {"retrieval_run": "frozen_run", "cases": cases})
    rows = []
    for case in cases:
        excluded = case["id"] == "excluded_named_source"
        records = (
            [] if excluded else [{"source": "local_document", "metadata": {"chunk_id": case["id"]}}]
        )
        folder = source / case["id"]
        artifacts = {
            "retrieval.json": write(
                folder / "retrieval.json",
                {
                    "query": case["question"],
                    "status": "NO_EVIDENCE" if excluded else "OK",
                    "records": records,
                },
            ),
            "diagnostics.json": write(
                folder / "diagnostics.json",
                {
                    "rerank_applied": True,
                    "delivered_ids": [r["metadata"]["chunk_id"] for r in records],
                },
            ),
        }
        rows.append({"id": case["id"], "status": "pass", "artifact_sha256": artifacts})
    result_sha = write(
        source / "results.json",
        {
            "status": "checked",
            "manifest": {"dataset_sha256": "live-suite-sha"},
            "source_unchanged": True,
            "dataset_unchanged": True,
            "corpus_unchanged": True,
        },
    )
    write(
        report_path,
        {
            "dataset_sha256": "live-suite-sha",
            "final": {
                "run": "frozen_run",
                "passed": 5,
                "results_sha256": result_sha,
                "cases": rows,
            },
        },
    )
    monkeypatch.setattr(transfer, "DATASET", suite_path)
    monkeypatch.setattr(transfer, "RETRIEVAL_RECORD", report_path)
    monkeypatch.setattr(transfer, "ROOT", tmp_path)
    monkeypatch.setattr(transfer, "safe_path", lambda value: Path(value).resolve())
    return cases, source


def test_transfer_loads_four_hash_bound_saved_cases_without_retrieval(saved):
    cases, _ = saved
    inputs, hashes = transfer.load_inputs()
    assert [item["id"] for item in inputs] == [case["id"] for case in cases]
    assert all(item["question"] and len(item["parts"]) == 1 for item in inputs)
    assert inputs[-1]["records"] == []
    assert len(hashes) == 11


def test_transfer_rejects_changed_saved_result_hash(saved):
    _, source = saved
    (source / "results.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="retrieval_result_hash_changed"):
        transfer.load_inputs()


def test_transfer_rejects_nonempty_excluded_source(saved):
    _, source = saved
    path = source / "excluded_named_source/retrieval.json"
    batch = json.loads(path.read_text(encoding="utf-8"))
    batch["records"] = [{"source": "local_document", "metadata": {"chunk_id": "bad"}}]
    write(path, batch)
    with pytest.raises(ValueError, match="saved_retrieval_artifact_changed"):
        transfer.load_inputs()
