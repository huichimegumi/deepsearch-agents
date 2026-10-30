import json

import pytest

from app.agent.runtime import ResearchBudget, ResearchBudgetLimits, ResearchRunTrace
from app.research.evidence.models import EvidenceRecord, EvidenceSource
from evals.reports_acceptance import run as runner
from evals.reports_acceptance.run import DEFAULT_DATASET, load_cases
from evals.reports_acceptance.scoring import audit_report, review_worksheet


def fixture_case():
    return {
        "id": "case",
        "question": "question",
        "answerable": True,
        "answer_keypoints": ["Required fact"],
        "evidence_units": [
            {"id": "fact", "locations": [{"document_sha256": "a" * 64, "anchor": "fact"}]}
        ],
    }


def record():
    return EvidenceRecord.create(
        source=EvidenceSource.LOCAL_DOCUMENT,
        locator=f"document://sha256/{'a' * 64}#chunk=0",
        content="source fact",
    )


def test_snapshot_contains_content_but_trace_does_not():
    limits = ResearchBudgetLimits("quick", 10, 0, 0, 1, 2, 1)
    trace = ResearchRunTrace("run", "thread", "quick", ResearchBudget(limits))
    trace.record_evidence((record(), record()))
    assert trace.export_evidence_snapshot()["records"] == [record().to_dict()]
    assert "source fact" not in json.dumps(trace.finalize(status="completed", final_result=""))


def test_resolving_citations_never_auto_approves_answer():
    evidence = record()
    audit = audit_report(
        f"Wrong answer [{evidence.evidence_id}]", {"records": [evidence.to_dict()]}, fixture_case()
    )
    assert audit["citation_ids_resolve"] is True
    assert audit["all_reference_units_cited"] is True
    assert audit["claim_entailment"] == "pending_human_review"
    assert audit["acceptance"] == "pending_human_review"


def test_unknown_citations_and_missing_snapshot():
    audit = audit_report("[ev1_local_document_unknown]", None, fixture_case())
    assert audit["unknown_cited_ids"] == ["ev1_local_document_unknown"]
    assert audit["citation_ids_resolve"] is None
    assert not audit["evidence_snapshot_present"]


def test_retrieved_but_not_cited_is_distinct():
    audit = audit_report("uncited answer", {"records": [record().to_dict()]}, fixture_case())
    assert audit["all_reference_units_retrieved"] is True
    assert audit["all_reference_units_cited"] is False
    assert audit["missing_required_citations"] is True


def test_wrong_document_not_credited():
    evidence = record().to_dict()
    evidence["locator"] = f"document://sha256/{'b' * 64}#chunk=0"
    assert not audit_report("report", {"records": [evidence]}, fixture_case())[
        "all_reference_units_retrieved"
    ]


def test_no_answer_requires_manual_abstention_review():
    case = {**fixture_case(), "answerable": False, "evidence_units": [], "answer_keypoints": []}
    audit = audit_report("Invented answer", {"records": []}, case)
    assert audit["all_reference_units_cited"] is None
    assert audit["appropriate_abstention"] == "pending_human_review"
    worksheet = review_worksheet(case, audit)
    assert "- [x]" not in worksheet
    assert "invents no answer" in worksheet


def test_frozen_local_suite_has_six_cases_and_no_gold_in_prompt():
    suite, cases = load_cases(DEFAULT_DATASET)
    assert len(cases) == 6
    assert sum(not case["answerable"] for case in cases) == 1
    for case in cases:
        prompt = suite["prompt_template"].format(question=case["question"])
        for unit in case["evidence_units"]:
            for location in unit["locations"]:
                assert location["anchor"] not in prompt
                assert location["document_sha256"] not in prompt


def test_reference_changes_rejected(tmp_path):
    suite = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))
    suite["reference_sha256"] = "0" * 64
    path = tmp_path / "suite.json"
    path.write_text(json.dumps(suite), encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        load_cases(path)


async def test_real_runner_saves_failure_package_without_provider_error(tmp_path, monkeypatch):
    async def failed(*args, **kwargs):
        assert kwargs["export_evaluation_evidence"] is True
        assert kwargs["research_limits_override"].max_search_queries == 0
        assert kwargs["research_limits_override"].max_fetched_pages == 0
        raise RuntimeError("private provider response")

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "run_deep_agent", failed)
    directory = tmp_path / "case"
    row = await runner.execute_case(fixture_case(), "prompt", "session", directory, 10)
    assert row["error_type"] == "RuntimeError"
    assert row["execution_status"] == "missing_trace"
    assert row["audit"]["report_nonempty"] is False
    assert "private provider response" not in json.dumps(row)
    assert (directory / "REVIEW.md").is_file()


async def test_runner_uses_actual_report_and_saved_evidence(tmp_path, monkeypatch):
    evidence = record()
    session_dir = tmp_path / "app/output/user_evals/session_session"

    async def completed(*args, **kwargs):
        session_dir.mkdir(parents=True)
        (session_dir / "evaluation_evidence.json").write_text(
            json.dumps({"records": [evidence.to_dict()]}), encoding="utf-8"
        )
        (session_dir / "research_trace.json").write_text(
            json.dumps({"status": "completed"}), encoding="utf-8"
        )
        return f"actual returned report [{evidence.evidence_id}]"

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "run_deep_agent", completed)
    directory = tmp_path / "case"
    row = await runner.execute_case(fixture_case(), "prompt", "session", directory, 10)
    assert row["execution_status"] == "completed"
    assert row["audit"]["all_reference_units_cited"] is True
    assert (directory / "report.md").read_text(encoding="utf-8").startswith("actual returned")
    assert (
        json.loads((directory / "evidence.json").read_text())["records"][0]["content"]
        == "source fact"
    )
    assert row["audit"]["acceptance"] == "pending_human_review"


async def test_runner_forwards_explicit_required_sources(tmp_path, monkeypatch):
    seen = []

    async def execute(*args, **kwargs):
        seen.append(kwargs.get("required_evidence_sources"))
        return None

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "run_deep_agent", execute)
    await runner.execute_case(
        fixture_case(),
        "prompt",
        "session",
        tmp_path / "case",
        10,
        required_evidence_sources=("sql", "local_document"),
    )
    assert seen == [("sql", "local_document")]
