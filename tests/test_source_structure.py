import json

import pytest

from app.rag.source_structure import (
    document_key,
    is_toc,
    plan_source_structure,
    requests_toc,
    scoped_delivery_ids,
)
from evals.rag import run_source_structure as replay

TOC = "7\n目 录\nCONTENTS\n01 第一主题\n02 第二主题"


@pytest.fixture
def corpus():
    return {
        "toc": {
            "chunk_id": "toc",
            "filename": "Report.pdf",
            "document_sha256": "doc",
            "content": TOC,
            "chunk_index": 0,
            "page_start": 7,
            "page_end": 7,
        },
        "body": {
            "chunk_id": "body",
            "filename": "Report.pdf",
            "document_sha256": "doc",
            "content": "body",
            "chunk_index": 1,
            "page_start": 8,
            "page_end": 8,
        },
        "foreign": {
            "chunk_id": "foreign",
            "filename": "Other.pdf",
            "document_sha256": "other",
            "content": TOC,
            "chunk_index": 0,
            "page_start": 1,
            "page_end": 1,
        },
    }


def test_exact_names_normalize_only_formatting_and_extension(corpus):
    assert document_key(" Ｒｅｐｏｒｔ.PDF ") == "report"
    assert (
        plan_source_structure("《Report》描述了什么？", corpus, list(corpus)).status == "resolved"
    )
    assert plan_source_structure("《Rep》目录", corpus, list(corpus)).status == "unresolved_source"
    assert (
        plan_source_structure("报告简称的目录", corpus, list(corpus)).status == "no_explicit_source"
    )


def test_duplicate_source_names_and_partial_resolution_do_not_guess(corpus):
    corpus["foreign"]["filename"] = "REPORT.pdf"
    assert (
        plan_source_structure("《Report》目录", corpus, list(corpus)).status == "ambiguous_source"
    )
    corpus["foreign"]["filename"] = "Other.pdf"
    plan = plan_source_structure("对比《Report》和《Missing》的目录", corpus, list(corpus))
    assert plan.status == "unresolved_source" and not plan.document_sha256


def test_negated_source_is_not_silently_selected(corpus):
    plan = plan_source_structure("不要查《Report》，请找别的材料。", corpus, list(corpus))
    assert plan.status == "unsupported_source_constraint" and not plan.document_sha256


def test_source_reservation_limit_is_explicit(corpus):
    corpus["third"] = {**corpus["toc"], "filename": "Third.pdf", "document_sha256": "third"}
    plan = plan_source_structure("列出《Report》《Other》《Third》的目录", corpus, list(corpus))
    assert plan.structure_status == "source_limit" and not plan.structural_ids


@pytest.mark.parametrize(
    "query,requested",
    [
        ("列出目录第一二章。不要据目录推断正文。", True),
        ("不要生成目录。请回答营收。", False),
        ("请无需目录", False),
        ("Do not list the table of contents", False),
        ("是否有火星移民的专门章节？", False),
        ("List table of contents", True),
    ],
)
def test_structural_intent_preserves_negative_controls(query, requested):
    assert requests_toc(query) == requested


@pytest.mark.parametrize(
    "text,expected",
    [
        (TOC, True),
        ("目录\n第1章 第一主题\n第2章 第二主题", True),
        ("正文讨论目录\n01 主题\n02 主题", False),
        ("目录\n01 主题", False),
        ("目录\n01 主题\n01 重复", False),
        ("目录\n这里没有编号条目", False),
    ],
)
def test_toc_requires_standalone_marker_and_distinct_entries(text, expected):
    assert is_toc(text) == expected


def test_structure_selection_is_document_and_pool_bound(corpus):
    plan = plan_source_structure("《Report》目录", corpus, list(corpus))
    assert plan.structural_ids == ("toc",) and plan.structure_status == "selected"
    outside = plan_source_structure("《Report》目录", corpus, ["body", "foreign"])
    assert outside.structure_status == "structure_outside_pool" and not outside.structural_ids
    assert not plan_source_structure("《Report》应用场景", corpus, list(corpus)).structural_ids


