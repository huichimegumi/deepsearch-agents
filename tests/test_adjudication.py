import json
from copy import deepcopy

import pytest

from evals.reports_acceptance import adjudication as human
from evals.reports_acceptance import support_review as support
from evals.runners.experiment import file_sha256
from tests.test_support_review import ID, review


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(human, "ROOT", tmp_path)
    dataset = write(tmp_path / "suite.json", {})
    monkeypatch.setattr(support, "DEFAULT_DATASET", dataset)
    case = {
        "id": "case",
        "question": "question",
        "answerable": True,
        "evidence_units": [{"id": "key", "keypoint": "fact"}],
    }
    monkeypatch.setattr(support, "load_cases", lambda _: ({}, [case]))
    directory = tmp_path / "evals/results/original/case"
    directory.mkdir(parents=True)
    report = f"# Title\nFact [{ID}]"
    (directory / "report.md").write_text(report, encoding="utf-8")
    snapshot = {
        "records": [
            {
                "evidence_id": ID,
                "content": "Original source fact",
                "metadata": {},
                "source": "local_document",
            }
        ]
    }
    write(directory / "evidence.json", snapshot)
    row = {
        "id": "case",
        "review_directory": "evals/results/original/case",
        "report_sha256": file_sha256(directory / "report.md"),
        "evidence_sha256": file_sha256(directory / "evidence.json"),
    }
    manifest = {"dataset_sha256": file_sha256(dataset)}
    write(
        directory.parent / "results.json",
        {"run_id": "original", "inputs_unchanged": True, "manifest": manifest, "results": [row]},
    )
    packet_dir = tmp_path / "evals/results/support"
    packet_dir.mkdir()
    payload = support.prepare_input(
        report, snapshot, case, [{"sha256": "a", "filename": "real.pdf"}]
    )
    write(packet_dir / "review_input.json", payload)
    packet_path = write(
        packet_dir / "results.json",
        {
            "original_run_id": "original",
            "case_id": "case",
            "inputs_unchanged": True,
            "status": "not_requested",
            "review_scope": "whole_saved_report_body",
            "review_input_sha256": file_sha256(packet_dir / "review_input.json"),
            "execution_manifest": manifest,
            "report_sha256": row["report_sha256"],
            "evidence_sha256": row["evidence_sha256"],
        },
    )
    batch = human.initialize([packet_path])
    decision = review().model_dump()
    decision.update(
        item_id="item_001",
        reference_labels="confirmed",
        decision="accepted",
        decision_reason="Reviewed whole report",
    )
    decision["segments"][0].update(error_tags=[], correction="")
    annotation = {
        "schema_version": 1,
        "batch_sha256": file_sha256(batch),
        "stage": "annotation",
        "reviewer": "synthetic-test-reviewer",
        "reviewed_at": "2026-10-26T10:00:00+09:00",
        "attestation": "I personally reviewed the report and cited evidence",
        "prior_annotations": [],
        "items": [decision],
    }
    return batch, annotation, packet_path


def submit(batch, annotation):
    return write(batch.parent / "filled.json", annotation)


def final(batch, annotation):
    prior = submit(batch, annotation)
    value = deepcopy(annotation)
    value.update(
        stage="adjudication",
        prior_annotations=[
            {"path": prior.relative_to(human.ROOT).as_posix(), "sha256": file_sha256(prior)}
        ],
    )
    return write(batch.parent / "final.json", value)


def test_template_is_pending_invalid_and_originals_unchanged(fixture):
    batch, _, packet = fixture
    before = packet.read_bytes()
    template = batch.parent / "annotation.template.json"
    assert json.loads(template.read_text())["items"][0]["decision"] is None
    with pytest.raises(ValueError):
        human.validate_annotation(template, batch)
    summary = human.summarize(batch)
    assert summary["pending_report_scopes"] == 1
    assert summary["acceptance_rate"] is None
    assert summary["acceptance_denominator"] == 0
    assert packet.read_bytes() == before


def test_annotation_cannot_be_reported_as_final_and_final_is_self_attested(fixture):
    batch, value, _ = fixture
    human.validate_annotation(submit(batch, value), batch)
    with pytest.raises(ValueError, match="explicit adjudication"):
        human.summarize(batch, submit(batch, value))
    result = human.summarize(batch, final(batch, value))
    assert result["acceptance_numerator"] == result["acceptance_denominator"] == 1
    assert result["review_status"] == "adjudicated_self_attested"


