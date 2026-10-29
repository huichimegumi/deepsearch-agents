import pytest

from app.rag.source_structure import (
    document_inventory,
    indexed_page_suffix_key,
    is_toc,
    requests_toc,
    resolve_document_sources,
)
from evals.rag.source_structure_challenges import evaluate


@pytest.mark.parametrize(
    "filename,page,expected",
    [
        ("Report17页.pdf", 17, "report"),
        ("研究报告63页.PDF", 63, "研究报告"),
        ("Report17页.pdf", 16, None),
        ("Report17页.pdf", None, None),
        ("Report17页.pdf", 17.0, None),
        ("Report1页.pdf", True, None),
        ("Report第17页.pdf", 17, None),
        ("Report017页.pdf", 17, None),
        ("Report2026.pdf", 2026, None),
    ],
)
def test_suffix_requires_indexed_page_attestation(filename, page, expected):
    assert indexed_page_suffix_key(filename, page) == expected


def test_alias_opt_in_and_exact_alias_collision_are_explicit():
    docs = [{"filename": "Report17页.pdf", "document_sha256": "doc", "indexed_page_end": 17}]
    assert resolve_document_sources("《Report》", docs).status == "unresolved_source"
    result = resolve_document_sources("《Report》", docs, allow_page_suffix=True)
    assert result.status == "resolved" and result.resolution_methods == ("indexed_page_suffix",)
    assert resolve_document_sources(
        "《Report17页》", docs, allow_page_suffix=True
    ).resolution_methods == ("exact_filename",)
    docs.append({"filename": "Report.pdf", "document_sha256": "foreign"})
    assert (
        resolve_document_sources("《Report》", docs, allow_page_suffix=True).status
        == "ambiguous_source"
    )


def test_inventory_uses_scoped_indexed_last_page_without_source_text():
    corpus = {
        "a": {"filename": "Report17页.pdf", "document_sha256": "doc", "page_end": 1},
        "b": {"filename": "Report17页.pdf", "document_sha256": "doc", "page_end": 17},
    }
    inventory = document_inventory(corpus)
    assert inventory == [
        {"filename": "Report17页.pdf", "document_sha256": "doc", "indexed_page_end": 17}
    ]
    assert (
        resolve_document_sources("《Report2025》", inventory, allow_page_suffix=True).status
        == "unresolved_source"
    )


@pytest.mark.parametrize(
    "query",
    [
        "请先不要生成目录，只概括场景。",
        "目录不用列，请概括场景。",
        "无需目录，只分析应用。",
        "Summarize without a table of contents.",
        "No table of contents, please.",
        "请勿列出目录，只说明实践。",
        "勿给出目录，概括方法。",
    ],
)
def test_negated_structural_request_does_not_reserve(query):
    assert not requests_toc(query)


def test_number_spelling_does_not_create_fake_distinct_entries():
    assert not is_toc("目录\n01 一个条目\n1 同一个编号")
    assert not is_toc("目录\n第01章 一个条目\n第1章 相同编号")
    assert is_toc("目录\n01 第一条\n02 第二条")


def test_separate_is_not_a_negative_but_polite_dont_still_is():
    assert requests_toc("分别列出目录第一、二章与第三、四章的标题。不要据目录推断正文。")
    assert not requests_toc("请先别生成目录。")


def test_challenge_fixture_is_separate_from_original_and_unknown_mutations_fail():
    corpus = {
        "a": {"filename": "Report.pdf", "document_sha256": "doc", "content": "目录\n01 A\n02 B"}
    }
    case = {
        "id": "ambiguous",
        "query": "《Report》目录",
        "mutation": "duplicate_toc",
        "expected": {"status": "resolved", "structure_status": "ambiguous_structure"},
    }
    assert evaluate(case, corpus)["passed"]
    assert len(corpus) == 1
    with pytest.raises(ValueError, match="unknown_fixture_mutation"):
        evaluate({**case, "mutation": "not_supported"}, corpus)