def test_ambiguous_or_missing_structure_is_explicit(corpus):
    corpus["duplicate"] = {**corpus["toc"], "chunk_id": "duplicate"}
    assert (
        plan_source_structure("《Report》目录", corpus, list(corpus)).structure_status
        == "ambiguous_structure"
    )
    del corpus["duplicate"]
    corpus["toc"]["content"] = "not a TOC"
    assert (
        plan_source_structure("《Report》目录", corpus, list(corpus)).structure_status
        == "structure_missing"
    )


def test_structure_reservation_is_explicit_and_does_not_protect_foreign_chunks(corpus):
    policy = {
        "reranked_ids": ["foreign", "body", "toc"],
        "rerank_scores": {"foreign": 10, "body": 5, "toc": 0.2},
        "hits": [corpus["foreign"], corpus["body"]],
    }
    plan = plan_source_structure("《Report》目录", corpus, list(corpus))
    assert scoped_delivery_ids(plan, corpus, policy) == ["toc", "body"]
    factual = plan_source_structure("《Report》应用场景", corpus, list(corpus))
    assert scoped_delivery_ids(factual, corpus, policy) == ["body"]
    unknown = plan_source_structure("《Unknown》目录", corpus, list(corpus))
    assert scoped_delivery_ids(unknown, corpus, policy) == ["foreign", "body"]


def test_raw_evidence_uses_stable_identity_and_context_budget(corpus):
    from app.rag.retrieval import RetrievedChunk
    from app.research.evidence import retrieved_chunks_to_evidence

    policy = {"reranked_ids": ["body", "toc"], "rerank_scores": {"body": 5, "toc": 0.2}}
    plan = plan_source_structure("《Report》目录", corpus, ["body", "toc"])
    output = replay.replay_policy({"query": "《Report》目录"}, corpus, plan, policy)
    assert output["hits"][0]["content"] == TOC
    reference = RetrievedChunk(
        chunk_id="toc",
        content=TOC,
        filename="Report.pdf",
        page_start=7,
        page_end=7,
        section=None,
        score=123,
        document_sha256="doc",
        chunk_index=0,
    )
    expected = retrieved_chunks_to_evidence([reference], knowledge_base_ids=["old"], query="old")
    assert output["hits"][0]["evidence_id"] == expected[0].evidence_id
    assert output["structural_delivery_ids"] == ["toc"]
    assert output["budget"]["answer_hits"] <= 6
    assert output["historical_scores_reused"]


def test_unresolved_policy_is_copied_without_changing_text_or_budget(corpus):
    plan = plan_source_structure("《Unknown》目录", corpus, list(corpus))
    policy = {"hits": [{"chunk_id": "body", "content": "already truncated"}], "budget": {"x": 1}}
    assert replay.replay_policy({"query": "q"}, corpus, plan, policy) == policy
    assert replay.replay_policy({"query": "q"}, corpus, plan, policy) is not policy


def test_invalid_candidate_membership_rejected(corpus):
    for ids in (["missing"], ["toc", "toc"]):
        with pytest.raises(ValueError, match="candidate_membership"):
            plan_source_structure("《Report》目录", corpus, ids)


def test_default_plan_does_not_run_replay(monkeypatch, tmp_path):
    monkeypatch.setattr(replay, "ROOT", tmp_path)
    monkeypatch.setattr(replay, "load_inputs", lambda **_: ([], {}, {}, {}))
    monkeypatch.setattr(replay, "build_manifest", lambda *_: {"source_sha256": "fixed"})
    monkeypatch.setattr(replay, "evaluate", lambda *_: pytest.fail("replay called"))
    path = replay.run()
    assert json.loads((path / "results.json").read_text())["status"] == "plan_only"


def test_changed_pool_control_is_rejected(corpus):
    with pytest.raises(ValueError, match="control_pool_binding"):
        replay.evaluate(
            {"hybrid_ids": list(corpus)}, corpus, {"status": "ok", "candidate_pool_sha256": "wrong"}
        )
