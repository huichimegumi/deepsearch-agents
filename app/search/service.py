"""多后端搜索调度、降级和结果融合。"""

import ipaddress
import os
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from threading import Lock
from time import monotonic
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

from app.api.monitor import monitor
from app.search.base import SearchProvider
from app.search.models import SearchRequest, SearchResponse, SearchResult, SearchTopic
from app.search.providers import (
    DuckDuckGoProvider,
    PerplexityProvider,
    SearxNGProvider,
    TavilyProvider,
)

TRACKING_PARAMETERS = {"fbclid", "gclid", "ref", "source"}
MAX_QUERIES = 5
MAX_RESULTS = 20


class _TextExtractor(HTMLParser):
    """从 HTML 中提取适合送入模型的可见文本。"""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            text = " ".join(data.split())
            if text:
                self.parts.append(text)


class SearchService:
    """对搜索 Agent 提供稳定、可降级的统一搜索能力。"""

    def __init__(
        self,
        providers: dict[str, SearchProvider] | None = None,
        *,
        timeout: float | None = None,
        max_content_chars: int | None = None,
    ) -> None:
        self.providers = providers or {
            "tavily": TavilyProvider(),
            "duckduckgo": DuckDuckGoProvider(),
            "perplexity": PerplexityProvider(),
            "searxng": SearxNGProvider(),
        }
        self.timeout = timeout or float(os.getenv("SEARCH_TIMEOUT", "15"))
        self.max_content_chars = max_content_chars or int(
            os.getenv("SEARCH_MAX_CONTENT_CHARS", "8000")
        )

    def search(self, request: SearchRequest) -> SearchResponse:
        """执行搜索，并将所有错误收敛为可读提示。"""
        queries = self._clean_queries(request.queries)
        if not queries:
            return SearchResponse([], request.backend, notices=["没有可执行的搜索查询"])

        max_results = min(max(1, request.max_results), MAX_RESULTS)
        provider_names = self._resolve_providers(request.backend)
        if not provider_names:
            return SearchResponse(
                queries,
                request.backend,
                notices=["没有可用的搜索后端，请检查依赖和环境变量"],
            )

        monitor.report_search(
            stage="start",
            data={
                "queries": queries,
                "requested_backend": request.backend,
                "providers": provider_names,
                "max_results": max_results,
            },
        )

        started_at = monotonic()
        results: list[SearchResult] = []
        answers: list[str] = []
        notices: list[str] = []
        used_providers: set[str] = set()

        # advanced 聚合全部后端；auto 对每个查询按配置顺序逐个降级。
        if request.backend == "auto":
            jobs = [(query, None) for query in queries]
        else:
            jobs = [(query, provider_name) for query in queries for provider_name in provider_names]
        workers = min(8, max(1, len(jobs)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {}
            for query, provider_name in jobs:
                if provider_name is None:
                    future = executor.submit(
                        self._search_with_fallback,
                        query,
                        provider_names,
                        request.topic,
                        max_results,
                    )
                else:
                    future = executor.submit(
                        self.providers[provider_name].search,
                        query,
                        topic=request.topic,
                        max_results=max_results,
                    )
                future_map[future] = (query, provider_name)

            for future in as_completed(future_map):
                query, provider_name = future_map[future]
                try:
                    if provider_name is None:
                        provider_results, answer, resolved, fallback_notices = future.result()
                        notices.extend(fallback_notices)
                        used_providers.add(resolved)
                    else:
                        provider_results, answer = future.result()
                        used_providers.add(provider_name)
                    results.extend(provider_results)
                    if answer and answer not in answers:
                        answers.append(answer)
                except Exception as exc:
                    notices.append(f"{provider_name or 'auto'} 查询“{query}”失败: {exc}")

        merged = self._merge_results(results, max_results)
        if request.fetch_full_page and merged:
            self._fetch_full_pages(merged)

        resolved_backend = "+".join(sorted(used_providers)) or request.backend
        monitor.report_search(
            stage="complete",
            data={
                "requested_backend": request.backend,
                "resolved_backend": resolved_backend,
                "result_count": len(merged),
                "notice_count": len(notices),
                "elapsed_ms": round((monotonic() - started_at) * 1000),
            },
        )
        return SearchResponse(
            queries=queries,
            backend=resolved_backend,
            results=merged,
            answer="\n\n".join(answers) or None,
            notices=notices,
        )

    def _resolve_providers(self, backend: str) -> list[str]:
        available = [name for name, provider in self.providers.items() if provider.is_available()]
        if backend == "advanced":
            return available
        if backend not in {"auto", "advanced"}:
            return [backend] if backend in available else []

        configured = os.getenv("SEARCH_BACKEND_ORDER", "tavily,searxng,duckduckgo,perplexity")
        ordered = [name.strip() for name in configured.split(",") if name.strip() in available]
        return ordered

    def _search_with_fallback(
        self,
        query: str,
        provider_names: list[str],
        topic: SearchTopic,
        max_results: int,
    ) -> tuple[list[SearchResult], str | None, str, list[str]]:
        """按顺序搜索，失败或无结果时自动尝试下一后端。"""
        notices: list[str] = []
        for provider_name in provider_names:
            try:
                results, answer = self.providers[provider_name].search(
                    query,
                    topic=topic,
                    max_results=max_results,
                )
                if results:
                    if notices:
                        notices.append(f"已降级到 {provider_name} 并获得结果")
                    return results, answer, provider_name, notices
                notices.append(f"{provider_name} 未返回结果，继续尝试下一后端")
            except Exception as exc:
                notices.append(f"{provider_name} 失败，继续降级: {exc}")
        raise RuntimeError("；".join(notices) or "所有搜索后端均不可用")

    @staticmethod
    def _clean_queries(queries: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for query in queries:
            value = " ".join(str(query).split()).strip()
            key = value.casefold()
            if value and key not in seen:
                cleaned.append(value)
                seen.add(key)
            if len(cleaned) >= MAX_QUERIES:
                break
        return cleaned

    @staticmethod
    def _canonical_url(url: str) -> str:
        parts = urlsplit(url.strip())
        filtered_query = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMETERS
        ]
        path = parts.path.rstrip("/") or "/"
        return urlunsplit(
            (parts.scheme.lower(), parts.netloc.lower(), path, urlencode(filtered_query), "")
        )

    def _merge_results(self, results: list[SearchResult], limit: int) -> list[SearchResult]:
        unique: dict[str, SearchResult] = {}
        provider_weight = {"tavily": 0.10, "perplexity": 0.08, "searxng": 0.05}
        for result in results:
            canonical = self._canonical_url(result.url)
            if not canonical.startswith(("http://", "https://")):
                continue
            result.url = canonical
            existing = unique.get(canonical)
            if existing is None:
                unique[canonical] = result
                continue
            existing.score = max(existing.score, result.score)
            existing.content = max((existing.content, result.content), key=len)
            existing.published_date = existing.published_date or result.published_date
            existing.matched_queries = list(
                dict.fromkeys(existing.matched_queries + result.matched_queries)
            )
            backends = set(existing.source_backend.split("+")) | {result.source_backend}
            existing.source_backend = "+".join(sorted(backends))

        for result in unique.values():
            query_bonus = min(0.20, 0.05 * (len(result.matched_queries) - 1))
            backend_bonus = max(
                (provider_weight.get(name, 0.0) for name in result.source_backend.split("+")),
                default=0.0,
            )
            result.score = round(result.score + query_bonus + backend_bonus, 4)

        ranked = sorted(unique.values(), key=lambda item: (-item.score, item.url))
        selected: list[SearchResult] = []
        domain_counts: dict[str, int] = {}
        for result in ranked:
            domain = urlsplit(result.url).netloc
            if domain_counts.get(domain, 0) >= 2:
                continue
            selected.append(result)
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
            if len(selected) >= limit:
                break
        return selected

    def _fetch_full_pages(self, results: list[SearchResult]) -> None:
        with ThreadPoolExecutor(max_workers=min(5, len(results))) as executor:
            future_map = {
                executor.submit(self._fetch_page, result.url): result for result in results
            }
            for future in as_completed(future_map):
                result = future_map[future]
                try:
                    result.raw_content = future.result()
                except Exception:
                    # 正文抓取属于增强能力，失败时仍保留搜索摘要。
                    result.raw_content = ""

    def _fetch_page(self, url: str) -> str:
        if not self._is_public_url(url):
            return ""
        response = requests.get(
            url,
            timeout=self.timeout,
            headers={"User-Agent": "DeepSearchAgents/0.1 (+research crawler)"},
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "html" not in content_type and "text/plain" not in content_type:
            return ""
        parser = _TextExtractor()
        parser.feed(response.text[: self.max_content_chars * 4])
        return "\n".join(parser.parts)[: self.max_content_chars]

    @staticmethod
    def _is_public_url(url: str) -> bool:
        """阻止全文抓取访问本机、内网和非 HTTP 地址。"""
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            return False
        try:
            addresses = socket.getaddrinfo(parts.hostname, parts.port or 443)
            for address in addresses:
                ip = ipaddress.ip_address(address[4][0])
                if not ip.is_global:
                    return False
        except (OSError, ValueError):
            return False
        return True


_service: SearchService | None = None
_service_lock = Lock()


def get_search_service() -> SearchService:
    """获取进程内复用的搜索服务实例。"""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = SearchService()
    return _service
