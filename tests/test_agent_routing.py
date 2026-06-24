"""Tests for deterministic source-routing hints."""

from app.agent.main_agent import _requires_knowledge_base_first


def test_document_content_query_prefers_knowledge_base():
    assert _requires_knowledge_base_first("2026数字人电商直播白皮书里提到的市场份额、营收内容是什么")


def test_general_market_query_does_not_force_knowledge_base():
    assert not _requires_knowledge_base_first("请搜索2026年数字人电商直播市场最新趋势")
