"""Freeze the selection itself as well as the upstream data."""

import json
from pathlib import Path
from unittest.mock import patch

from evals import benchmark_preflight


def test_preflight_rejects_selection_changed_without_changing_case_ids(tmp_path: Path):
    suite = json.loads(benchmark_preflight.SUITE.read_text(encoding="utf-8"))
    for source in suite["source_sets"]:
        for key in ("lock", "selection"):
            relative = Path(source[key])
            copy = tmp_path / relative
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes((benchmark_preflight.ROOT / relative).read_bytes())
    copied_selection = tmp_path / suite["source_sets"][0]["selection"]
    copied_selection.write_bytes(copied_selection.read_bytes() + b"\n")
    copied_suite = tmp_path / "suite.json"
    copied_suite.write_text(json.dumps(suite), encoding="utf-8")

    with (
        patch.object(benchmark_preflight, "SUITE", copied_suite),
        patch.object(benchmark_preflight, "ROOT", tmp_path),
        patch.object(benchmark_preflight, "verify_dabstep_files", return_value=[]),
        patch.object(benchmark_preflight, "verify_adyen_dev", return_value=[]),
        patch.object(benchmark_preflight, "verify_hybrid_files", return_value=[]),
        patch.object(benchmark_preflight, "DABSTEP_DATABASE", tmp_path / "missing.sqlite"),
        patch.object(
            benchmark_preflight,
            "_selected_dabstep_ids",
            return_value=suite["source_sets"][0]["case_ids"],
        ),
        patch.object(
            benchmark_preflight,
            "load_selected_tasks",
            return_value=[{"id": x} for x in suite["source_sets"][1]["case_ids"]],
        ),
    ):
        result = benchmark_preflight.preflight()

    assert not result["ready"]
    assert "dabstep_research_selection_hash_mismatch" in result["problems"]
