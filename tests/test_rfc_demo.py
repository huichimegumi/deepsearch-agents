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

    result = await rfc_demo.run_rfc_qa(
        "What does Vary do?", tmp_path, model=Writer(), retry_format=False
    )
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


@pytest.mark.asyncio
async def test_sources_only_returns_literal_excerpt_and_never_creates_writer(tmp_path, monkeypatch):
    location = "https://www.rfc-editor.org/rfc/rfc9111.html#section-4.1"
    record = rfc_demo.EvidenceRecord.create(
        source=rfc_demo.EvidenceSource.LOCAL_DOCUMENT,
        locator=location,
        content="See [example] (literal source text).",
        metadata={"title": "RFC 9111 §4.1"},
    ).to_dict()
    monkeypatch.setattr(
        rfc_demo, "get_model", lambda: pytest.fail("source mode must not create writer")
    )
    assert rfc_demo.SECTION_REF.findall("RFC 9111 section 4.1.") == [("9111", "4.1")]
    another = rfc_demo.EvidenceRecord.create(
        source=rfc_demo.EvidenceSource.LOCAL_DOCUMENT,
        locator="https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.1",
        content="An additional section.",
        metadata={"title": "RFC 9110 §9.2.1"},
    ).to_dict()
    result = await rfc_demo.run_rfc_qa(
        "Locate RFC 9111 section 4.1 and RFC 9110 section 9.2.1",
        tmp_path,
        sources_only=True,
        prepared_evidence=[record] * 5 + [another],
    )
    assert result["status"] == "evidence_found"
    assert result["requests"] == 0
    assert result["evidence_ids"] == [record["evidence_id"], another["evidence_id"]]
    assert f"[RFC 9111 §4.1]({location})" in result["answer"]
    assert "\n\n    See [example] (literal source text)." in result["answer"]


@pytest.mark.asyncio
@pytest.mark.parametrize("second", ["A supported fact. [1]", "A bad citation. [2]"])
async def test_retry_format_uses_same_evidence_and_stops(tmp_path, second):
    record = rfc_demo.EvidenceRecord.create(
        source=rfc_demo.EvidenceSource.LOCAL_DOCUMENT,
        locator="https://www.rfc-editor.org/rfc/rfc9110.html#section-8.6",
        content="A supported fact.",
        metadata={"title": "RFC 9110 §8.6"},
    ).to_dict()
    calls = []
    replies = iter(["A bad citation. [2]", second])

    class Writer:
        def bind(self, **_kwargs):
            return self

        async def ainvoke(self, messages):
            calls.append(messages)
            return SimpleNamespace(
                content=next(replies),
                usage_metadata={"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
                response_metadata={},
            )

    result = await rfc_demo.run_rfc_qa(
        "Question", tmp_path, model=Writer(), prepared_evidence=[record]
    )
    assert result["status"] == ("answered" if "[1]" in second else "failed")
    assert calls[0] == calls[1][:2]
    assert len(calls) == 2
    assert result["model_usage"]["total_tokens"] == 6
    assert result["writer_attempts"][0]["format_error"] == "unknown_rfc_citation"


def test_rfc_bm25_rare_term_and_deterministic_ties():
    rows = [
        ("z", "http request cache"),
        ("a", "http request cache"),
        ("b", "http etag request"),
        ("c", "http field request"),
    ]
    result = rfc_demo._bm25_rank("HTTP etag request", rows, 3)
    assert [key for key, _ in result] == ["b", "a", "c"]
    assert rfc_demo._bm25_rank("absent", rows, 3) == []
