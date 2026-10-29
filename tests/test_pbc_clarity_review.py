import pytest

from evals.reports_acceptance.pbc_clarity_review import (
    check_methods,
    check_titles,
    index_titles,
)

INDEX = (
    "VI\n专栏\n"
    "专栏 1 财政金融协同 ........ 14\n"
    "专栏 2 绿色金融 ........ 17\n"
    "专栏 3 流动性总量 ........ 26\n"
    "专栏 4 信用修复 ........ 37\n"
)


def test_four_headings_require_exact_index_titles_and_index_citations():
    titles = index_titles(INDEX)
    assertions = [
        {
            "assertion_id": f"a{i:02}",
            "text": f"专栏{i}的标题是{title}。",
            "evidence_ids": ["toc"],
        }
        for i, title in titles.items()
    ]
    assert check_titles(assertions, titles, "toc")["complete_index_bound"]
    wrong = [*assertions]
    wrong[1] = {**wrong[1], "text": "专栏2的标题是财政金融协同。"}
    assert not check_titles(wrong, titles, "toc")["complete_index_bound"]
    assert not check_titles(assertions, titles, None)["complete_index_bound"]


def test_column_index_rejects_missing_or_duplicate_entries():
    with pytest.raises(ValueError, match="four_column_titles_not_found"):
        index_titles(INDEX.replace("专栏 4 信用修复 ........ 37\n", ""))
    with pytest.raises(ValueError, match="duplicate_column_index_number"):
        index_titles(INDEX + "专栏 4 另一标题 ........ 40\n")


def test_method_sentence_must_be_in_its_cited_passage():
    records = [
        {"evidence_id": "a", "content": "通过担保等增信方式分担风险成本。"},
        {"evidence_id": "b", "content": "另一页只谈融资成本。"},
    ]
    assertion = {
        "assertion_id": "a01",
        "text": "通过担保等增信方式分担风险成本。",
        "evidence_ids": ["b"],
    }
    result = check_methods([assertion], records)["assertions"][0]
    assert not result["literal_in_cited_passage"]
    assert result["literal_in_other_delivered_passage"]
    with pytest.raises(ValueError, match="method_assertion_has_unbound_evidence"):
        check_methods([{**assertion, "evidence_ids": ["unknown"]}], records)
