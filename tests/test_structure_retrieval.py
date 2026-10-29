from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.rag import structure_retrieval as sr
from app.rag.retrieval import CandidatePool, RetrievedChunk
from app.research.evidence import retrieved_chunks_to_evidence

TOC = "目录\n01 第一主题\n02 第二主题"


@pytest.fixture
def live(monkeypatch):
    document = SimpleNamespace(id="doc", filename="Report.pdf", sha256="hash")
    foreign = SimpleNamespace(id="foreign-doc", filename="Other.pdf", sha256="foreign")

    def chunk(i, content):
        return SimpleNamespace(
            id=i,
            content=content,
            chunk_index=0 if i == "toc" else 1,
            page_start=1,
            page_end=1,
            section=None,
        )

    rows = {
        "toc": (chunk("toc", TOC), document),
        "body": (chunk("body", "body"), document),
        "foreign": (chunk("foreign", "other"), foreign),
    }
    pool = CandidatePool(list(rows), list(rows), rows)
    baseline = [
        RetrievedChunk(
            "body",
            "body",
            "Report.pdf",
            1,
            1,
            None,
            5,
            document_sha256="hash",
            chunk_index=1,
            rerank_applied=True,
        )
    ]
    calls = []
    monkeypatch.setattr(sr, "collect_candidates", lambda q, kb: (calls.append((q, kb)), pool)[1])

    def rank(q, values, *, diagnostics):
        calls.append("rank")
        diagnostics.update(
            reranked_ids=["foreign", "body", "toc"],
            rerank_scores={"foreign": 8, "body": 5, "toc": 0.2},
            rerank_applied=True,
        )
        return baseline

    monkeypatch.setattr(sr, "_rank_candidates", rank)
    monkeypatch.setattr(sr, "_load_documents", lambda _: [document, foreign])
    monkeypatch.setattr(sr, "_load_source_chunks", lambda *_: [rows["toc"], rows["body"]])
    return rows, pool, baseline, calls


def test_live_path_has_one_recall_and_rerank_and_explicit_score_bypass(live):
    _, _, _, calls = live
    details = {}
    result = sr.search_source_structure("《Report》目录", ["kb"], diagnostics=details)
    assert calls == [("《Report》目录", ["kb"]), "rank"]
    assert [h.chunk_id for h in result] == ["toc", "body"]
    assert result[0].score == 0.2 and result[0].rerank_applied
    records = retrieved_chunks_to_evidence(result, knowledge_base_ids=["kb"], query="q")
    assert records[0].metadata["retrieval_method"] == "explicit_toc_structure"
    assert records[0].metadata["semantic_score_gate_bypassed"] is True
    assert records[1].metadata["semantic_score_gate_bypassed"] is False
    assert details["source_structure"]["semantic_score_gate_bypassed_ids"] == ["toc"]


def test_unresolved_source_falls_back_without_body_read(live, monkeypatch):
    _, _, baseline, _ = live
    monkeypatch.setattr(sr, "_load_source_chunks", lambda *_: pytest.fail("body read"))
    details = {}
    assert sr.search_source_structure("《Unknown》目录", ["kb"], diagnostics=details) == baseline
    assert details["source_structure"]["status"] == "unresolved_source"


def test_live_path_accepts_attested_suffix_metadata(live):
    rows, _, _, _ = live
    document = rows["body"][1]
    document.filename = "Report17页.pdf"
    document.indexed_page_end = 17
    details = {}
    result = sr.search_source_structure("《Report》应用场景", ["kb"], diagnostics=details)
    assert [h.chunk_id for h in result] == ["body"]
    assert details["source_structure"]["resolution_methods"] == ("indexed_page_suffix",)


def test_negated_toc_in_live_path_does_not_read_structure(live, monkeypatch):
    monkeypatch.setattr(sr, "_load_source_chunks", lambda *_: pytest.fail("negated TOC body scan"))
    details = {}
    result = sr.search_source_structure(
        "《Report》请先不要生成目录，只概括场景。", ["kb"], diagnostics=details
    )
    assert [h.chunk_id for h in result] == ["body"]
    assert details["source_structure"]["structure_status"] == "not_requested"


