"""Frozen scoring arithmetic and citation checks."""

import pytest

from evals.score_v3 import (
    ChecklistJudgement,
    CriterionGrade,
    aggregate_grades,
    checklist_items,
    citation_metrics,
)


def test_scoring_distinguishes_supported_partial_and_missing() -> None:
    items = ["grounded fact", "incomplete answer", "omitted item"]
    judgement = ChecklistJudgement(
        grades=[
            CriterionGrade(index=1, coverage="full", supported=True, reason="source agrees"),
            CriterionGrade(index=2, coverage="partial", supported=False, reason="no source"),
            CriterionGrade(index=3, coverage="missing", supported=False, reason="absent"),
        ]
    )
    scores = aggregate_grades(items, judgement)
    assert scores["checklist_coverage"] == 0.5
    assert scores["supported_coverage"] == 0.333


def test_scoring_rejects_missing_judge_item() -> None:
    judgement = ChecklistJudgement(
        grades=[CriterionGrade(index=1, coverage="full", supported=True, reason="okay")]
    )
    with pytest.raises(ValueError, match="judge_grade_index_mismatch"):
        aggregate_grades(["first", "second"], judgement)


def test_citation_ids_must_come_from_current_case_evidence() -> None:
    good = "ev1_sql_abc123"
    bad = "ev1_sql_other123"
    metrics = citation_metrics(
        f"Value [{good}], invented [{bad}], repeated [{good}]", [{"evidence_id": good}]
    )
    assert metrics["cited_ids"] == 2
    assert metrics["citation_id_validity"] == 0.5
    assert metrics["invalid_cited_ids"] == [bad]


def test_dabstep_selection_has_nonempty_frozen_checklists() -> None:
    assert len(checklist_items("dabstep_research_002")) >= 5
