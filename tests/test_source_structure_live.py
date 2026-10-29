from evals.rag.run_source_structure_live import check_delivery, load_cases


def test_five_case_suite_is_unique_and_bounded():
    cases = load_cases()
    assert len(cases) == 5
    assert len({case["id"] for case in cases}) == 5


def test_live_check_accepts_tuple_plan_and_rejects_foreign_chunk():
    case = {
        "expected_status": "resolved",
        "expected_structure_status": "not_requested",
        "expected_document_sha256": "target",
    }
    batch = {
        "records": [{"evidence_id": "ev1_local_document_a", "metadata": {"chunk_id": "chunk-a"}}]
    }
    diagnostics = {
        "rerank_applied": True,
        "source_structure": {
            "status": "resolved",
            "structure_status": "not_requested",
            "document_sha256": ("target",),
        },
        "delivered_ids": ["chunk-a"],
    }
    checks = check_delivery(case, batch, diagnostics, {"chunk-a": "target"})
    assert all(checks.values())
    assert not check_delivery(case, batch, diagnostics, {"chunk-a": "foreign"})["source_scope"]


def test_excluded_source_check_requires_empty_no_evidence_batch():
    case = {
        "expected_status": "unsupported_source_constraint",
        "expected_structure_status": "not_requested",
    }
    diagnostics = {
        "rerank_applied": True,
        "source_structure": {
            "status": "unsupported_source_constraint",
            "structure_status": "not_requested",
            "selected_ids": [],
        },
        "delivered_ids": [],
    }
    assert all(
        check_delivery(case, {"records": [], "status": "NO_EVIDENCE"}, diagnostics, {}).values()
    )
    assert not check_delivery(case, {"records": [], "status": "OK"}, diagnostics, {})[
        "excluded_source_not_delivered"
    ]
