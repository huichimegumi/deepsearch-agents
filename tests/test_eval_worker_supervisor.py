"""Fault injection for the public benchmark process boundary."""

import json
import sys
import time
from pathlib import Path

from evals.worker_supervisor import supervise


def _worker(tmp_path: Path) -> Path:
    script = tmp_path / "worker.py"
    script.write_text(
        """import argparse, json, signal, time
p = argparse.ArgumentParser()
p.add_argument('--result-path')
p.add_argument('--mode')
a = p.parse_args()
if a.mode == 'hang':
    print('worker started')
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    while True: time.sleep(1)
if a.mode == 'crash':
    raise RuntimeError('injected worker crash')
with open(a.result_path, 'w') as f:
    json.dump({'status': 'completed'}, f)
""",
        encoding="utf-8",
    )
    return script


def test_stuck_worker_is_killed_then_next_case_completes(tmp_path: Path) -> None:
    worker = _worker(tmp_path)
    started = time.monotonic()
    hung = supervise(
        [sys.executable, str(worker), "--mode", "hang"],
        cwd=tmp_path,
        attempt_dir=tmp_path / "hung",
        timeout_seconds=0.3,
        cleanup_seconds=0.2,
    )
    assert hung.status == "timeout"
    assert "worker started" in (tmp_path / "hung" / "stdout.log").read_text()
    if sys.platform != "win32":
        assert hung.forced_termination
    assert time.monotonic() - started < 3
    completed = supervise(
        [sys.executable, str(worker), "--mode", "ok"],
        cwd=tmp_path,
        attempt_dir=tmp_path / "completed",
        timeout_seconds=2,
    )
    assert completed.status == "completed"
    assert (
        json.loads((tmp_path / "completed" / "worker_result.json").read_text())["status"]
        == "completed"
    )


def test_crashed_worker_has_terminal_error_and_log(tmp_path: Path) -> None:
    worker = _worker(tmp_path)
    outcome = supervise(
        [sys.executable, str(worker), "--mode", "crash"],
        cwd=tmp_path,
        attempt_dir=tmp_path / "crash",
        timeout_seconds=2,
    )
    assert outcome.status == "error"
    assert "injected worker crash" in (tmp_path / "crash" / "stderr.log").read_text()


def test_missing_executable_is_terminal_error(tmp_path: Path) -> None:
    outcome = supervise(
        [str(tmp_path / "missing-worker")],
        cwd=tmp_path,
        attempt_dir=tmp_path / "missing",
        timeout_seconds=2,
    )
    assert outcome.status == "error"
    assert (
        json.loads((tmp_path / "missing" / "worker_result.json").read_text())["error_type"]
        == "FileNotFoundError"
    )
