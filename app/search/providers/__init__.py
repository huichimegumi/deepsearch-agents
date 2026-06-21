"""内置搜索后端。"""

from app.search.providers.duckduckgo import DuckDuckGoProvider
from app.search.providers.perplexity import PerplexityProvider
from app.search.providers.searxng import SearxNGProvider
from app.search.providers.tavily import TavilyProvider

__all__ = [
    "DuckDuckGoProvider",
    "PerplexityProvider",
    "SearxNGProvider",
    "TavilyProvider",
]
