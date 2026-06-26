"""Tests for local RAG answer generation."""

from unittest.mock import patch

from app.rag.retrieval import RetrievedChunk
from app.tools.local_rag_tools import _answer, _limit_hits_for_answer


class FakeResponse:
    content = "本地知识库答案"


class FakeModel:
    def invoke(self, messages):
        assert "检索片段" in messages[0]["content"]
        return FakeResponse()


def test_answer_uses_lazy_model_factory():
    hits = [
        RetrievedChunk(
            chunk_id="chunk-1",
            content="营收相关内容",
            filename="2026数字人电商直播白皮书.pdf",
            page_start=11,
            page_end=11,
            section=None,
            score=1.0,
        )
    ]
    with patch("app.agent.llm.get_model", return_value=FakeModel()):
        assert _answer("营收情况如何？", hits) == "本地知识库答案"


def test_limit_hits_for_answer_caps_hits_and_context(monkeypatch):
    monkeypatch.setenv("RAG_ANSWER_MAX_HITS", "2")
    monkeypatch.setenv("RAG_ANSWER_MAX_CONTEXT_CHARS", "180")

    from app.config import get_settings

    get_settings.cache_clear()
    hits = [
        RetrievedChunk(
            chunk_id=f"chunk-{index}",
            content="很长的片段内容" * 20,
            filename=f"doc-{index}.pdf",
            page_start=index,
            page_end=index,
            section=None,
            score=float(index),
        )
        for index in range(1, 4)
    ]

    limited_hits, metadata = _limit_hits_for_answer(hits)

    assert len(limited_hits) <= 2
    assert metadata["max_answer_hits"] == 2
    assert metadata["max_context_chars"] == 180
    assert metadata["context_chars"] <= 220
    assert metadata["truncated"] is True
    get_settings.cache_clear()
