"""统一多后端网络搜索工具。

文件名暂时保留为 tavily_tool.py，避免已有导入路径失效；实际搜索能力已经
扩展为 Tavily、DuckDuckGo、Perplexity 和 SearXNG，并支持自动降级与聚合。
"""

import os
from typing import Literal

from langchain_core.tools import tool

from app.agent.runtime import get_research_budget, get_research_trace
from app.api.audit import write_audit_event
from app.api.monitor import monitor
from app.search.models import SearchRequest
from app.search.service import get_search_service


@tool
def research_search(
    queries: list[str],
    backend: Literal[
        "auto",
        "advanced",
        "tavily",
        "duckduckgo",
        "perplexity",
        "searxng",
    ] = "auto",
    topic: Literal["news", "finance", "general"] = "general",
    max_results: int | None = None,
    fetch_full_page: bool = False,
) -> dict:
    """从多个公开网络来源检索信息。

    复杂问题应在一次调用中传入 2 至 5 个互补查询。auto 模式会按配置顺序
    自动降级，advanced 模式会并发聚合所有可用后端。工具仅查询公开网络，
    不用于业务数据库或私有知识库。

    :param queries: 一至五个互补的搜索关键词或自然语言问题
    :param backend: 搜索模式或指定后端
    :param topic: 搜索主题，可选 news、finance、general
    :param max_results: 去重后最多返回的结果数
    :param fetch_full_page: 是否抓取公开网页正文，默认只使用搜索摘要
    :return: 包含 results、answer、backend 和 notices 的统一结构
    """
    requested_backend = backend
    budget = get_research_budget()
    trace = get_research_trace()
    if budget is not None:
        accepted_query_count = budget.take_search_queries(len(queries))
        queries = queries[:accepted_query_count]
        if not queries:
            return {
                "queries": [],
                "backend": backend,
                "results": [],
                "answer": None,
                "notices": ["本次研究已达到搜索查询预算，停止继续搜索"],
            }
    configured_backend = os.getenv("SEARCH_BACKEND", "auto").strip().lower()
    if backend == "auto" and configured_backend in {
        "auto",
        "advanced",
        "tavily",
        "duckduckgo",
        "perplexity",
        "searxng",
    }:
        backend = configured_backend

    resolved_max_results = max_results or int(os.getenv("SEARCH_MAX_RESULTS", "8"))
    if fetch_full_page and budget is not None:
        remaining_pages = budget.limits.max_fetched_pages - budget.fetched_pages_used
        resolved_max_results = min(resolved_max_results, max(0, remaining_pages))
        if resolved_max_results <= 0:
            fetch_full_page = False
    monitor.report_tool(
        tool_name="多源网络搜索工具",
        args={
            "queries": queries,
            "requested_backend": requested_backend,
            "configured_backend": backend,
            "topic": topic,
            "max_results": resolved_max_results,
            "fetch_full_page": fetch_full_page,
        },
    )
    response = get_search_service().search(
        SearchRequest(
            queries=queries,
            backend=backend,
            topic=topic,
            max_results=resolved_max_results,
            fetch_full_page=fetch_full_page,
        )
    )
    response_dict = response.to_dict()
    fetched_pages = sum(1 for item in response_dict.get("results", []) if item.get("raw_content"))
    if budget is not None:
        budget.take_fetched_pages(fetched_pages)
    if trace is not None:
        trace.record_search(queries, response_dict.get("results", []))
    write_audit_event(
        "search_result",
        {
            "queries": queries,
            "requested_backend": requested_backend,
            "resolved_backend": response_dict.get("backend"),
            "result_count": len(response_dict.get("results", [])),
            "notices": response_dict.get("notices", []),
            "top_results": [
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "published_date": item.get("published_date"),
                }
                for item in response_dict.get("results", [])[:5]
                if isinstance(item, dict)
            ],
        },
    )
    return response_dict


# 保留旧名称，已有代码仍可通过 internet_search.invoke(...) 调用新工具。
internet_search = research_search
