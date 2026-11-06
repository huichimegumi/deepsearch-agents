import json
from types import SimpleNamespace

import pytest

from app.research.compact_report import Outline, ResultRegistry, SectionText, write_report
from app.research.evidence_store import EvidenceStore, count_tokens
from app.research.report import ResearchReport, numeric_binding_errors
from evals.diagnostics.score_e9 import mechanical


def store_rows(tmp_path, n=200):
    store = EvidenceStore(tmp_path)
    store.add(
        [
            {
                "evidence_id": f"original_long_id_{i}",
                "source": "sql",
                "locator": "fixture:query",
                "content": {"entity": f"item-{i}", "n": i, "label": "x|y\nz"},
                "metadata": {"query": "SELECT entity,n,label FROM items", "truncated": False},
            }
            for i in range(n)
        ],
        "s0",
    )
    return store


def test_backend_tables_preserve_all_rows_and_reject_tampered_values(tmp_path):
    store = store_rows(tmp_path)
    registry = ResultRegistry(store)
    from app.research.compact_report import TableSelection

    table = registry.table(
        TableSelection(table_id=next(iter(registry.tables)), title="Results"), "Counts"
    )
    report = ResearchReport(title="Rows", answerability="answered", tables=[table])
    assert len(table.rows) == 200
    assert table.rows[-1][1] == 199
    assert not numeric_binding_errors(report, list(store.records.values()))
    assert not mechanical(
        {"oracle": {"answerable": True}, "required_sources": ["sql"]},
        {
            "status": "completed",
            "report": report.model_dump(),
            "evidence": list(store.records.values()),
        },
    )
    assert "x\\|y<br>z" in report.render()
    table.rows[0][1] = 999
    assert "table_cell_binding_mismatch" in numeric_binding_errors(
        report, list(store.records.values())
    )


def test_provenance_and_short_refs_survive_bounded_views(tmp_path):
    store = store_rows(tmp_path, 3)
    store.add(
        [
            {
                "evidence_id": "original_doc_id",
                "source": "local_document",
                "locator": "fixture:doc",
                "content": "Report details",
                "metadata": {"file_name": "report.pdf", "page_number": 7, "title": "Source"},
            }
        ],
        "s1",
    )
    registry = ResultRegistry(store)
    view = registry.view("Report details", max_tokens=700)
    assert count_tokens(view) <= 700
    doc = view["evidence"][0]
    assert doc["metadata"]["file_name"] == "report.pdf"
    assert doc["metadata"]["page_number"] == 7
    assert registry.resolve(doc["evidence_id"]) == "original_doc_id"
    assert "original_long_id" not in json.dumps(view)
    with pytest.raises(ValueError, match="unknown_short"):
        registry.resolve("invented")


def test_truncated_result_cannot_be_promoted_to_a_complete_report_table(tmp_path):
    from app.research.compact_report import TableSelection

    store = store_rows(tmp_path, 2)
    next(iter(store.records.values()))["metadata"]["truncated"] = True
    registry = ResultRegistry(store)
    with pytest.raises(ValueError, match="incomplete"):
        registry.table(TableSelection(table_id=next(iter(registry.tables)), title="Results"), None)


@pytest.mark.asyncio
async def test_failed_section_preserves_other_section_and_original_rows(tmp_path):
    store = store_rows(tmp_path / "evidence", 150)
    registry = ResultRegistry(store)
    table_id = next(iter(registry.tables))
    outline = Outline(
        report_title="Counts",
        answerability="answered",
        heading_1="Counts",
        focus_1="table",
        table_refs_1=table_id,
        heading_2="Explanation",
        focus_2="notes",
    )

    class Model:
        calls = 0

        def with_structured_output(self, schema, **kwargs):
            assert schema is SectionText
            self.schema = schema
            return self

        def bind(self, **kwargs):
            assert kwargs["max_tokens"] == 1800
            return self

        async def ainvoke(self, messages):
            self.calls += 1
            if self.calls == 2:
                return {
                    "parsed": None,
                    "parsing_error": "truncated",
                    "raw": SimpleNamespace(
                        tool_calls=[], content="", response_metadata={"finish_reason": "length"}
                    ),
                }
            return {"parsed": self.schema(claims=[]), "raw": SimpleNamespace(response_metadata={})}

    model = Model()
    report, responses, errors = await write_report(
        "Show counts", store, tmp_path / "report", model=model, outline=outline
    )
    assert model.calls == 2
    assert errors
    assert report.answerability == "partial"
    assert len(report.tables[0].rows) == 150
    assert not numeric_binding_errors(report, list(store.records.values()))
    assert (tmp_path / "report/section-2-rejected.json").exists()


