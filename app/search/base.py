"""搜索后端的抽象接口与共享异常。"""

from abc import ABC, abstractmethod

from app.search.models import SearchResult, SearchTopic


class SearchProviderError(RuntimeError):
    """搜索后端不可用或请求失败。"""


class SearchProvider(ABC):
    """所有搜索后端必须实现的最小接口。"""

    name: str

    @abstractmethod
    def is_available(self) -> bool:
        """返回当前环境是否具备调用该后端的必要配置。"""

    @abstractmethod
    def search(
        self,
        query: str,
        *,
        topic: SearchTopic,
        max_results: int,
    ) -> tuple[list[SearchResult], str | None]:
        """执行查询并返回标准结果和可选的直接答案。"""
