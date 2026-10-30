"""The public batch cannot silently omit failures or mix evaluation versions."""

import json

import pytest

from evals.reports_acceptance import ten_case_batch as batch
from evals.runners.experiment import file_sha256


def test_plan_rejects_missing_or_duplicate_cases(monkeypatch, tmp_path):
    lock = tmp_path / "lock.json"
    lock.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(batch, "ROOT", tmp_path)
    monkeypatch.setattr(batch, "private_path", lambda path: lock)
    monkeypatch.setattr(batch, "load_cases", lambda _: ({"version": "local"}, [{"id": "x"}] * 6))
    monkeypatch.setattr(
        batch.extended, "load_suite", lambda: {"version": "extended", "cases": [{"id": "y"}] * 4}
    )
    monkeypatch.setattr(batch.extended, "validate_lock", lambda _: ({"corpus_sha256": "c"}, []))
    with pytest.raises(ValueError, match="ten distinct"):
        batch.plan(lock)


def test_summary_keeps_degraded_case_and_rejects_mixed_sources(monkeypatch, tmp_path):
    ids = [f"local_{n}" for n in range(6)] + [f"web_{n}" for n in range(4)]
    frozen = {
        "case_ids": ids,
        "lock_path": "evals/results/lock.json",
        "corpus_sha256": "corpus",
        "local_dataset_sha256": "local-data",
        "extended_dataset_sha256": "web-data",
        "lock_sha256": "lock",
        "scheduled_search_query_ceiling": 10,
    }
    root = tmp_path
    monkeypatch.setattr(batch, "ROOT", root)
    monkeypatch.setattr(batch, "plan", lambda _: frozen)
    results = root / "evals/results"
    results.mkdir(parents=True)
    (results / "lock.json").write_text("{}", encoding="utf-8")
    plan_path = results / "plan.json"
    plan_path.write_text(json.dumps(frozen), encoding="utf-8")
    paths = []
    for part, names in enumerate((ids[:6], ids[6:])):
        rows = []
        for name in names:
            folder = results / name
            folder.mkdir()
            (folder / "report.md").write_text("report", encoding="utf-8")
            (folder / "evidence.json").write_text("{}", encoding="utf-8")
            rows.append(
                {
                    "id": name,
                    "review_directory": f"evals/results/{name}",
                    "report_sha256": file_sha256(folder / "report.md"),
                    "evidence_sha256": file_sha256(folder / "evidence.json"),
                    "execution_status": "degraded" if name == ids[0] else "completed",
                    "error_type": None,
                    "failure_reasons": ["budget"] if name == ids[0] else [],
                    "elapsed_seconds": 2,
                    "audit": {
                        "report_nonempty": True,
                        "evidence_count": 0,
                        "citation_ids_resolve": True,
                        "all_reference_units_retrieved": False,
                        "all_reference_units_cited": False,
                    },
                    "trace_metrics": {"llm_calls": 1},
                }
            )
        run = {
            "inputs_unchanged": True,
            "manifest": {
                "source_sha256": "same",
                "dataset_sha256": "local-data" if part == 0 else "web-data",
                "configuration": {
                    "execution_enabled": True,
                    "selected_cases": names,
                    "model": "qwen-flash",
                    **(
                        {"indexed_local_research_enabled": False}
                        if part == 0
                        else {"default_researcher": True, "lock_sha256": "lock"}
                    ),
                },
            },
            "results": rows,
            **(
                {"corpus_sha256": "corpus"}
                if part == 0
                else {"reported_admitted_search_queries": 9}
            ),
        }
        path = results / f"run_{part}.json"
        path.write_text(json.dumps(run), encoding="utf-8")
        paths.append(path)
    output = batch.summarize(plan_path, *paths)
    assert len(output["rows"]) == 10
    assert output["execution_counts"] == {"degraded": 1, "completed": 9}
    assert output["generative_answer_accuracy"] is None
    changed = json.loads(paths[1].read_text(encoding="utf-8"))
    changed["manifest"]["source_sha256"] = "different"
    paths[1].write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="source version"):
        batch.summarize(plan_path, *paths)
