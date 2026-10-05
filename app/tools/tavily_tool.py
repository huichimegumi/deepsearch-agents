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
from app.research.evidence import web_results_to_evidence
from app.search.models import SearchRequest, canonicalize_web_url
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
    :param fetch_full_page: 是否抓取公开网页正文；只有成功抓取的正文会生成 Web Evidence
    :return: 包含搜索候选和已抓取网页 Evidence 的统一结构
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
                "evidence_records": [],
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
    trace_results = [result.to_dict() for result in response.results]
    evidence_records = web_results_to_evidence(response.results)
    evidence_by_url = {record.locator: record for record in evidence_records}
    for item in response_dict.get("results", []):
        record = evidence_by_url.get(canonicalize_web_url(str(item.get("url") or "")))
        item["evidence_id"] = record.evidence_id if record is not None else None
        item["evidence_status"] = "FETCHED" if record is not None else "CANDIDATE_ONLY"
        # Fetched text is emitted once in evidence_records to avoid doubling model context.
        item.pop("raw_content", None)
    response_dict["evidence_records"] = [record.to_dict() for record in evidence_records]
    response_dict["answer_evidence_status"] = (
        "CANDIDATE_ONLY" if response_dict.get("answer") else None
    )
    if response.results and not evidence_records:
        response_dict.setdefault("notices", []).append(
            "搜索结果仅为候选；没有成功抓取的网页正文，因此未生成 Web Evidence"
        )
    fetched_pages = sum(1 for item in trace_results if item.get("raw_content"))
    if budget is not None:
        budget.take_fetched_pages(fetched_pages)
    if trace is not None:
        trace.record_search(queries, trace_results)
        trace.record_evidence(evidence_records)
    write_audit_event(
        "search_result",
        {
            "queries": queries,
            "requested_backend": requested_backend,
            "resolved_backend": response_dict.get("backend"),
            "result_count": len(response_dict.get("results", [])),
            "evidence_ids": [record.evidence_id for record in evidence_records],
            "evidence_count": len(evidence_records),
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
