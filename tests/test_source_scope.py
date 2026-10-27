import json

import pytest

from app.agent import main_agent
from app.research.evidence import EvidenceRecord, EvidenceSource
from app.research.source_scope import requires_local_only
from evals.reports_acceptance.extended import load_suite


@pytest.mark.parametrize(
    "query",
    [
        "仅使用公开网络，不要查询本地知识库或数据库。",
        "请只使用网页资料，禁止使用本地知识库。",
        "不要检索本地知识库。只能使用网络。",
        "不得访问本地知识库和数据库，仅使用公开网页回答。",
        "无需使用RAG，只使用网页。",
        "只用网络，不需要使用本地知识库。",
        "Use only web search; do not use RAG or SQL.",
        "Do not use RAG; only use internet search.",
        "仅使用本地知识库和数据库，不联网。",
        "仅使用SQL与本地知识库。",
        "仅使用本地知识库；也使用网页。",
        "使用本地知识库，不要使用网页，但查询数据库。",
        "RAG与网络结合分析。",
        "知识库助手有哪些功能？",
        "比较fragment storage两个术语，只使用网络。",
    ],
)
def test_negative_local_constraints_and_affirmed_other_sources_keep_general_route(query):
    assert not requires_local_only(query)


@pytest.mark.parametrize(
    "query",
    [
        "仅使用本地知识库回答问题。",
        "请只使用本地知识库助手，看一下报告中的营收情况。",
        "只能使用本地知识库（金融行业、电商行业），不要联网。",
        "只用本地知识库回答，不要查询数据库。",
        "只根据本地知识库回答。",
        "只从本地知识库获取材料。",
        "使用本地知识库回答，禁止网络搜索。",
        "本地知识库回答，不使用网络。",
        "仅使用本地知识库，不要使用网络搜索、数据库或费用引擎。",
        "不要使用网络搜索、数据库或费用引擎，仅使用本地知识库。",
        "只使用RAG，禁止网络搜索。",
        "Use only RAG; do not use web search or SQL.",
        "Only use RAG, never access web or SQL.",
        "仅使用本地知识库回答网络安全问题，不联网。",
        "仅使用本地知识库，分析报告里的数据库行业趋势。",
        "只使用RAG回答SQL优化问题。",
    ],
)
def test_affirmative_local_only_and_negated_other_source_lists_are_preserved(query):
    assert requires_local_only(query)


def test_frozen_extended_questions_are_general_and_frozen_local_questions_stay_local():
    assert all(not requires_local_only(case["question"]) for case in load_suite()["cases"])
    from evals.reports_acceptance.run import DEFAULT_DATASET, load_cases

    suite, cases = load_cases(DEFAULT_DATASET)
    assert all(
        requires_local_only(suite["prompt_template"].format(question=case["question"]))
        for case in cases
    )


@pytest.mark.parametrize(
    "query",
    [
        "仅使用本地知识库（金融行业）和数据库，不联网。",
        "仅使用本地知识库（网络安全）以及SQL。",
    ],
)
def test_named_knowledge_base_parenthesis_does_not_hide_an_actual_source_join(query):
    assert not requires_local_only(query)


async def test_web_evidence_reaches_writer_without_mandatory_local_lookup(tmp_path, monkeypatch):
    record = EvidenceRecord.create(
        source=EvidenceSource.WEB, locator="https://example.test/page", content="Synthetic source"
    )
    phases = []

    async def phase(**kwargs):
        trace = kwargs["run_trace"]
        key = kwargs["phase"].key
        phases.append(key)
        assert "【本地知识库限定】" not in kwargs["prompt"]
        trace.start_phase(key, key)
        if key == "supervisor_research":
            trace.record_evidence((record,))
        if key == "evidence_compression":
            trace.claim_evidence_ids = [record.evidence_id]
        trace.finish_phase(key, "end")
        return (
            f"Synthetic answer [{record.evidence_id}]" if key == "final_report" else "phase output"
        )

    async def forbidden(*args):
        raise AssertionError("Web-only request must not start mandatory local retrieval")

    monkeypatch.setattr(main_agent, "project_root_path", tmp_path)
    for name in ["get_planner_agent", "get_research_agent", "get_writer_agent"]:
        monkeypatch.setattr(main_agent, name, lambda: object())
    monkeypatch.setattr(main_agent, "require_local_retrieval", forbidden)
    monkeypatch.setattr(main_agent, "_run_agent_phase", phase)
    monkeypatch.setattr(main_agent, "_run_direct_phase", phase)
    monkeypatch.setattr(main_agent, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_agent.monitor, "_emit", lambda *args, **kwargs: None)
    result = await main_agent.run_deep_agent(
        "仅使用公开网络，不要查询本地知识库或数据库。", "web-scope"
    )
    trace = json.loads(
        (tmp_path / "output/session_web-scope/research_trace.json").read_text(encoding="utf-8")
    )
    assert result == f"Synthetic answer [{record.evidence_id}]"
    assert phases == [
        "clarify_and_brief",
        "supervisor_research",
        "evidence_compression",
        "final_report",
    ]
    assert trace["local_retrieval"]["required"] is False
    assert trace["local_retrieval"]["attempts"] == []
