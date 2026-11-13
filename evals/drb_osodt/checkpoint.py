"""Resume sequential DRB workers without overwriting completed reports."""

from datetime import UTC, datetime

from evals.public_benchmarks.run import read
from evals.worker_supervisor import atomic_json


def open_run(output, manifest):
    output.mkdir(parents=True, exist_ok=True)
    path = output / "manifest.json"
    if path.exists():
        saved = read(path)
        if any(manifest.get(key) != value for key, value in saved.items()):
            raise ValueError("DRB run configuration differs from saved manifest")
    atomic_json(path, manifest)


def pending_case(output, case_id):
    attempt = output / f"drb_{case_id}" / "attempt-0001"
    if (attempt / "worker_result.json").is_file():
        # Older runners wrote the completion marker just before the status file.
        if not all((attempt / name).is_file() for name in ("report.md", "research_result.json")):
            raise ValueError(f"Incomplete checkpoint for DRB task {case_id}")
        return False
    if attempt.exists():
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        attempt.rename(attempt.with_name(f"interrupted-{stamp}"))
    return True
