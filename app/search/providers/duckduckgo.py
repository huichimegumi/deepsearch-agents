"""DuckDuckGo 搜索后端。"""

from app.search.base import SearchProvider, SearchProviderError
from app.search.models import SearchResult, SearchTopic


class DuckDuckGoProvider(SearchProvider):
    """使用无需 API Key 的 DuckDuckGo 作为默认和兜底后端。"""

    name = "duckduckgo"

    def is_available(self) -> bool:
        try:
            import ddgs  # noqa: F401
        except ImportError:
            return False
        return True

    def search(
        self,
        query: str,
        *,
        topic: SearchTopic,
        max_results: int,
    ) -> tuple[list[SearchResult], str | None]:
        try:
            from ddgs import DDGS

            client = DDGS()
            if topic == "news":
                rows = list(client.news(query, max_results=max_results))
            else:
                rows = list(client.text(query, max_results=max_results))
        except Exception as exc:
            raise SearchProviderError(f"DuckDuckGo 请求失败: {exc}") from exc

        results = []
        for index, item in enumerate(rows):
            url = str(item.get("href") or item.get("url") or "")
            if not url:
                continue
            results.append(
                SearchResult(
                    title=str(item.get("title") or url),
                    url=url,
                    content=str(item.get("body") or item.get("content") or ""),
                    published_date=str(item.get("date") or ""),
                    score=max(0.0, 1.0 - index * 0.08),
                    source_backend=self.name,
                    matched_queries=[query],
                )
            )
        return results, None
