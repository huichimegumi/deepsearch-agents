from evals.reports_acceptance.ten_case_review import delivery_checks

SQL = "ev1_sql_a628020b895a2d4e2d853d02"


def test_completed_sql_only_report_with_fabricated_local_citations_is_not_ready():
    row = {
        "execution_status": "completed",
        "error_type": None,
        "audit": {"required_sources_collected": False, "required_sources_cited": False},
    }
    report = f"SQL [{SQL}]. Local passage [ev2_doc_fabricated]."
    issues = delivery_checks(
        row,
        {"answerable": True},
        {"records": [{"evidence_id": SQL}]},
        report,
    )
    assert issues == [
        "required_source_not_collected",
        "required_source_not_cited",
        "unknown_citation",
    ]


def test_clean_delivery_remains_only_ready_for_semantic_review():
    row = {
        "execution_status": "completed",
        "error_type": None,
        "audit": {"required_sources_collected": True, "required_sources_cited": True},
    }
    assert not delivery_checks(
        row, {"answerable": True}, {"records": [{"evidence_id": SQL}]}, f"Result [{SQL}]."
    )


def test_degraded_no_answer_notice_is_not_accepted_by_empty_citation_rule():
    row = {"execution_status": "degraded", "error_type": None, "audit": {}}
    assert delivery_checks(row, {"answerable": False}, {"records": []}, "No bounded evidence.") == [
        "execution_not_completed"
    ]
