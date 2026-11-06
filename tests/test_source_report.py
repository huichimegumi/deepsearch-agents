import json

import pytest

from app.research.evidence_store import EvidenceStore
from app.research.source_report import SourceExcerpt, excerpt_valid, write_source_report


def store(tmp_path, *, complete=True):
    evidence = EvidenceStore(tmp_path)
    evidence.add(
        [
            {
                "evidence_id": "row",
                "source": "sql",
                "locator": "fixture:query",
                "content": {"value": 42},
                "metadata": {"query": "SELECT value FROM records", "truncated": not complete},
            },
            {
                "evidence_id": "doc",
                "source": "local_document",
                "locator": "fixture:document",
                "content": "The opening year is not known. Records were published in 2010.",
                "metadata": {},
            },
        ],
        "observed",
    )
    return evidence


def test_excerpt_rejects_paraphrase_clipped_negation_and_unseen_text():
    text = "The answer is not 42. Another observation exists."
    assert excerpt_valid("The answer is not 42.", text)
    assert not excerpt_valid("42.", text)
    assert not excerpt_valid("The answer is 42.", text)
    assert not excerpt_valid("Another observation", text)
    assert not excerpt_valid("", text)


@pytest.mark.asyncio
async def test_backend_binds_source_and_preserves_tables_without_model_references(tmp_path):
    evidence = store(tmp_path / "evidence")

    class Model:
        def with_structured_output(self, schema, **kwargs):
            assert schema is SourceExcerpt
            return self

        def bind(self, **kwargs):
            return self

        async def ainvoke(self, messages):
            payload = json.loads(messages[-1]["content"])
            assert set(payload) == {"question", "source_text"}
            assert "evidence_id" not in payload
            return {"parsed": SourceExcerpt(quote="The opening year is not known."), "raw": None}

    report, delivery = await write_source_report(
        "Find opening year", evidence, tmp_path / "report", model=Model()
    )
    assert report.claims[0].evidence_ids == ["doc"]
    assert "not known" in report.claims[0].text
    assert report.tables[0].rows == [[42]]
    assert report.answerability == "partial" and not delivery["coverage_evaluated"]
    assert not delivery["protocol_errors"]


@pytest.mark.asyncio
async def test_failed_excerpt_keeps_valid_tables_and_excludes_truncated_results(tmp_path):
    class Model:
        def with_structured_output(self, schema, **kwargs):
            return self

        def bind(self, **kwargs):
            return self

        async def ainvoke(self, messages):
            return {"parsed": SourceExcerpt(quote="The opening year is 2010."), "raw": None}

    for complete in (True, False):
        evidence = store(tmp_path / f"evidence-{complete}", complete=complete)
        report, delivery = await write_source_report(
            "Find year", evidence, tmp_path / f"report-{complete}", model=Model()
        )
        assert not report.claims and delivery["protocol_errors"]
        assert len(report.tables) == int(complete)
        assert report.answerability == ("partial" if complete else "insufficient_evidence")


@pytest.mark.asyncio
async def test_explicit_abstention_is_valid_protocol_and_never_creates_a_fact(tmp_path):
    class Model:
        def with_structured_output(self, schema, **kwargs):
            return self

        def bind(self, **kwargs):
            return self

        async def ainvoke(self, messages):
            return {"parsed": SourceExcerpt(quote=""), "raw": None}

    report, delivery = await write_source_report(
        "Unsupported question", store(tmp_path / "evidence"), tmp_path / "report", model=Model()
    )
    assert delivery["excerpt_abstained"] and not delivery["excerpt_delivered"]
    assert not delivery["protocol_errors"] and not report.claims
    assert report.answerability == "partial" and report.tables
