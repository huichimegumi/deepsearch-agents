import json

import pytest

from app.agent import main_agent
from app.agent.runtime import ResearchBudget, ResearchBudgetLimits, ResearchRunTrace
from app.research.claims import ClaimDraft, validate_claims
from app.research.evidence import EvidenceRecord, EvidenceSource
from app.research.source_provenance import (
    check_source_filenames,
    document_catalog,
    enforce_local_source_references,
)
from evals.reports_acceptance import replay_sources
from evals.runners.experiment import file_sha256


def evidence(filename="Known.pdf", source=EvidenceSource.LOCAL_DOCUMENT):
    return EvidenceRecord.create(
        source=source,
        locator="document://source#1",
        content="private passage",
        metadata={"filename": filename},
    )


def trace(capture=False):
    result = ResearchRunTrace(
        "run",
        "thread",
        "deep_report",
        ResearchBudget(ResearchBudgetLimits("deep_report", 300, 0, 0, 2, 12, 75)),
    )
    result.local_retrieval_required = True
    result.capture_report_source_checks = capture
    result.record_evidence((evidence(),))
    result.claim_evidence_ids = [evidence().evidence_id]
    return result


def test_catalog_comes_only_from_actual_local_record_metadata():
    records = [
        evidence(),
        evidence("KNOWN.PDF"),
        evidence(None),
        evidence("Web.pdf", EvidenceSource.WEB),
    ]
    catalog = document_catalog(records)
    assert len(catalog) == 1
    assert catalog[0]["filename"] == "Known.pdf"
    assert len(catalog[0]["evidence_ids"]) == 1


@pytest.mark.parametrize("extension", ["pdf", "doc", "docx", "xls", "xlsx", "txt", "md"])
def test_explicit_document_filename_extensions_are_checked(extension):
    audit = check_source_filenames(f"《Unverified.{extension}》", document_catalog([evidence()]))
    assert audit["unverified_filenames"] == [f"Unverified.{extension}"]


def test_identity_is_not_fuzzy_or_whitespace_erasing():
    catalog = document_catalog([evidence("A B.pdf"), evidence("café.pdf")])
    audit = check_source_filenames("《a b.PDF》 《café.pdf》 《AB.pdf》 《A B 2026.pdf》", catalog)
    assert audit["unverified_filenames"] == ["AB.pdf", "A B 2026.pdf"]


def test_short_titles_and_non_book_quoted_filenames_are_outside_policy():
    assert check_source_filenames("《Unknown short title》 unknown.pdf", []) == {
        "mentioned_filenames": [],
        "unverified_filenames": [],
    }


def test_nonlocal_requests_are_not_gated():
    current = trace()
    current.local_retrieval_required = False
    assert (
        enforce_local_source_references("《Unknown.pdf》", current, candidate_kind="test") is None
    )
    assert current.local_source_reference_checks == []


@pytest.mark.parametrize("capture", [False, True])
def test_unknown_source_withheld_without_promoting_the_fallback_or_absence(capture):
    current = trace(capture)
    unsafe = f"《Invented.pdf》 contains a fact [{evidence().evidence_id}]"
    safe, citation = main_agent._enforce_final_report_citations(
        report_markdown=unsafe, compressed_fallback="unsafe fallback", run_trace=current
    )
    assert citation.valid  # A technical boundary notice, not a supported factual answer.
    assert "Invented.pdf" not in safe and "unsafe fallback" not in safe
    assert "Known.pdf" in safe and "不表示相关文件不存在" in safe
    assert current.degraded
    assert current.failure_reasons == ["unverified_local_source_filename"]
    assert len(current.export_evidence_snapshot()["source_reference_checks"]) == int(capture)
    telemetry = json.dumps(current.finalize(status="completed", final_result=""))
    assert "Invented.pdf" not in telemetry and "private passage" not in telemetry


def test_citation_fallback_is_checked_instead_of_republishing_contaminated_claims():
    current = trace()
    current.record_claim_validation(
        validate_claims(
            [ClaimDraft(text="《Invented.pdf》 fact", evidence_ids=[evidence().evidence_id])],
            available_evidence_ids=current.claim_eligible_evidence_ids,
        )
    )
    safe, _ = main_agent._enforce_final_report_citations(
        report_markdown="no citations",
        compressed_fallback="《Invented.pdf》 fact",
        run_trace=current,
    )
    assert "Invented.pdf" not in safe
    assert current.failure_reasons == [
        "final_report_citation_validation_failed",
        "unverified_local_source_filename",
    ]
    assert current.local_source_reference_checks[-1]["candidate_kind"] == "citation_fallback"


