import json

import pytest

from evals.rag.protocol import canonical_sha256
from evals.reports_acceptance import pbc_clarity as clarity


def test_frozen_two_case_suite_and_pair_order():
    suite = clarity.load_suite()
    assert [case["id"] for case in suite["cases"]] == [
        "pbc_column_headings",
        "pbc_column_one_methods",
    ]
    assert [(case["id"], variant) for case, variant in clarity.questions(suite)] == [
        ("pbc_column_headings", "ordinary"),
        ("pbc_column_headings", "experimental"),
        ("pbc_column_one_methods", "ordinary"),
        ("pbc_column_one_methods", "experimental"),
    ]


def test_reference_hash_and_scoped_corpus_are_checked(monkeypatch, tmp_path):
    corpus = [
        {"chunk_id": "a", "document_sha256": "target", "content_sha256": "hash-a"},
        {"chunk_id": "b", "document_sha256": "target", "content_sha256": "hash-b"},
    ]
    record = tmp_path / "record.json"
    record.write_text(
        json.dumps({"final": {"corpus_sha256": {"金融行业": canonical_sha256(corpus)}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(clarity, "E416", record)
    suite = {
        "document_sha256": "target",
        "cases": [
            {"reference_chunk_id": "a", "reference_content_sha256": "hash-a"},
            {"reference_chunk_id": "b", "reference_content_sha256": "hash-b"},
        ],
    }
    assert set(clarity.validate_corpus(suite, corpus)) == {"a", "b"}
    with pytest.raises(ValueError, match="frozen_source_reference_changed"):
        clarity.validate_corpus(
            {**suite, "cases": [{**suite["cases"][0], "reference_content_sha256": "wrong"}]},
            corpus,
        )
    with pytest.raises(ValueError, match="pbc_finance_corpus_changed"):
        clarity.validate_corpus(
            suite,
            [*corpus, {"chunk_id": "c", "document_sha256": "target", "content_sha256": "hash-c"}],
        )
