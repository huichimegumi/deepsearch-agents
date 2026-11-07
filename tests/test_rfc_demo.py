from types import SimpleNamespace

import pytest

from app.research import rfc_demo


def test_index_marks_body_sections_without_inheriting_reference_section():
    raw = "   4.1.  Cache keys\n\n4.1.  Cache keys\n\n   Passage\n\nAppendix A.  Extra\n"
    marked = rfc_demo.index_text(raw)
    assert marked == raw.replace("\n4.1.  ", "\n# 4.1. ", 1).replace(
        "\nAppendix", "\n# Appendix", 1
    )
    assert not rfc_demo.SECTION.match("Appendix A. Extra")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("Caches use the field to choose a stored response. [1]", "answered"),
        ("First claim. [1] Second claim. [1].", "answered"),
        ("A cited claim. [1] An uncited tail.", "failed"),
        ("A claim about the wrong excerpt. [2]", "failed"),
        ("A claim without evidence.", "failed"),
        ("A claim [spoof](https://example.org). [1]", "failed"),
        ("INSUFFICIENT_EVIDENCE", "insufficient_evidence"),
        ("INSUFFICIENT_EVIDENCE.", "insufficient_evidence"),
    ],
)
async def test_writer_can_only_link_retrieved_sources(tmp_path, monkeypatch, reply, expected):
    location = "https://www.rfc-editor.org/rfc/rfc9111.html#section-4.1"
    record = rfc_demo.EvidenceRecord.create(
        source=rfc_demo.EvidenceSource.LOCAL_DOCUMENT,
        locator=location,
        content="The selected response depends on the request header fields.",
        metadata={"title": "RFC 9111 §4.1"},
    ).to_dict()
    monkeypatch.setattr(rfc_demo, "_retrieve", lambda _question: [record])
    calls = []

    class Writer:
        def bind(self, **_kwargs):
            return self

        async def ainvoke(self, messages):
            calls.append(messages)
            assert record["content"] in messages[-1]["content"]
            assert location not in messages[-1]["content"]
            return SimpleNamespace(content=reply, usage_metadata=None, response_metadata={})

    result = await rfc_demo.run_rfc_qa("What does Vary do?", tmp_path, model=Writer())
    assert len(calls) == 1
    assert result["status"] == expected
    assert (location in result["answer"]) == (expected == "answered")
    assert "example.org" not in result["answer"]
    assert list(tmp_path.glob("*/evidence/index.json"))
    assert list(tmp_path.glob("*/result.json"))


@pytest.mark.asyncio
async def test_empty_retrieval_does_not_request_a_model(tmp_path, monkeypatch):
    monkeypatch.setattr(rfc_demo, "_retrieve", lambda _question: [])
    monkeypatch.setattr(rfc_demo, "get_model", lambda: pytest.fail("no evidence to send"))
    result = await rfc_demo.run_rfc_qa("Outside the corpus", tmp_path)
    assert result["status"] == "insufficient_evidence"
    assert result["requests"] == 0