def test_known_source_is_not_rewritten_and_ledger_supplies_actual_filename():
    current = trace()
    original = f"《Known.pdf》 fact [{evidence().evidence_id}]"
    result, citation = main_agent._enforce_final_report_citations(
        report_markdown=original, compressed_fallback="", run_trace=current
    )
    assert result == original and citation.valid and not current.degraded
    assert "Known.pdf" in current.render_evidence_ledger()
    assert "not a full-document inventory audit" in current.render_evidence_ledger()


def replay_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(replay_sources, "ROOT", tmp_path)
    directory = tmp_path / "evals/results/original/report_local_006"
    directory.mkdir(parents=True)
    (directory / "report.md").write_text("《Invented.pdf》 fact", encoding="utf-8")
    (directory / "evidence.json").write_text(
        json.dumps({"records": [evidence().to_dict()]}), encoding="utf-8"
    )
    result = {
        "run_id": "original",
        "inputs_unchanged": True,
        "manifest": {"dataset_sha256": file_sha256(replay_sources.DEFAULT_DATASET)},
        "results": [
            {
                "id": "report_local_006",
                "review_directory": "evals/results/original/report_local_006",
                "report_sha256": file_sha256(directory / "report.md"),
                "evidence_sha256": file_sha256(directory / "evidence.json"),
            }
        ],
    }
    path = directory.parent / "results.json"
    return path, result


def test_saved_source_replay_is_offline_and_preserves_the_original(tmp_path, monkeypatch):
    path, original = replay_fixture(tmp_path, monkeypatch)
    path.write_text(json.dumps(original), encoding="utf-8")
    replayed = replay_sources.replay(path)
    row = replayed["results"][0]
    assert row["status"] == "withheld"
    assert row["before_unverified_mentions"] == 1 and row["after_unverified_mentions"] == 0
    assert not row["candidate_unchanged"]
    assert replayed["semantic_acceptance"] == "pending_human_review"


@pytest.mark.parametrize("failure", ["unfinished", "hash", "outside", "unknown_case", "unexecuted"])
def test_source_replay_rejects_invalid_inputs(tmp_path, monkeypatch, failure):
    path, original = replay_fixture(tmp_path, monkeypatch)
    if failure == "unfinished":
        original["inputs_unchanged"] = False
    elif failure == "hash":
        original["results"][0]["report_sha256"] = "changed"
    elif failure == "outside":
        original["results"][0]["review_directory"] = "outside"
    elif failure == "unknown_case":
        original["results"][0]["id"] = "../../outside"
    path.write_text(json.dumps(original), encoding="utf-8")
    with pytest.raises(ValueError):
        replay_sources.replay(path, ["report_local_001"] if failure == "unexecuted" else None)


@pytest.mark.parametrize(
    ("candidate", "artifact_status"),
    [
        ("《Invented.pdf》 claim", "source_withheld_persisted"),
        ("所有可访问的文档均未提及 private-topic", "scope_withheld_persisted"),
    ],
)
async def test_main_workflow_persists_only_the_source_boundary(
    tmp_path, monkeypatch, candidate, artifact_status
):
    async def lookup(query, current, timeout):
        current.record_evidence((evidence(),))
        current.record_local_retrieval("OK", 1)

    async def phase(**kwargs):
        current = kwargs["run_trace"]
        key = kwargs["phase"].key
        current.start_phase(key, key)
        current.finish_phase(key, "end")
        if key == "evidence_compression":
            current.claim_evidence_ids = [evidence().evidence_id]
        if key == "final_report":
            assert "Known.pdf" in kwargs["prompt"]
            return f"{candidate} [{evidence().evidence_id}]"
        return "phase output"

    monkeypatch.setattr(main_agent, "project_root_path", tmp_path)
    for name in (
        "get_planner_agent",
        "get_research_agent",
        "get_indexed_local_research_agent",
        "get_writer_agent",
    ):
        monkeypatch.setattr(main_agent, name, lambda: object())
    monkeypatch.setattr(main_agent, "require_local_retrieval", lookup)
    monkeypatch.setattr(main_agent, "_run_agent_phase", phase)
    monkeypatch.setattr(main_agent, "_run_direct_phase", phase)
    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "_emit", lambda *args, **kwargs: None)
    result = await main_agent.run_deep_agent("仅使用本地知识库，生成 Markdown 报告", "source-guard")
    directory = tmp_path / "output/session_source-guard"
    assert "Invented.pdf" not in result
    assert "private-topic" not in result
    assert (directory / "report.md").read_text(encoding="utf-8") == result
    saved = json.loads((directory / "research_trace.json").read_text(encoding="utf-8"))
    assert saved["status"] == "degraded"
    assert saved["phases"][-1]["artifact_status"] == artifact_status
