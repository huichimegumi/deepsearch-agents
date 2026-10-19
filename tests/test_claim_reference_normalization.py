import json

import pytest

from app.agent.main_agent import CompressedEvidence, _render_validated_compression
from app.agent.runtime import ResearchBudget, ResearchBudgetLimits, ResearchRunTrace
from app.research.claims import ClaimDraft, ClaimIssueCode, validate_claims
from app.research.evidence import EvidenceRecord, EvidenceSource
from evals.reports_acceptance import replay_claims
from evals.runners.experiment import file_sha256

KNOWN = "ev1_local_document_" + "a" * 24
UNKNOWN = "ev1_local_document_" + "b" * 24


@pytest.mark.parametrize("source", ["local_document", "sql", "web", "fee_engine"])
def test_all_production_source_prefixes_require_exact_eligible_ids(source):
    evidence_id = f"ev1_{source}_{'a' * 24}"
    draft = ClaimDraft(text="fact", evidence_ids=[f"[{evidence_id}]"])
    assert validate_claims([draft], available_evidence_ids=[evidence_id]).accepted[
        0
    ].evidence_ids == (evidence_id,)
    assert not validate_claims([draft], available_evidence_ids=[]).accepted


def test_normalization_is_not_semantic_support_validation():
    report = validate_claims(
        [
            ClaimDraft(
                text="An unsupported invented document inventory", evidence_ids=[f"[{KNOWN}]"]
            )
        ],
        available_evidence_ids=[KNOWN],
    )
    assert len(report.accepted) == 1  # Structural linkage only, never entailment approval.


@pytest.mark.parametrize(
    "bad",
    [
        f"[{UNKNOWN}]",
        f"[[{KNOWN}]]",
        f"`[{KNOWN}]`",
        f"prefix [{KNOWN}]",
        f"[{KNOWN}] suffix",
        f"[{KNOWN} {UNKNOWN}]",
        f"[{KNOWN}][{UNKNOWN}]",
        f"[{KNOWN.upper()}]",
        f"[{KNOWN[:-1]}]",
        f"[ {KNOWN} ]",
        "[ev1_local_document_not-a-hash]",
        f"[{KNOWN}](https://example.com)",
    ],
)
def test_only_single_exact_known_wrapper_is_repaired(bad):
    result = validate_claims(
        [ClaimDraft(text="fact", evidence_ids=[bad])], available_evidence_ids=[KNOWN]
    )
    assert not result.accepted
    assert result.rejected[0].issues[0].code is ClaimIssueCode.UNKNOWN_EVIDENCE
    assert result.rejected[0].issues[0].detail == bad
    assert result.normalized_evidence_references == 0


def test_canonical_identity_deduplication_and_input_immutability():
    draft = ClaimDraft(text="fact", evidence_ids=[f" [{KNOWN}] ", KNOWN])
    before = draft.model_dump()
    repaired = validate_claims([draft], available_evidence_ids=[KNOWN])
    bare = validate_claims(
        [ClaimDraft(text="fact", evidence_ids=[KNOWN])], available_evidence_ids=[KNOWN]
    )
    assert repaired.accepted == bare.accepted
    assert repaired.accepted[0].evidence_ids == (KNOWN,)
    assert repaired.normalized_evidence_references == 1
    assert draft.model_dump() == before
    assert not validate_claims(
        [draft], available_evidence_ids=[KNOWN], normalize_known_wrappers=False
    ).accepted


def test_repair_never_bypasses_other_claim_gates():
    drafts = [
        ClaimDraft(text="unknown too", evidence_ids=[f"[{KNOWN}]", f"[{UNKNOWN}]"]),
        ClaimDraft(text="unbounded", evidence_ids=[f"[{KNOWN}]"], kind="inference"),
        ClaimDraft(text="missing", evidence_ids=[]),
    ]
    result = validate_claims(drafts, available_evidence_ids=[KNOWN])
    assert not result.accepted
    assert {issue.code for claim in result.rejected for issue in claim.issues} == {
        ClaimIssueCode.UNKNOWN_EVIDENCE,
        ClaimIssueCode.MISSING_INFERENCE_LIMITATION,
        ClaimIssueCode.MISSING_EVIDENCE,
    }
    assert result.rejected[0].draft.evidence_ids == drafts[0].evidence_ids


