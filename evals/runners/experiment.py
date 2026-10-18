"""Small, credential-free manifests for reproducible evaluation runs."""

import hashlib
import importlib.metadata
import json
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

from evals.runners.common import ROOT


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def new_run_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now(UTC):%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:10]}"


def build_manifest(dataset: Path, configuration: dict) -> dict:
    def git(*args):
        try:
            return subprocess.check_output(
                ["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    versions = {}
    for package in ("fastembed", "onnxruntime", "qdrant-client", "deepagents"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    changes = git("status", "--porcelain")
    tracked = git("ls-files", "--", "app", "evals") or ""
    untracked = git("ls-files", "--others", "--exclude-standard", "--", "app", "evals") or ""
    source_hashes = {
        name: file_sha256(ROOT / name)
        for name in sorted(set(tracked.splitlines() + untracked.splitlines()))
        if (ROOT / name).is_file() and Path(name).suffix in {".py", ".yaml", ".yml"}
    }
    return {
        "git_commit": git("rev-parse", "HEAD"),
        "git_dirty": bool(changes) if changes is not None else None,
        "source_sha256": hashlib.sha256(
            json.dumps(source_hashes, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "dataset_sha256": file_sha256(dataset),
        "dependency_lock_sha256": file_sha256(ROOT / "uv.lock"),
        "versions": versions,
        "configuration": configuration,
    }
