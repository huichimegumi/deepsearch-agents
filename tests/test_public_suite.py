"""Portable frozen selection checks; no benchmark download or task text needed."""

import json
from collections import Counter
from pathlib import Path


def test_public_suite_is_stratified_and_excludes_prior_task_ids():
    root = Path(__file__).resolve().parents[1]
    lock = json.loads((root / "evals/public_benchmarks/suite.lock.json").read_text())
    cases = lock["cases"]
    assert len({row["id"] for row in cases}) == 30
    assert Counter(row["suite"] for row in cases) == {"dabstep": 12, "hybrid": 12, "drb": 6}
    old = json.loads((root / "evals/benchmark_v3.json").read_text())["source_sets"]
    dab_ids = {
        int(i.rsplit("_", 1)[1])
        for s in old
        if s["name"].startswith("dabstep")
        for i in s["case_ids"]
    }
    hybrid_ids = {i for s in old if s["name"] == "hybrid_deep_research" for i in s["case_ids"]}
    assert not dab_ids & {r["source_id"] for r in cases if r["suite"] == "dabstep"}
    assert not hybrid_ids & {r["source_id"] for r in cases if r["suite"] == "hybrid"}
    assert set(Counter(r["stratum"] for r in cases if r["suite"] == "hybrid").values()) == {4}
    assert not any(k in row for row in cases for k in ("question", "answer", "checklist", "sql"))
