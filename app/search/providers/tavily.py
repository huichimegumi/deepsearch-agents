"""Tavily 搜索后端。"""

import os

from app.search.base import SearchProvider, SearchProviderError
from app.search.models import SearchResult, SearchTopic


class TavilyProvider(SearchProvider):
    """通过 Tavily API 获取结构化网页结果。"""

    name = "tavily"

    def __init__(self) -> None:
        self._client = None

    def is_available(self) -> bool:
        return bool(os.getenv("TAVILY_API_KEY"))

    def search(
        self,
        query: str,
        *,
        topic: SearchTopic,
        max_results: int,
    ) -> tuple[list[SearchResult], str | None]:
        if not self.is_available():
            raise SearchProviderError("Tavily 未配置 TAVILY_API_KEY")

        try:
            if self._client is None:
                from tavily import TavilyClient

                self._client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
            payload = self._client.search(
                query=query,
                topic=topic,
                max_results=max_results,
                include_answer=True,
                include_raw_content=False,
            )
        except Exception as exc:
            raise SearchProviderError(f"Tavily 请求失败: {exc}") from exc

        results = [
            SearchResult(
                title=str(item.get("title") or item.get("url") or ""),
                url=str(item.get("url") or ""),
                content=str(item.get("content") or ""),
                published_date=str(item.get("published_date") or ""),
                score=float(item.get("score") or 0.0),
                source_backend=self.name,
                matched_queries=[query],
            )
            for item in payload.get("results", [])
            if item.get("url")
        ]
        return results, payload.get("answer")
