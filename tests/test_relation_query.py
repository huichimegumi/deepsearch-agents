import copy
import json
from types import SimpleNamespace

import pytest

from evals.rag import run_relation_query as rq


@pytest.mark.parametrize(
    "query,expected",
    [
        (
            "《报告2025》对2024年调查有什么描述？不要推断。",
            "文档1对2024年调查有什么描述？不要推断。",
        ),
        (
            "列出《白皮书》目录第一、二章标题。不要据目录推断正文。",
            "列出文档1目录第一、二章标题。不要据目录推断正文。",
        ),
        ("对比《A》与《B》，再看《A》。", "对比文档1与文档2，再看文档1。"),
        ("对比数字人直播白皮书和全球电商AI应用报告", "对比数字人直播白皮书和全球电商AI应用报告"),
        (
            "是否包含火星移民电商直播？如果没有依据，请说明。",
            "是否包含火星移民电商直播？如果没有依据，请说明。",
        ),
    ],
)
def test_relation_transform_preserves_relation_constraints_and_does_not_guess(query, expected):
    assert rq.relation_query(query) == expected


def setup_pair(monkeypatch, query="《Source》 relation?"):
    calls = []
    policy = {"hits": [{"chunk_id": "a", "content": "raw"}], "metrics": None}
    output = {
        "id": "one",
        "status": "ok",
        "local_rerank_calls": 2,
        "candidate_pool_sha256": "pool",
        "pool_order_source": "saved",
        "policies": {"baseline": policy, "source_context": policy},
    }
    task = {"id": "one", "query": query, "case": {"SECRET": "EVALUATOR_ONLY"}}

    def evaluate(actual_task, corpus):
        calls.append(copy.deepcopy(actual_task))
        assert corpus == {"a": "raw"}
        assert actual_task["case"] == task["case"]
        return copy.deepcopy(output)

    monkeypatch.setattr(rq.context, "evaluate", evaluate)
    return task, output, calls


def test_factorial_pair_changes_only_query_and_keeps_controls(monkeypatch):
    task, control, calls = setup_pair(monkeypatch)
    result = rq.evaluate(task, {"a": "raw"}, control)
    assert [c["query"] for c in calls] == ["《Source》 relation?", "文档1 relation?"]
    assert calls[0]["case"] == calls[1]["case"]
    assert result["local_rerank_calls"] == 4
    assert result["status"] == "ok"
    assert set(result["policies"]) == set(rq.POLICIES)
    assert all(result["historical_delivery_controls_equal"].values())
    assert "EVALUATOR_ONLY" not in rq.relation_query(task["query"])
    assert not result["relation_reused_current_controls"]


def test_noop_reuses_current_controls_without_extra_inference(monkeypatch):
    task, control, calls = setup_pair(monkeypatch, query="unquoted question")
    result = rq.evaluate(task, {"a": "raw"}, control)
    assert len(calls) == 1 and result["local_rerank_calls"] == 2
    assert result["relation_reused_current_controls"]
    assert result["policies"]["original_raw"] == result["policies"]["relation_raw"]
    assert result["policies"]["original_raw"] is not result["policies"]["relation_raw"]


def test_changed_delivery_control_invalidates_row(monkeypatch):
    task, control, _ = setup_pair(monkeypatch)
    control = copy.deepcopy(control)
    control["policies"]["source_context"]["hits"] = []
    result = rq.evaluate(task, {"a": "raw"}, control)
    assert result["status"] == "invalid"
    assert not result["historical_delivery_controls_equal"]["original_context"]


def test_relation_fallback_preserves_attempted_call_count(monkeypatch):
    task, control, _ = setup_pair(monkeypatch)
    calls = []

    def evaluate(*_):
        calls.append(1)
        return (
            copy.deepcopy(control)
            if len(calls) == 1
            else {
                "id": "one",
                "status": "invalid",
                "local_rerank_calls": 1,
                "error_type": "reranker_fallback_not_an_experiment",
            }
        )

    monkeypatch.setattr(rq.context, "evaluate", evaluate)
    result = rq.evaluate(task, {"a": "raw"}, control)
    assert result["status"] == "invalid" and result["local_rerank_calls"] == 3


def test_plan_has_no_model_or_configuration_calls(monkeypatch, tmp_path):
    monkeypatch.setattr(rq, "ROOT", tmp_path)
    monkeypatch.setattr(rq, "load_inputs", lambda **_: ([], {}, {}, {}))
    monkeypatch.setattr(rq, "build_manifest", lambda *_: {"source_sha256": "fixed"})
    monkeypatch.setattr(rq, "verify_configuration", lambda: pytest.fail("configuration"))
    monkeypatch.setattr(rq.context, "model_artifacts", lambda: pytest.fail("model artifacts"))
    monkeypatch.setattr(rq, "evaluate", lambda *_: pytest.fail("inference"))
    path = rq.run()
    assert json.loads((path / "results.json").read_text())["status"] == "plan_only"


def test_historical_control_hash_checked_before_use(monkeypatch, tmp_path):
    monkeypatch.setattr(rq, "ROOT", tmp_path)
    report = tmp_path / "report.json"
    report.write_text('{"development_run":"saved","development_results_sha256":"wrong"}')
    monkeypatch.setattr(rq, "REPORT", report)
    monkeypatch.setattr(rq.context, "load_pools", lambda **_: ([], {}, {}))
    path = tmp_path / "evals/results/saved/results.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}")
    with pytest.raises(ValueError, match="historical_context_control_changed"):
        rq.load_inputs()


def test_budget_change_rejected(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(rag_answer_max_hits=7))
    with pytest.raises(ValueError, match="configuration_changed"):
        rq.verify_configuration()
