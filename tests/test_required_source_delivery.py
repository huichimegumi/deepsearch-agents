from types import SimpleNamespace

from app.agent.main_agent import _enforce_required_source_delivery
from app.agent.runtime import ResearchRunTrace
from app.research.claims import validate_report_citations

SQL = "ev1_sql_aaaaaaaaaaaaaaaaaaaaaaaa"
LOCAL = "ev1_local_document_bbbbbbbbbbbbbbbbbbbbbbbb"


def trace_with(*sources):
    trace = ResearchRunTrace(run_id="r", thread_id="t", budget_profile="deep_report", budget=None)
    records = [SimpleNamespace(evidence_id=eid, source=source) for eid, source in sources]
    trace.record_evidence(records)
    return trace


def test_missing_local_source_withholds_completed_looking_sql_report():
    trace = trace_with((SQL, "sql"))
    report = f"SQL answer [{SQL}]. Local answer [ev2_doc_fabricated]."
    original = validate_report_citations(report, allowed_evidence_ids=trace.evidence_ids)
    delivered, validation = _enforce_required_source_delivery(
        report, original, trace, ("sql", "local_document")
    )
    assert delivered.startswith("# Report delivery withheld")
    assert "Local answer" not in delivered
    assert validation.valid
    assert trace.degraded
    assert "required_evidence_source_missing" in trace.failure_reasons


def test_collected_but_uncited_source_is_withheld():
    trace = trace_with((SQL, "sql"), (LOCAL, "local_document"))
    report = f"Only SQL [{SQL}]."
    original = validate_report_citations(report, allowed_evidence_ids=trace.evidence_ids)
    delivered, _ = _enforce_required_source_delivery(
        report, original, trace, ("sql", "local_document")
    )
    assert delivered.startswith("# Report delivery withheld")


def test_both_eligible_sources_cited_preserves_report():
    trace = trace_with((SQL, "sql"), (LOCAL, "local_document"))
    report = f"SQL [{SQL}]. Local [{LOCAL}]."
    original = validate_report_citations(report, allowed_evidence_ids=trace.evidence_ids)
    delivered, validation = _enforce_required_source_delivery(
        report, original, trace, ("sql", "local_document")
    )
    assert delivered == report
    assert validation is original
    assert not trace.degraded
