"""Perplexity 搜索后端。"""

import os

import requests

from app.search.base import SearchProvider, SearchProviderError
from app.search.models import SearchResult, SearchTopic


class PerplexityProvider(SearchProvider):
    """通过 Perplexity Sonar 获取带引用的直接答案。"""

    name = "perplexity"
    endpoint = "https://api.perplexity.ai/chat/completions"

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    def is_available(self) -> bool:
        return bool(os.getenv("PERPLEXITY_API_KEY"))

    def search(
        self,
        query: str,
        *,
        topic: SearchTopic,
        max_results: int,
    ) -> tuple[list[SearchResult], str | None]:
        if not self.is_available():
            raise SearchProviderError("Perplexity 未配置 PERPLEXITY_API_KEY")

        try:
            response = requests.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {os.environ['PERPLEXITY_API_KEY']}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": os.getenv("PERPLEXITY_MODEL", "sonar"),
                    "messages": [{"role": "user", "content": query}],
                    "return_related_questions": False,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise SearchProviderError(f"Perplexity 请求失败: {exc}") from exc

        choices = payload.get("choices") or []
        answer = choices[0].get("message", {}).get("content") if choices else None
        rows = payload.get("search_results") or []
        if not rows:
            rows = [{"url": url, "title": url} for url in payload.get("citations") or []]

        results = [
            SearchResult(
                title=str(item.get("title") or item.get("url") or ""),
                url=str(item.get("url") or ""),
                content=str(item.get("snippet") or item.get("content") or ""),
                published_date=str(item.get("date") or item.get("published_date") or ""),
                score=max(0.0, 1.0 - index * 0.08),
                source_backend=self.name,
                matched_queries=[query],
            )
            for index, item in enumerate(rows[:max_results])
            if item.get("url")
        ]
        return results, answer
