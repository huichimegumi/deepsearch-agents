import asyncio
import json
from types import SimpleNamespace

import pytest

from evals.reports_acceptance import writer_fidelity as wf
from evals.runners.experiment import file_sha256

TEXT = "This experimental feature is available in the installers as well."
ID = "ev1_web_" + "a" * 24


def record(url="https://docs.python.org/release"):
    return {
        "evidence_id": ID,
        "source": "web",
        "locator": url,
        "content": TEXT,
        "metadata": {"content_kind": "fetched_page_text"},
    }


def extracts():
    return wf.prepare_extracts([{"evidence_id": ID, "quote": TEXT}], [record()], ("python.org",))[
        "extracts"
    ]


@pytest.mark.parametrize(
    "url,allowed",
    [
        ("https://python.org/page", True),
        ("https://docs.python.org/page", True),
        ("https://python.org.evil.test/page", False),
        ("https://evilpython.org/page", False),
        ("https://python.org@evil.test/page", False),
        ("file://python.org/page", False),
    ],
)
def test_official_host_policy_uses_actual_hostname_and_scheme(url, allowed):
    assert wf.official_url(url, ("python.org",)) is allowed


def test_non_official_extract_is_excluded_and_invented_saved_quote_fails():
    quote = {"evidence_id": ID, "quote": TEXT}
    result = wf.prepare_extracts([quote], [record("https://thirdparty.test")], ("python.org",))
    assert not result["extracts"]
    assert result["excluded"][0]["reason"] == "non_official_host"
    with pytest.raises(ValueError, match="revalidation"):
        wf.prepare_extracts([{**quote, "quote": TEXT.upper()}], [record()], ("python.org",))


def test_structural_audit_rejects_unknown_links_but_cannot_detect_scope_errors():
    source = extracts()
    known = source[0]["quote_id"]
    result = wf.audit_assertions(
        wf.StructuredWriter(
            assertions=[
                wf.Assertion(text="Only these installers support the feature.", quote_ids=[known]),
                wf.Assertion(text="A claim", quote_ids=["invented"]),
                wf.Assertion(text="Other [ev1_web_unknown]", quote_ids=[known]),
            ]
        ),
        source,
    )
    assert len(result["accepted"]) == 1
    assert result["accepted"][0]["semantic_support"] == "pending_review"
    assert len(result["rejected"]) == 2
    baseline = wf.render_extract_baseline(source)
    assert TEXT in baseline
    assert "Only these" not in baseline


@pytest.fixture
def frozen_inputs(tmp_path, monkeypatch):
    source = tmp_path / "prior"
    source.mkdir()
    dataset = tmp_path / "dataset.json"
    cases = [
        {
            "id": case_id,
            "question": "Question " + case_id,
            "answer_keypoints": ["SECRET_ANSWER_KEY"],
        }
        for case_id in wf.OFFICIAL_DOMAINS
    ]
    dataset.write_text(json.dumps({"cases": cases}), encoding="utf-8")
    rows = []
    for case in cases:
        folder = source / case["id"]
        folder.mkdir()
        domain = wf.OFFICIAL_DOMAINS[case["id"]][0]
        (folder / "inputs.json").write_text(
            json.dumps(
                {"question": case["question"], "records": [record(f"https://{domain}/release")]}
            ),
            encoding="utf-8",
        )
        (folder / "quotes.json").write_text(
            json.dumps({"accepted": [{"evidence_id": ID, "quote": TEXT}]}), encoding="utf-8"
        )
        rows.append(
            {
                "id": case["id"],
                "artifact_sha256": {
                    name: file_sha256(folder / name) for name in ("inputs.json", "quotes.json")
                },
            }
        )
    (source / "results.json").write_text(
        json.dumps(
            {
                "inputs_unchanged": True,
                "source_unchanged": True,
                "manifest": {"dataset_sha256": file_sha256(dataset)},
                "cases": rows,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(wf, "DATASET", dataset)
    monkeypatch.setattr(wf, "safe_path", lambda p: tmp_path / p)
    monkeypatch.setattr(wf, "build_manifest", lambda *_: {"source_sha256": "fixed"})
    return source


def test_hash_mismatch_fails_before_calling_model(frozen_inputs, monkeypatch):
    case = frozen_inputs / "report_web_002" / "inputs.json"
    case.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        wf, "experiment_model", lambda: pytest.fail("model called before preflight")
    )
    with pytest.raises(ValueError, match="hash_mismatch"):
        asyncio.run(wf.run(frozen_inputs, execute=True))


def test_offline_mode_builds_both_baselines_without_model_or_answer_keys(
    frozen_inputs, monkeypatch
):
    monkeypatch.setattr(wf, "experiment_model", lambda: pytest.fail("offline model call"))
    output = asyncio.run(wf.run(frozen_inputs))
    result = json.loads((output / "results.json").read_text(encoding="utf-8"))
    assert len(result["cases"]) == 2
    assert sum(row["logical_calls"] for row in result["cases"]) == 0
    assert result["inputs_unchanged"] and result["source_unchanged"]
    for path in output.rglob("*.json"):
        assert "SECRET_ANSWER_KEY" not in path.read_text(encoding="utf-8")


def test_execute_calls_once_per_case_and_retains_parse_failure(frozen_inputs, monkeypatch):
    calls = []

    class FakeModel:
        def with_structured_output(self, schema, include_raw):
            assert schema is wf.StructuredWriter and include_raw
            return self

        async def ainvoke(self, messages):
            calls.append(messages)
            assert "SECRET_ANSWER_KEY" not in str(messages)
            if len(calls) == 1:
                return {
                    "parsed": None,
                    "raw": SimpleNamespace(content="invalid", usage_metadata={}),
                }
            payload = json.loads(messages[1][1])
            return {
                "parsed": wf.StructuredWriter(
                    assertions=[
                        wf.Assertion(
                            text="A test paraphrase", quote_ids=[payload["extracts"][0]["quote_id"]]
                        )
                    ]
                ),
                "raw": SimpleNamespace(content="structured", usage_metadata={}),
            }

    monkeypatch.setattr(wf, "experiment_model", FakeModel)
    output = asyncio.run(wf.run(frozen_inputs, execute=True))
    result = json.loads((output / "results.json").read_text(encoding="utf-8"))
    assert len(calls) == 2
    assert [row["status"] for row in result["cases"]] == [
        "parse_failed",
        "generated_pending_semantic_review",
    ]
    assert result["human_accuracy"] is None
