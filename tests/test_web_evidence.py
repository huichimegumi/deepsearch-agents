from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.research.claims import ClaimDraft, validate_claims, validate_report_citations
from app.research.evidence import EvidenceSource, web_results_to_evidence
from app.search.models import SearchResponse, SearchResult
from app.tools.tavily_tool import research_search


def _result(
    *,
    url: str = "https://Example.com/report/?utm_source=search#section",
    raw_content: str = "Official revenue was 42 million in 2025.",
    score: float = 0.9,
) -> SearchResult:
    return SearchResult(
        title="Official report",
        url=url,
        content="Search-engine snippet",
        raw_content=raw_content,
        published_date="2026-01-15",
        score=score,
        source_backend="test",
        matched_queries=["official revenue"],
    )


def test_web_evidence_is_stable_across_tracking_ranking_and_whitespace():
    first = web_results_to_evidence([_result()])[0]
    second = web_results_to_evidence(
        [
            _result(
                url="https://example.com/report",
                raw_content="Official revenue was 42 million\n\nin 2025.",
                score=0.1,
            )
        ]
    )[0]

    assert first.source is EvidenceSource.WEB
    assert first.locator == "https://example.com/report"
    assert first.evidence_id == second.evidence_id
    assert first.evidence_id.startswith("ev1_web_")


def test_search_snippets_are_candidates_not_evidence():
    records = web_results_to_evidence([_result(raw_content="")])

    assert records == ()


def test_research_search_marks_snippets_and_provider_answers_as_candidates():
    response = SearchResponse(
        queries=["market"],
        backend="test",
        results=[_result(raw_content="")],
        answer="Provider-generated answer",
    )
    service = SimpleNamespace(search=lambda _request: response)

    with (
        patch("app.tools.tavily_tool.get_search_service", return_value=service),
        patch("app.tools.tavily_tool.get_research_budget", return_value=None),
        patch("app.tools.tavily_tool.get_research_trace", return_value=None),
        patch("app.tools.tavily_tool.write_audit_event"),
    ):
        payload = research_search.invoke({"queries": ["market"]})

    assert payload["evidence_records"] == []
    assert payload["results"][0]["evidence_status"] == "CANDIDATE_ONLY"
    assert payload["answer_evidence_status"] == "CANDIDATE_ONLY"
    assert "未生成 Web Evidence" in payload["notices"][-1]


def test_changed_fetched_page_content_changes_web_evidence_identity():
    first = web_results_to_evidence([_result(raw_content="Version one")])[0]
    changed = web_results_to_evidence([_result(raw_content="Version two")])[0]

    assert first.evidence_id != changed.evidence_id


def test_research_search_returns_and_traces_fetched_web_evidence():
    response = SearchResponse(
        queries=["official revenue"],
        backend="test",
        results=[_result()],
    )
    service = SimpleNamespace(search=lambda _request: response)
    trace = Mock()

    with (
        patch("app.tools.tavily_tool.get_search_service", return_value=service),
        patch("app.tools.tavily_tool.get_research_budget", return_value=None),
        patch("app.tools.tavily_tool.get_research_trace", return_value=trace),
        patch("app.tools.tavily_tool.write_audit_event"),
    ):
        payload = research_search.invoke({"queries": ["official revenue"], "fetch_full_page": True})

    evidence = payload["evidence_records"][0]
    assert evidence["source"] == "web"
    assert payload["results"][0]["evidence_id"] == evidence["evidence_id"]
    assert payload["results"][0]["evidence_status"] == "FETCHED"
    assert "raw_content" not in payload["results"][0]
    trace.record_search.assert_called_once()
    traced_records = trace.record_evidence.call_args.args[0]
    assert traced_records[0].evidence_id == evidence["evidence_id"]


def test_search_backend_lock_overrides_model_requested_advanced_mode(monkeypatch):
    captured = []
    response = SearchResponse(queries=["market"], backend="duckduckgo", results=[])
    service = SimpleNamespace(search=lambda request: captured.append(request) or response)
    monkeypatch.setenv("SEARCH_BACKEND_LOCK", "duckduckgo")

    with (
        patch("app.tools.tavily_tool.get_search_service", return_value=service),
        patch("app.tools.tavily_tool.get_research_budget", return_value=None),
        patch("app.tools.tavily_tool.get_research_trace", return_value=None),
        patch("app.tools.tavily_tool.write_audit_event"),
    ):
        research_search.invoke({"queries": ["market"], "backend": "advanced"})

    assert captured[0].backend == "duckduckgo"


def test_fetched_web_evidence_passes_claim_and_report_gates():
    record = web_results_to_evidence([_result()])[0]
    claims = validate_claims(
        [ClaimDraft(text="Revenue was 42 million.", evidence_ids=[record.evidence_id])],
        available_evidence_ids=[record.evidence_id],
    )
    citations = validate_report_citations(
        f"Revenue was 42 million [{record.evidence_id}].",
        allowed_evidence_ids=claims.referenced_evidence_ids,
    )

    assert len(claims.accepted) == 1
    assert citations.valid is True
