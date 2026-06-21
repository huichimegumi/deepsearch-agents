"""SearXNG 搜索后端。"""

import os

import requests

from app.search.base import SearchProvider, SearchProviderError
from app.search.models import SearchResult, SearchTopic


class SearxNGProvider(SearchProvider):
    """调用自托管 SearXNG 的 JSON 搜索接口。"""

    name = "searxng"

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    def is_available(self) -> bool:
        return bool(os.getenv("SEARXNG_URL"))

    def search(
        self,
        query: str,
        *,
        topic: SearchTopic,
        max_results: int,
    ) -> tuple[list[SearchResult], str | None]:
        if not self.is_available():
            raise SearchProviderError("SearXNG 未配置 SEARXNG_URL")

        categories = "news" if topic == "news" else "general"
        try:
            response = requests.get(
                f"{os.environ['SEARXNG_URL'].rstrip('/')}/search",
                params={"q": query, "format": "json", "categories": categories},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise SearchProviderError(f"SearXNG 请求失败: {exc}") from exc

        results = [
            SearchResult(
                title=str(item.get("title") or item.get("url") or ""),
                url=str(item.get("url") or ""),
                content=str(item.get("content") or ""),
                published_date=str(item.get("publishedDate") or ""),
                score=float(item.get("score") or max(0.0, 1.0 - index * 0.08)),
                source_backend=self.name,
                matched_queries=[query],
            )
            for index, item in enumerate(payload.get("results", [])[:max_results])
            if item.get("url")
        ]
        return results, None