@pytest.mark.parametrize("capture", [False, True])
def test_renderer_keeps_canonical_ids_and_private_replay_inputs_out_of_telemetry(capture):
    trace = ResearchRunTrace(
        "run", "thread", "test", ResearchBudget(ResearchBudgetLimits("test", 60, 0, 0, 1, 4, 10))
    )
    record = EvidenceRecord.create(
        source=EvidenceSource.LOCAL_DOCUMENT, locator="document://test", content="private source"
    )
    trace.record_evidence((record,))
    trace.capture_claim_validation_inputs = capture
    parsed = CompressedEvidence(
        claims=[ClaimDraft(text="private claim", evidence_ids=[f"[{record.evidence_id}]"])]
    )
    markdown = _render_validated_compression(parsed, trace)
    assert f"[[{record.evidence_id}]]" not in markdown
    assert trace.claim_evidence_ids == [record.evidence_id]
    snapshot = trace.export_evidence_snapshot()
    assert len(snapshot["claim_validation_batches"]) == int(capture)
    if capture:
        assert snapshot["claim_validation_batches"][0]["drafts"][0]["evidence_ids"] == [
            f"[{record.evidence_id}]"
        ]
    telemetry = json.dumps(trace.finalize(status="completed", final_result=""))
    assert "private claim" not in telemetry
    assert "private source" not in telemetry
    assert trace.normalized_evidence_references == 1


def replay_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(replay_claims, "ROOT", tmp_path)
    directory = tmp_path / "evals/results/original/case"
    directory.mkdir(parents=True)
    snapshot = directory / "evidence.json"
    snapshot.write_text(
        json.dumps(
            {
                "records": [{"evidence_id": KNOWN}],
                "claim_validation_batches": [
                    {
                        "policy": "known_single_bracket_v1",
                        "drafts": [{"text": "fact", "evidence_ids": [f"[{KNOWN}]"]}],
                        "available_evidence_ids": [KNOWN],
                        "accepted_count": 1,
                        "rejected_count": 0,
                        "normalized_evidence_references": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    results = directory.parent / "results.json"
    results.write_text(
        json.dumps(
            {
                "run_id": "original",
                "manifest": {},
                "results": [
                    {
                        "id": "case",
                        "review_directory": "evals/results/original/case",
                        "evidence_sha256": file_sha256(snapshot),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return results, snapshot


def test_exact_same_saved_drafts_replay_without_calls(tmp_path, monkeypatch):
    results, _ = replay_fixture(tmp_path, monkeypatch)
    report = replay_claims.replay(results)
    batch = report["results"][0]["batches"][0]
    assert batch["exact"]["accepted"] == 0
    assert batch["canonical"]["accepted"] == 1
    assert report["semantic_acceptance"] == "pending_human_review"


def test_missing_compression_is_not_counted_as_a_successful_replay(tmp_path, monkeypatch):
    results, snapshot = replay_fixture(tmp_path, monkeypatch)
    saved = json.loads(snapshot.read_text())
    saved["claim_validation_batches"] = []
    snapshot.write_text(json.dumps(saved), encoding="utf-8")
    report = json.loads(results.read_text())
    report["results"][0]["evidence_sha256"] = file_sha256(snapshot)
    results.write_text(json.dumps(report), encoding="utf-8")
    replayed = replay_claims.replay(results)
    assert replayed["results"][0]["status"] == "no_validation_batches"
    assert replayed["results"][0]["batches"] == []


@pytest.mark.parametrize("failure", ["hash", "legacy", "mismatch", "unknown_eligible", "outside"])
def test_replay_rejects_missing_or_changed_inputs(tmp_path, monkeypatch, failure):
    results, snapshot = replay_fixture(tmp_path, monkeypatch)
    saved = json.loads(snapshot.read_text())
    report = json.loads(results.read_text())
    if failure == "legacy":
        del saved["claim_validation_batches"]
    elif failure == "mismatch":
        saved["claim_validation_batches"][0]["accepted_count"] = 0
    elif failure == "unknown_eligible":
        saved["claim_validation_batches"][0]["available_evidence_ids"] = [UNKNOWN]
    elif failure == "outside":
        report["results"][0]["review_directory"] = "outside"
    snapshot.write_text(json.dumps(saved), encoding="utf-8")
    report["results"][0]["evidence_sha256"] = (
        "0" * 64 if failure == "hash" else file_sha256(snapshot)
    )
    results.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError):
        replay_claims.replay(results)