@pytest.mark.parametrize("failure", ["document_limit", "chunk_limit", "outside_pool", "fallback"])
def test_bounded_inventory_and_availability_fallbacks(live, monkeypatch, failure):
    rows, pool, baseline, _ = live
    if failure == "document_limit":
        monkeypatch.setattr(sr, "DOCUMENT_LIMIT", 1)
    elif failure == "chunk_limit":
        monkeypatch.setattr(sr, "STRUCTURE_CHUNK_LIMIT", 1)
    elif failure == "outside_pool":
        rows["toc"][0].id = "outside"
        del pool.rows["toc"]
        pool.hybrid_ids.remove("toc")

        def rank(*_, diagnostics):
            diagnostics.update(
                reranked_ids=["body"], rerank_scores={"body": 5}, rerank_applied=True
            )
            return baseline

        monkeypatch.setattr(sr, "_rank_candidates", rank)
        monkeypatch.setattr(
            sr,
            "_load_source_chunks",
            lambda *_: [(SimpleNamespace(id="outside", content=TOC), rows["body"][1])],
        )
    else:

        def rank(*_, diagnostics):
            diagnostics.update(rerank_applied=False)
            return baseline

        monkeypatch.setattr(sr, "_rank_candidates", rank)
        monkeypatch.setattr(sr, "_load_documents", lambda _: pytest.fail("inventory on fallback"))
    details = {}
    result = sr.search_source_structure("《Report》目录", ["kb"], diagnostics=details)
    assert all(h.chunk_id != "toc" for h in result)
    plan = details["source_structure"]
    assert plan.get("status") in {"resolved", "document_inventory_limit", "reranker_unavailable"}
    if failure in {"chunk_limit", "outside_pool"}:
        assert plan["structure_status"] in {"structure_inventory_limit", "structure_outside_pool"}


def test_database_reads_are_ready_scoped_and_bounded(monkeypatch):
    from app.rag.models import Base, Chunk, Document, KnowledgeBase

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[KnowledgeBase.__table__, Document.__table__, Chunk.__table__]
    )
    with Session(engine) as session:
        for i, kb, status in [
            ("a", "allowed", "ready"),
            ("b", "other", "ready"),
            ("c", "allowed", "pending"),
        ]:
            session.add(
                Document(
                    id=i,
                    knowledge_base_id=kb,
                    filename=i + ".pdf",
                    object_key=i,
                    size_bytes=1,
                    sha256=i,
                    status=status,
                )
            )
            session.add(
                Chunk(
                    id=i,
                    document_id=i,
                    knowledge_base_id=kb,
                    chunk_index=0,
                    content=TOC,
                    lexical_text="toc",
                    token_count=1,
                    page_end=17 if i == "a" else 999,
                )
            )
        session.add(
            Chunk(
                id="mismatched",
                document_id="a",
                knowledge_base_id="other",
                chunk_index=1,
                content=TOC,
                lexical_text="toc",
                token_count=1,
                page_end=999,
            )
        )
        session.commit()

    @contextmanager
    def scope():
        with Session(engine, expire_on_commit=False) as session:
            yield session

    monkeypatch.setattr(sr, "session_scope", scope)
    assert [d.id for d in sr._load_documents(["allowed"])] == ["a"]
    assert sr._load_documents(["allowed"])[0].indexed_page_end == 17
    assert [c.id for c, _ in sr._load_source_chunks(["allowed"], ["a", "b", "c"])] == ["a"]
    monkeypatch.setattr(sr, "DOCUMENT_LIMIT", 0)
    assert len(sr._load_documents(["allowed"])) == 1  # limit + one overflow sentinel


def test_evidence_tool_opt_in_preserves_order_and_default_is_unchanged(monkeypatch):
    from app.tools import evidence_tool as et

    toc = RetrievedChunk(
        "toc",
        TOC,
        "Report.pdf",
        1,
        1,
        None,
        0.2,
        document_sha256="hash",
        chunk_index=0,
        rerank_applied=True,
        retrieval_method="explicit_toc_structure",
    )
    body = RetrievedChunk(
        "body", "body", "Report.pdf", 2, 2, None, 5, document_sha256="hash", chunk_index=1
    )
    monkeypatch.setattr(et, "_resolve_knowledge_bases", lambda _: [SimpleNamespace(id="kb")])
    monkeypatch.setattr(et, "hybrid_search", lambda *_: [body])

    def experimental(*_, diagnostics):
        diagnostics["source_structure"] = {"status": "resolved", "structure_status": "selected"}
        return [toc, body]

    monkeypatch.setattr(sr, "search_source_structure", experimental)
    ordinary = et._collect_local_documents("q", "kb")
    assert [r.metadata["chunk_id"] for r in ordinary.records] == ["body"]
    details = {}
    result = et._collect_local_documents(
        "q", "kb", experimental_source_structure=True, diagnostics=details
    )
    assert [r.metadata["chunk_id"] for r in result.records] == ["toc", "body"]
    expected = retrieved_chunks_to_evidence([toc], knowledge_base_ids=["old"], query="old")[0]
    assert result.records[0].evidence_id == expected.evidence_id
    assert details["delivered_ids"] == ["toc", "body"]
