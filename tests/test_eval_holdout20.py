"""Once-only public task selection and the frozen workflow comparison switch."""

from evals.dabstep.common import HERE, load_jsonl
from evals.dabstep.holdout20 import task_for, validate_selection
from evals.score_v3 import checklist_items
from evals.simple_sql_baseline import collect_public_evidence


def test_holdout_is_disjoint_and_has_scorable_source_labels():
    selected = validate_selection()["cases"]
    exposed = {row["benchmark_id"] for row in load_jsonl(HERE / "selected_tasks.jsonl")}
    assert len(selected) == len({row["id"] for row in selected}) == 20
    assert not exposed.intersection(row["id"] for row in selected)
    assert {row["type"] for row in selected} == {
        "Data Analysis",
        "Data Insight",
        "Data Preparation",
        "Report Generation",
    }
    for row in selected:
        assert task_for(row["id"])
        assert checklist_items(row["id"])


def test_p2_and_p4_flows_share_sql_evidence():
    baseline = collect_public_evidence(include_fee=False)
    final = collect_public_evidence(include_fee=True)
    assert final[: len(baseline)] == baseline
    assert all(row["source"] == "fee_engine" for row in final[len(baseline) :])