@pytest.mark.parametrize(
    "failure",
    [
        "blank_reviewer",
        "timezone",
        "attestation",
        "batch_hash",
        "missing_item",
        "duplicate_item",
        "missing_segment",
        "invented_quote",
        "uncited_quote",
        "missing_keypoint",
        "blank_reason",
        "accepted_uncertain",
        "accepted_bad_reference",
        "accepted_failure",
        "accepted_error_tag",
        "unjustified_rejection",
    ],
)
def test_invalid_annotations_are_rejected(fixture, failure):
    batch, value, _ = fixture
    item = value["items"][0]
    segment = item["segments"][0]
    if failure == "blank_reviewer":
        value["reviewer"] = "  "
    elif failure == "timezone":
        value["reviewed_at"] = "2026-10-26T10:00:00"
    elif failure == "attestation":
        value["attestation"] = "model generated"
    elif failure == "batch_hash":
        value["batch_sha256"] = "changed"
    elif failure == "missing_item":
        value["items"] = []
    elif failure == "duplicate_item":
        value["items"].append(deepcopy(item))
    elif failure == "missing_segment":
        item["segments"] = []
    elif failure == "invented_quote":
        segment["report_quote"] = "not in report"
    elif failure == "uncited_quote":
        segment["evidence_quotes"][0]["evidence_id"] = "unknown"
    elif failure == "missing_keypoint":
        item["keypoints"] = []
    elif failure == "blank_reason":
        item["decision_reason"] = " "
    elif failure == "accepted_uncertain":
        segment["verdict"] = "uncertain"
    elif failure == "accepted_bad_reference":
        item["reference_labels"] = "uncertain"
    elif failure == "accepted_failure":
        segment.update(
            verdict="unsupported", error_tags=["scope_overclaim"], correction="Limit scope"
        )
    elif failure == "accepted_error_tag":
        segment["error_tags"] = ["numeric_error"]
    elif failure == "unjustified_rejection":
        item["decision"] = "rejected"
    with pytest.raises(ValueError):
        human.validate_annotation(submit(batch, value), batch)


@pytest.mark.parametrize("failure", ["missing_tags", "missing_correction", "duplicate_tag"])
def test_problem_labels_require_actionable_unique_tags(fixture, failure):
    batch, value, _ = fixture
    value["items"][0]["decision"] = "rejected"
    segment = value["items"][0]["segments"][0]
    segment.update(verdict="unsupported", error_tags=["scope_overclaim"], correction="Limit scope")
    if failure == "missing_tags":
        segment["error_tags"] = []
    elif failure == "missing_correction":
        segment["correction"] = "  "
    else:
        segment["error_tags"] *= 2
    with pytest.raises(ValueError):
        human.validate_annotation(submit(batch, value), batch)


def test_rejected_report_tags_are_counted_without_inventing_accuracy(fixture):
    batch, value, _ = fixture
    value["items"][0]["decision"] = "rejected"
    value["items"][0]["segments"][0].update(
        verdict="unsupported",
        error_tags=["scope_overclaim"],
        correction="Cannot infer full-corpus absence",
    )
    result = human.summarize(batch, final(batch, value))
    assert result["acceptance_denominator"] == 1 and result["acceptance_numerator"] == 0
    assert result["segment_error_tag_counts"] == {"scope_overclaim": 1}


def test_uncertain_reference_is_excluded_from_denominator(fixture):
    batch, value, _ = fixture
    value["items"][0].update(reference_labels="uncertain", decision="uncertain")
    result = human.summarize(batch, final(batch, value))
    assert result["decision_counts"] == {"uncertain": 1}
    assert result["acceptance_rate"] is None


@pytest.mark.parametrize("failure", ["prior_changed", "no_prior", "cycle", "duplicate_prior"])
def test_adjudication_revalidates_prior_inputs_and_rejects_chains(fixture, failure):
    batch, value, _ = fixture
    path = final(batch, value)
    data = json.loads(path.read_text())
    if failure == "prior_changed":
        (batch.parent / "filled.json").write_text("{}")
    elif failure == "no_prior":
        data["prior_annotations"] = []
    elif failure == "cycle":
        data["prior_annotations"] = [
            {"path": path.relative_to(human.ROOT).as_posix(), "sha256": file_sha256(path)}
        ]
    else:
        data["prior_annotations"] *= 2
    write(path, data)
    with pytest.raises(ValueError):
        human.summarize(batch, path)


