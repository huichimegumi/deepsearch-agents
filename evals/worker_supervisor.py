"""Bound one evaluation case in a separate process and preserve every attempt."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkerOutcome:
    status: str
    elapsed_seconds: float
    exit_code: int | None
    forced_termination: bool
    result: dict | None


def atomic_json(path: Path, payload: dict) -> None:
    """Replace a report only after all bytes have reached the temporary file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _signal_tree(process: subprocess.Popen, *, force: bool) -> None:
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        if force:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=3,
                check=False,
            )
        else:
            process.terminate()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
        except ProcessLookupError:
            pass


def supervise(
    command: list[str],
    *,
    cwd: Path,
    attempt_dir: Path,
    timeout_seconds: float,
    cleanup_seconds: float = 5.0,
    environment: dict[str, str] | None = None,
) -> WorkerOutcome:
    """Return by the deadline even if the worker ignores cancellation."""
    if timeout_seconds <= 0 or cleanup_seconds < 0:
        raise ValueError("invalid_worker_deadline")
    attempt_dir.mkdir(parents=True, exist_ok=False)
    result_path = attempt_dir / "worker_result.json"
    child_env = os.environ.copy()
    if environment:
        child_env.update(environment)
    # The shared host has other GPU jobs. FastEmbed also selects CPU explicitly.
    child_env["CUDA_VISIBLE_DEVICES"] = "-1"
    child_env["SEARCH_BACKEND_LOCK"] = "duckduckgo"
    child_env["EVAL_DISABLE_SDK_RETRIES"] = "1"
    child_env["PYTHONUNBUFFERED"] = "1"
    child_env.pop("TAVILY_API_KEY", None)
    child_env.pop("PERPLEXITY_API_KEY", None)
    started = time.monotonic()
    with (
        (attempt_dir / "stdout.log").open("wb") as stdout,
        (attempt_dir / "stderr.log").open("wb") as stderr,
    ):
        try:
            process = subprocess.Popen(  # noqa: S603 - fixed argv from our own CLI
                [*command, "--result-path", str(result_path)],
                cwd=cwd,
                env=child_env,
                stdout=stdout,
                stderr=stderr,
                start_new_session=sys.platform != "win32",
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
                ),
            )
        except OSError as exc:
            atomic_json(result_path, {"status": "error", "error_type": type(exc).__name__})
            return WorkerOutcome("error", round(time.monotonic() - started, 3), None, False, None)
        forced = False
        timed_out = False
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            _signal_tree(process, force=False)
            try:
                process.wait(timeout=cleanup_seconds)
            except subprocess.TimeoutExpired:
                forced = True
                _signal_tree(process, force=True)
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
        except BaseException:
            _signal_tree(process, force=True)
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            raise

    result = None
    if result_path.is_file():
        try:
            loaded = json.loads(result_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                result = loaded
        except (OSError, json.JSONDecodeError):
            pass
    status = "timeout" if timed_out else "error"
    if not timed_out and process.returncode == 0 and result:
        status = str(result.get("status") or "completed")
    return WorkerOutcome(
        status=status,
        elapsed_seconds=round(time.monotonic() - started, 3),
        exit_code=process.returncode,
        forced_termination=forced,
        result=result,
    )