def test_whole_table_citation_avoids_repeating_every_row_id(tmp_path):
    store = store_rows(tmp_path, 80)
    registry = ResultRegistry(store)
    key = registry.resolve("t1")
    record = registry.table_records["t1"]
    assert key == record["evidence_id"]
    assert len(record["content"]["rows"]) == 80
    assert record["metadata"]["derived_from"] == list(store.records)
    assert record["content"]["rows"][42][1] == 42


def test_scalar_claims_isolate_bad_refs_and_never_promote_a_preview(tmp_path):
    from app.research.compact_report import SectionDraft, draft_claims, text_view

    store = store_rows(tmp_path, 20)
    registry = ResultRegistry(store)
    preview = text_view(registry.view("counts", max_tokens=400))
    assert "table_ref" not in preview["result_tables"][0]
    row_ref = preview["result_tables"][0]["rows"][0]["ref"]
    draft = SectionDraft(
        claim_1="One observed item",
        refs_1=row_ref,
        claim_2="All items",
        refs_2="t1",
        scope_2="complete_result",
    )
    claims, errors = draft_claims(draft, registry, preview, "Results")
    assert len(claims) == 1
    assert errors == [{"claim": 2, "reason": "claim_scope_or_visibility_mismatch"}]
    # Even a complete stored table cannot support a model's whole-table claim
    # when some rows were omitted from the model's view.
    assert registry.tables["t1"]["complete"]
    next(iter(store.records.values()))["metadata"]["truncated"] = True
    registry = ResultRegistry(store)
    assert "table_ref" not in text_view(registry.view("counts"))["result_tables"][0]
    with pytest.raises(ValueError, match="incomplete_table"):
        registry.resolve("t1")


@pytest.mark.asyncio
async def test_scalar_writer_backend_structure_survives_invalid_second_claim(tmp_path):
    from app.research.compact_report import SectionDraft

    store = store_rows(tmp_path / "evidence", 3)

    class Model:
        calls = 0

        def with_structured_output(self, schema, **kwargs):
            assert schema is SectionDraft
            return self

        def bind(self, **kwargs):
            return self

        async def ainvoke(self, messages):
            self.calls += 1
            payload = json.loads(messages[-1]["content"])
            assert "section" not in payload  # no section object to echo into output
            return {
                "parsed": SectionDraft(
                    claim_1="The query returned observed rows.",
                    refs_1="t1",
                    scope_1="complete_result",
                    claim_2="Unseen evidence",
                    refs_2="e999",
                ),
                "raw": None,
            }

    model = Model()
    report, _, errors = await write_report(
        "Show counts", store, tmp_path / "report", model=model, scalar=True
    )
    assert model.calls == 1  # no model outline request
    assert len(report.tables) == 1 and len(report.tables[0].rows) == 3
    assert len(report.claims) == 1 and len(errors) == 1
    assert report.answerability == "partial"
    assert not numeric_binding_errors(report, list(store.records.values()))
    diagnostics = json.loads((tmp_path / "report/section-1-claims.json").read_text())
    assert diagnostics["accepted"] == 1
    assert diagnostics["rejected"][0]["claim"] == 2


def test_scalar_protocol_rejects_nested_output_and_excess_refs_without_truncation(tmp_path):
    from pydantic import ValidationError

    from app.research.compact_report import SectionDraft, draft_claims, text_view

    with pytest.raises(ValidationError):
        SectionDraft.model_validate({"claims": [{"text": "extra"}], "section": {"title": "extra"}})
    registry = ResultRegistry(store_rows(tmp_path, 10))
    draft = SectionDraft(claim_1="Too many refs", refs_1=",".join(f"e{i}" for i in range(1, 10)))
    claims, errors = draft_claims(draft, registry, text_view(registry.view("counts")), "Results")
    assert not claims and errors[0]["reason"] == "invalid_claim_references"
