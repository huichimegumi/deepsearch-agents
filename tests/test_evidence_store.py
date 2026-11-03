import json

import pytest

from app.research.evidence_store import EvidenceStore, count_tokens


def record(key, text):
    return {
        "evidence_id": key,
        "source": "sql",
        "locator": "fixture:" + key,
        "content": {"name": text},
        "metadata": {"query": "SELECT name FROM items"},
    }


def test_late_relevant_evidence_can_replace_earlier_bulk_and_remains_durable(tmp_path):
    store = EvidenceStore(tmp_path)
    rows = [record(f"old_{i}", "unrelated " * 40) for i in range(30)]
    store.add(rows, "s0")
    store.add([record("late", "Kyoto target limit 17")], "s1")
    selected = store.select("Kyoto target limit", max_tokens=350)
    assert "late" in {r["evidence_id"] for r in selected["evidence"]}
    assert count_tokens(selected) <= 350
    assert len(store.records) == 31
    assert len(json.loads((tmp_path / "evidence/index.json").read_text())["records"]) == 31
    assert store.read(["old_0"])[0]["content"]["name"] == rows[0]["content"]["name"]
    with pytest.raises(ValueError, match="evidence_identity_collision"):
        store.add([record("late", "changed source")], "s2")


def test_excerpt_is_marked_and_original_is_not_overwritten(tmp_path):
    store = EvidenceStore(tmp_path)
    raw = {
        "evidence_id": "web1",
        "source": "web",
        "locator": "https://example.org",
        "content": "context " * 2000 + "Kyoto",
    }
    store.add([raw], "s0")
    view = store.select("Kyoto")["evidence"][0]
    assert view["excerpt"]["full_record_available"]
    assert view["content"] in raw["content"]
    assert store.read(["web1"])[0]["content"] == raw["content"]
