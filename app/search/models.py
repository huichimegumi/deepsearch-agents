"""搜索服务使用的统一数据模型。"""

from dataclasses import asdict, dataclass, field
from typing import Literal

SearchBackend = Literal[
    "auto",
    "advanced",
    "tavily",
    "duckduckgo",
    "perplexity",
    "searxng",
]
SearchTopic = Literal["general", "news", "finance"]


@dataclass(slots=True)
class SearchRequest:
    """一次搜索任务，可包含多个互补查询。"""

    queries: list[str]
    backend: SearchBackend = "auto"
    topic: SearchTopic = "general"
    max_results: int = 8
    fetch_full_page: bool = False


@dataclass(slots=True)
class SearchResult:
    """不同搜索后端归一化后的单条结果。"""

    title: str
    url: str
    content: str = ""
    raw_content: str = ""
    published_date: str = ""
    score: float = 0.0
    source_backend: str = ""
    matched_queries: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """转换为便于 LangChain 工具传递的字典。"""
        return asdict(self)


@dataclass(slots=True)
class SearchResponse:
    """搜索工具对 Agent 暴露的稳定响应结构。"""

    queries: list[str]
    backend: str
    results: list[SearchResult] = field(default_factory=list)
    answer: str | None = None
    notices: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """转换为可序列化字典。"""
        return {
            "queries": self.queries,
            "backend": self.backend,
            "results": [result.to_dict() for result in self.results],
            "answer": self.answer,
            "notices": self.notices,
        }