@pytest.mark.parametrize(
    "failure", ["packet", "input", "report", "evidence", "batch_duplicate", "outside"]
)
def test_saved_inputs_are_bound_and_paths_are_restricted(fixture, failure):
    batch, _, packet = fixture
    if failure == "packet":
        packet.write_text("{}")
    elif failure == "input":
        (packet.parent / "review_input.json").write_text("{}")
    elif failure in {"report", "evidence"}:
        name = "report.md" if failure == "report" else "evidence.json"
        (human.ROOT / "evals/results/original/case" / name).write_text("changed")
    elif failure == "batch_duplicate":
        data = json.loads(batch.read_text())
        data["items"].append(deepcopy(data["items"][0]))
        write(batch, data)
    else:
        with pytest.raises(ValueError):
            human.private_path("outside.json")
        return
    with pytest.raises(ValueError):
        human.summarize(batch)


def revise_packet(packet, payload):
    write(packet.parent / "review_input.json", payload)
    meta = json.loads(packet.read_text())
    meta["review_input_sha256"] = file_sha256(packet.parent / "review_input.json")
    meta["review_scope"] = payload["review_scope"]
    write(packet, meta)
    return human.initialize([packet])


def test_rehashed_invented_segment_is_still_rejected_by_original_reconstruction(fixture):
    _, _, packet = fixture
    payload = json.loads((packet.parent / "review_input.json").read_text())
    payload["segments"][0]["text"] = "invented body"
    with pytest.raises(ValueError, match="differs from its original"):
        revise_packet(packet, payload)


def test_selected_scope_never_counts_as_accepted_whole_report(fixture):
    _, value, packet = fixture
    payload = json.loads((packet.parent / "review_input.json").read_text())
    batch = revise_packet(packet, support.select_segments(payload, ["segment_001"]))
    value["batch_sha256"] = file_sha256(batch)
    item = value["items"][0]
    item.update(keypoints=[], abstention="not_evaluated")
    with pytest.raises(ValueError, match="whole-report review"):
        human.validate_annotation(submit(batch, value), batch)
    item["decision"] = "uncertain"
    result = human.summarize(batch, final(batch, value))
    assert result["acceptance_denominator"] == 0
    assert result["adjudicated_report_scopes"] == 1


def test_negative_requires_explicit_quoted_abstention_judgment(fixture):
    _, value, packet = fixture
    _, cases = support.load_cases(support.DEFAULT_DATASET)
    cases[0]["answerable"] = False
    payload = json.loads((packet.parent / "review_input.json").read_text())
    payload["answerable_draft_label"] = False
    batch = revise_packet(packet, payload)
    value["batch_sha256"] = file_sha256(batch)
    with pytest.raises(ValueError, match="No-answer case"):
        human.validate_annotation(submit(batch, value), batch)
    value["items"][0].update(
        abstention="inappropriate", abstention_report_quote="Fact", decision="rejected"
    )
    result = human.summarize(batch, final(batch, value))
    assert result["decision_counts"] == {"rejected": 1}


def test_disagreement_requires_explicit_final_and_is_reported(fixture):
    batch, first, _ = fixture
    first_path = submit(batch, first)
    second = deepcopy(first)
    second["reviewer"] = "second-synthetic-reviewer"
    second["items"][0]["decision"] = "rejected"
    second["items"][0]["segments"][0].update(
        verdict="unsupported", error_tags=["scope_overclaim"], correction="Limit scope"
    )
    second_path = write(batch.parent / "second.json", second)
    adjudicated = deepcopy(first)
    adjudicated.update(
        stage="adjudication",
        prior_annotations=[
            {"path": p.relative_to(human.ROOT).as_posix(), "sha256": file_sha256(p)}
            for p in [first_path, second_path]
        ],
    )
    adjudicated["items"][0]["decision_reason"] = (
        "Personally resolved the disagreement against the source"
    )
    path = write(batch.parent / "adjudicated.json", adjudicated)
    result = human.summarize(batch, path)
    assert result["prior_final_decision_disagreement_items"] == 1
    assert result["prior_annotation_count"] == 2
    assert result["same_reviewer_prior_count"] == 1


def test_cli_rejects_pending_template_with_machine_readable_error(fixture, monkeypatch, capsys):
    batch, _, _ = fixture
    monkeypatch.setattr(
        "sys.argv",
        [
            "adjudication",
            "validate",
            "--batch",
            str(batch),
            "--annotation",
            str(batch.parent / "annotation.template.json"),
        ],
    )
    assert human.main() == 1
    error = json.loads(capsys.readouterr().out)
    assert error["status"] == "invalid_annotation"
    assert all("input" not in row for row in error["errors"])
