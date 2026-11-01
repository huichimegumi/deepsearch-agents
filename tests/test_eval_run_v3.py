"""The batch runner must preserve terminal rows and resume only missing cases."""

import json
from pathlib import Path

import pytest

from evals import run_v3
from evals.worker_supervisor import WorkerOutcome


def test_batch_continues_after_timeout_and_resume_skips_terminal_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(run_v3, "RESULTS", tmp_path)
    monkeypatch.setattr(run_v3, "_cases", lambda: ["one", "two"])
    monkeypatch.setattr(run_v3, "preflight", lambda: {"ready": True, "input_sha256": {}})
    seen: list[str] = []

    def fake_supervise(command: list[str], **kwargs) -> WorkerOutcome:
        case_id = command[command.index("--case-id") + 1]
        seen.append(case_id)
        return WorkerOutcome(
            "timeout" if case_id == "one" else "completed",
            1.0,
            -9 if case_id == "one" else 0,
            case_id == "one",
            None if case_id == "one" else {"status": "completed"},
        )

    monkeypatch.setattr(run_v3, "supervise", fake_supervise)
    run_dir = run_v3.run(case_ids=["one", "two"], timeout_seconds=2)
    rows = [json.loads(line) for line in (run_dir / "results.jsonl").read_text().splitlines()]
    assert [row["status"] for row in rows] == ["timeout", "completed"]
    assert json.loads((run_dir / "summary.json").read_text())["terminal"] == 2
    assert seen == ["one", "two"]
    assert run_v3.run(case_ids=["one", "two"], timeout_seconds=2, resume_run=run_dir) == run_dir
    assert seen == ["one", "two"]


def test_resume_rejects_changed_suite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(run_v3, "RESULTS", tmp_path)
    monkeypatch.setattr(run_v3, "_cases", lambda: ["one"])
    monkeypatch.setattr(run_v3, "preflight", lambda: {"ready": True, "input_sha256": {}})
    monkeypatch.setattr(
        run_v3,
        "supervise",
        lambda *args, **kwargs: WorkerOutcome("completed", 1, 0, False, {"status": "completed"}),
    )
    run_dir = run_v3.run(case_ids=["one"])
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["suite_sha256"] = "changed"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="resume_manifest_mismatch"):
        run_v3.run(case_ids=["one"], resume_run=run_dir)
