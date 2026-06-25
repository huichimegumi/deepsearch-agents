"""统一搜索服务的单元测试。"""

import os
import time
import unittest
from unittest.mock import patch

from app.search.base import SearchProvider, SearchProviderError
from app.search.models import SearchRequest, SearchResult
from app.search.service import SearchService


class FakeProvider(SearchProvider):
    """无需访问网络的可控搜索后端。"""

    def __init__(
        self,
        name: str,
        results: list[SearchResult] | None = None,
        *,
        available: bool = True,
        error: str | None = None,
    ) -> None:
        self.name = name
        self.results = results or []
        self.available = available
        self.error = error
        self.calls: list[str] = []

    def is_available(self) -> bool:
        return self.available

    def search(self, query, *, topic, max_results):
        self.calls.append(query)
        if self.error:
            raise SearchProviderError(self.error)
        rows = []
        for item in self.results[:max_results]:
            rows.append(
                SearchResult(
                    title=item.title,
                    url=item.url,
                    content=item.content,
                    score=item.score,
                    source_backend=self.name,
                    matched_queries=[query],
                )
            )
        return rows, None


def make_result(url: str, *, score: float = 0.8, content: str = "摘要") -> SearchResult:
    return SearchResult(title=url, url=url, content=content, score=score)


class SlowProvider(FakeProvider):
    def __init__(self, name: str, delay: float) -> None:
        super().__init__(name)
        self.delay = delay

    def search(self, query, *, topic, max_results):
        self.calls.append(query)
        time.sleep(self.delay)
        return [], None


class SearchServiceTests(unittest.TestCase):
    @patch("app.search.service.monitor.report_search")
    def test_auto在首选后端失败后自动降级(self, _report_search):
        primary = FakeProvider("primary", error="临时超时")
        fallback = FakeProvider("fallback", [make_result("https://example.com/a")])
        service = SearchService({"primary": primary, "fallback": fallback})

        with patch.dict(os.environ, {"SEARCH_BACKEND_ORDER": "primary,fallback"}):
            response = service.search(SearchRequest(queries=["测试"], backend="auto"))

        self.assertEqual(response.backend, "fallback")
        self.assertEqual(len(response.results), 1)
        self.assertTrue(any("降级到 fallback" in notice for notice in response.notices))
        self.assertEqual(primary.calls, ["测试"])
        self.assertEqual(fallback.calls, ["测试"])

    @patch("app.search.service.monitor.report_search")
    def test_advanced聚合后规范网址并合并来源(self, _report_search):
        first = FakeProvider(
            "first",
            [make_result("https://Example.com/page/?utm_source=test", content="短摘要")],
        )
        second = FakeProvider(
            "second",
            [make_result("https://example.com/page", score=0.9, content="更完整的摘要内容")],
        )
        service = SearchService({"first": first, "second": second})

        response = service.search(SearchRequest(queries=["测试"], backend="advanced"))

        self.assertEqual(len(response.results), 1)
        result = response.results[0]
        self.assertEqual(result.url, "https://example.com/page")
        self.assertEqual(result.content, "更完整的摘要内容")
        self.assertEqual(result.source_backend, "first+second")

    @patch("app.search.service.monitor.report_search")
    def test_查询会去空去重并限制为五个(self, _report_search):
        provider = FakeProvider("only", [make_result("https://example.com/result")])
        service = SearchService({"only": provider})
        queries = ["  Alpha  ", "alpha", "", "Beta", "Gamma", "Delta", "Epsilon", "Zeta"]

        response = service.search(SearchRequest(queries=queries, backend="advanced"))

        self.assertEqual(response.queries, ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"])
        self.assertEqual(provider.calls, response.queries)

    def test_指定不可用后端返回提示而不抛异常(self):
        service = SearchService({"offline": FakeProvider("offline", available=False)})

        response = service.search(SearchRequest(queries=["测试"], backend="offline"))

        self.assertEqual(response.results, [])
        self.assertIn("没有可用的搜索后端", response.notices[0])

    @patch("app.search.service.monitor.report_search")
    def test_advanced部分失败仍返回其他后端结果(self, _report_search):
        failed = FakeProvider("failed", error="限流")
        healthy = FakeProvider("healthy", [make_result("https://example.com/healthy")])
        service = SearchService({"failed": failed, "healthy": healthy})

        response = service.search(SearchRequest(queries=["测试"], backend="advanced"))

        self.assertEqual(len(response.results), 1)
        self.assertEqual(response.backend, "healthy")
        self.assertTrue(any("failed" in notice and "限流" in notice for notice in response.notices))

    @patch("app.search.service.monitor.report_search")
    def test_auto全部失败时返回空结果和诊断提示(self, _report_search):
        first = FakeProvider("first", error="超时")
        second = FakeProvider("second", error="认证失败")
        service = SearchService({"first": first, "second": second})

        with patch.dict(os.environ, {"SEARCH_BACKEND_ORDER": "first,second"}):
            response = service.search(SearchRequest(queries=["测试"], backend="auto"))

        self.assertEqual(response.results, [])
        self.assertEqual(response.backend, "auto")
        self.assertTrue(any("认证失败" in notice for notice in response.notices))

    @patch("app.search.service.monitor.report_search")
    def test_单域名最多保留两条结果(self, _report_search):
        provider = FakeProvider(
            "only",
            [
                make_result("https://example.com/a", score=1.0),
                make_result("https://example.com/b", score=0.9),
                make_result("https://example.com/c", score=0.8),
                make_result("https://other.example/a", score=0.7),
            ],
        )
        service = SearchService({"only": provider})

        response = service.search(SearchRequest(queries=["测试"], backend="advanced"))

        self.assertEqual(len(response.results), 3)
        self.assertNotIn("https://example.com/c", [item.url for item in response.results])


    @patch("app.search.service.monitor.report_search")
    def test_provider_timeout_stops_waiting_for_slow_backend(self, _report_search):
        slow = SlowProvider("slow", delay=0.2)
        service = SearchService({"slow": slow}, provider_timeout=0.01)

        started_at = time.monotonic()
        response = service.search(SearchRequest(queries=["slow query"], backend="advanced"))

        self.assertLess(time.monotonic() - started_at, 0.15)
        self.assertEqual(response.results, [])
        self.assertTrue(any("exceeded" in notice for notice in response.notices))


if __name__ == "__main__":
    unittest.main()
