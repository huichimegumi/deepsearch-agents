import os

import pytest

from app.research.evidence import web_results_to_evidence
from app.search.models import SearchResult
from app.search.service import SearchService

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        os.getenv("RUN_WEB_EVIDENCE_TESTS") != "1",
        reason="set RUN_WEB_EVIDENCE_TESTS=1 to fetch a public page",
    ),
]


def test_public_page_fetch_produces_stable_web_evidence():
    url = "https://example.com/"
    service = SearchService({}, timeout=10, max_content_chars=4000)
    first_content = service._fetch_page(url)
    second_content = service._fetch_page(url)

    first = web_results_to_evidence(
        [SearchResult(title="Example Domain", url=url, raw_content=first_content)]
    )[0]
    second = web_results_to_evidence(
        [SearchResult(title="Renamed metadata", url=url, raw_content=second_content, score=0.1)]
    )[0]

    assert "Example Domain" in first.content
    assert first.locator == "https://example.com/"
    assert first.evidence_id == second.evidence_id
    assert first.evidence_id.startswith("ev1_web_")
