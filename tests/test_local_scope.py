import json

import pytest

from app.agent import main_agent
from app.research.local_scope import check_local_absence_scope, enforce_local_absence_scope
from evals.reports_acceptance import replay_sources
from tests.test_source_provenance import evidence, replay_fixture, trace


@pytest.mark.parametrize(
    "text",
    [
        "所有可访问的文档均未提及任何该类关键词。",
        "本地知识库中**不存在**相关章节。仅取得三个片段，可能存在遗漏。",
        "知识库未收录此类资料",
        "全部文件都没有相关章节",
        "该文档全文未涉及这一主题",
        "The knowledge base does not contain this chapter.",
        "All indexed documents do not mention that topic.",
        "The entire document contains no related section.",
    ],
)
def test_explicit_corpus_absence_is_flagged_even_with_a_later_caveat(text):
    assert check_local_absence_scope(text)["matched_assertions"]


@pytest.mark.parametrize(
    "text",
    [
        "当前检索片段未提及该主题，不能据此推断全文内容。",
        "无法确认本地知识库中不存在相关章节。",
        "不能断言所有文档均未提及该主题。",
        "本地知识库中是否包含相关章节？",
        "本地知识库包含该章节。",
        "所有文档均讨论风险控制。",
        "无法支持该主题存在于知识库中的主张。",
        "I cannot conclude that the corpus contains no relevant chapter.",
        "The retrieved excerpts do not mention this topic.",
    ],
)
def test_bounded_gaps_questions_and_positive_findings_are_not_flagged(text):
    assert not check_local_absence_scope(text)["matched_assertions"]


def test_uncertainty_in_another_clause_does_not_excuse_assertion():
    assert check_local_absence_scope("无法确认是否遗漏，但本地知识库中不存在该章节。")[
        "matched_assertions"
    ]


@pytest.mark.parametrize("capture", [False, True])
def test_gate_has_count_only_telemetry_and_opt_in_private_inputs(capture):
    current = trace(capture)
    unsafe = f"知识库中不存在 private-topic [{evidence().evidence_id}]"
    result, validation = main_agent._enforce_final_report_citations(
        report_markdown=unsafe, compressed_fallback="unsafe fallback", run_trace=current
    )
    assert "private-topic" not in result and "unsafe fallback" not in result
    assert "不足以判断" in result
    assert current.degraded and validation.valid
    assert current.failure_reasons == ["unverified_local_absence_scope"]
    assert not check_local_absence_scope(result)["matched_assertions"]
    private = current.export_evidence_snapshot()["local_scope_checks"]
    assert len(private) == int(capture)
    telemetry = json.dumps(current.finalize(status="completed", final_result=""))
    assert "private-topic" not in telemetry and "private passage" not in telemetry


def test_citation_fallback_cannot_republish_absence_claim():
    current = trace()
    result, _ = main_agent._enforce_final_report_citations(
        report_markdown="no citations",
        compressed_fallback=f"所有文档均未提及 private-topic [{evidence().evidence_id}]",
        run_trace=current,
    )
    assert "private-topic" not in result
    assert current.local_scope_checks[-1]["candidate_kind"] == "citation_fallback"
    assert current.failure_reasons == [
        "final_report_citation_validation_failed",
        "unverified_local_absence_scope",
    ]


def test_nonlocal_compatibility():
    current = trace()
    current.local_retrieval_required = False
    assert enforce_local_absence_scope("知识库不存在章节", current, candidate_kind="test") is None
    assert current.local_scope_checks == []


def test_bounded_positive_report_is_unchanged_by_delivery_gate():
    current = trace()
    report = f"《Known.pdf》的片段讨论直播应用 [{evidence().evidence_id}]"
    result, validation = main_agent._enforce_final_report_citations(
        report_markdown=report, compressed_fallback="", run_trace=current
    )
    assert result == report and validation.valid and not current.degraded


def test_offline_scope_replay_checks_saved_hashes_and_preserves_original(tmp_path, monkeypatch):
    path, original = replay_fixture(tmp_path, monkeypatch)
    report = path.parent / "report_local_006/report.md"
    report.write_text("所有可访问的文档均未提及此主题。", encoding="utf-8")
    original["results"][0]["report_sha256"] = replay_sources.file_sha256(report)
    path.write_text(json.dumps(original), encoding="utf-8")
    before = path.read_bytes(), report.read_bytes()
    result = replay_sources.replay(path, policy="absence_scope")
    row = result["results"][0]
    assert row["status"] == "withheld"
    assert row["before_scope_matches"] == 1 and row["after_scope_matches"] == 0
    assert result["manifest"]["configuration"]["llm_calls"] == 0
    assert before == (path.read_bytes(), report.read_bytes())
    assert result["semantic_acceptance"] == "pending_human_review"
