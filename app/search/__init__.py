"""统一网络搜索服务。"""

from app.search.models import SearchRequest, SearchResponse, SearchResult
from app.search.service import SearchService, get_search_service

__all__ = [
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
    "SearchService",
    "get_search_service",
]
