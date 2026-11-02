"""No-assets fault injection for interrupted request ledgers and worker recovery."""

import json

from app.research.request_budget import admit_request, usage
from evals import run_v4


def test_partial_ledger_tail_is_repaired_before_next_admission(tmp_path, monkeypatch):
    path = tmp_path / "ledger.jsonl"
    path.write_text('{"event":"admitted","reserved_tokens":5}\n{"event":"admit')
    monkeypatch.setenv("EVAL_LEDGER_PATH", str(path))
    monkeypatch.setenv("EVAL_MAX_REQUESTS", "4")
    monkeypatch.setenv("EVAL_MAX_RESERVED_TOKENS", "10000")
    admit_request({"messages": [{"role": "user", "content": "hello"}], "max_tokens": 10})
    assert usage(path)["requests"] == 2
    assert usage(path)["reserved_tokens"] > 5


def _run_fixture(tmp_path, monkeypatch):
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    (data / "dev.sqlite").write_bytes(b"test database hash only")
    (tasks / "dev.public.json").write_text(
        json.dumps([{"id": "case_0", "question": "test", "sources": ["sql"], "split": "dev"}])
    )
    lock = tmp_path / "lock.json"
    lock.write_text("{}")
    monkeypatch.setattr(run_v4, "TASKS", tasks)
    monkeypatch.setattr(run_v4, "DATA", data)
    monkeypatch.setattr(run_v4, "LOCK", lock)
    monkeypatch.setattr(run_v4, "source_hash", lambda: "frozen")
    monkeypatch.setattr(run_v4, "verify_sources", lambda: None)

    def unexpected(*args, **kwargs):
        raise AssertionError("Paid worker must not be repeated")

    monkeypatch.setattr(run_v4, "supervise", unexpected)
    output = tmp_path / "run"
    attempt = output / "case_0/attempt-0001"
    attempt.mkdir(parents=True)
    (attempt / "model_requests.jsonl").write_text('{"event":"admitted","reserved_tokens":50}\n')
    return output, attempt


def test_interrupted_worker_retains_spend_without_automatic_repeat(tmp_path, monkeypatch):
    output, _ = _run_fixture(tmp_path, monkeypatch)
    run_v4.run("dev", "bounded", output)
    row = json.loads((output / "results.json").read_text())[0]
    assert row["status"] == "interrupted"
    assert row["model_reservations"] == {"requests": 1, "reserved_tokens": 50}
    run_v4.run("dev", "bounded", output)
    assert len(json.loads((output / "results.json").read_text())) == 1


def test_completed_worker_before_parent_checkpoint_is_reused(tmp_path, monkeypatch):
    output, attempt = _run_fixture(tmp_path, monkeypatch)
    (attempt / "worker_result.json").write_text(
        json.dumps({"status": "completed", "elapsed_seconds": 1})
    )
    run_v4.run("dev", "bounded", output)
    row = json.loads((output / "results.json").read_text())[0]
    assert row["status"] == "completed"
    assert row["model_reservations"]["reserved_tokens"] == 50
