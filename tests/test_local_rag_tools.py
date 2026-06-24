"""Tests for local RAG answer generation."""

from unittest.mock import patch

from app.rag.retrieval import RetrievedChunk
from app.tools.local_rag_tools import _answer


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
