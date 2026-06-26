"""Schema and count checks for first-phase project eval datasets."""

import json
from pathlib import Path

from evals.runners.common import load_jsonl


ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "evals" / "datasets"

EXPECTED_COUNTS = {
    "web_research_zh.jsonl": 20,
    "db_query_zh.jsonl": 20,
    "routing_boundary_zh.jsonl": 20,
    "end_to_end_report_zh.jsonl": 10,
    "rag_local_zh.jsonl": 20,
}

ALLOWED_ROUTES = {
    "network_search",
    "database_query",
    "knowledge_base",
    "file_read",
    "memory",
    "report_generation",
    "direct_answer",
    "refusal",
}

REQUIRED_FIELDS = {
    "id",
    "category",
    "task",
    "expected_route",
    "disallowed_routes",
}


def _load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_first_phase_eval_counts_and_schema():
    seen_ids: set[str] = set()
    for filename, expected_count in EXPECTED_COUNTS.items():
        rows = _load_jsonl(DATASET_DIR / filename)
        assert len(rows) == expected_count
        for row in rows:
            assert REQUIRED_FIELDS <= row.keys()
            assert row["id"] not in seen_ids
            seen_ids.add(row["id"])
            assert row["task"].strip()
            assert row.get("success_criteria") or row.get("answer_checks")
            assert set(row["expected_route"]) <= ALLOWED_ROUTES
            assert set(row["disallowed_routes"]) <= ALLOWED_ROUTES


def test_local_knowledge_base_qa_dataset_exists():
    assert (DATASET_DIR / "rag_local_zh.jsonl").exists()


def test_runner_jsonl_loader_accepts_utf8_bom(tmp_path):
    path = tmp_path / "bom.jsonl"
    path.write_text('\ufeff{"id": "sample_1", "task": "测试"}\n', encoding="utf-8")

    assert load_jsonl(path) == [{"id": "sample_1", "task": "测试"}]
