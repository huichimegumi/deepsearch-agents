import json
from types import SimpleNamespace

import pytest

from app.research.bounded import Plan, StructuredResponseError, _structured, execute
from app.research.report import ResearchReport
from app.research.sources import SourceCatalog
from app.research.trace import ResearchTrace


@pytest.mark.asyncio
async def test_rejected_model_candidate_is_written_before_schema_validation(tmp_path):
    class Invalid:
        def with_structured_output(self, *args, **kwargs):
            return self

        def bind(self, **kwargs):
            return self

        async def ainvoke(self, messages):
            return {
                "parsed": None,
                "parsing_error": "invalid",
                "raw": SimpleNamespace(
                    content="raw candidate",
                    tool_calls=[{"args": {"bad": True}}],
                    response_metadata={},
                ),
            }

    with ResearchTrace(tmp_path).activate(), pytest.raises(StructuredResponseError):
        await _structured(Plan, "plan", {"question": "test"}, model=Invalid())
    saved = json.loads((tmp_path / "trace/model-001-response.json").read_text())
    assert saved["tool_calls"][0]["args"]["bad"] is True
    assert saved["content"] == "raw candidate"


@pytest.mark.asyncio
async def test_full_tool_response_survives_context_drop(tmp_path):
    class Catalog(SourceCatalog):
        def describe(self):
            return {"allowed_sources": ["sql"]}

        def collect(self, *args):
            return [
                {
                    "evidence_id": "ev1_big",
                    "source": "sql",
                    "locator": "fixture:big",
                    "content": {"text": "x" * 60000},
                }
            ], []

    class Model:
        def with_structured_output(self, schema, **kwargs):
            self.schema = schema
            return self

        def bind(self, **kwargs):
            return self

        async def ainvoke(self, messages):
            parsed = (
                Plan(steps=[{"source": "sql", "query": "SELECT text"}])
                if self.schema is Plan
                else ResearchReport(
                    title="Missing",
                    answerability="insufficient_evidence",
                    limitations=["No delivered evidence"],
                    claims=[],
                    facts=[],
                )
            )
            return {"parsed": parsed, "raw": SimpleNamespace(response_metadata={})}

    result = await execute(
        "Find text", Catalog(allowed_sources=("sql",)), tmp_path, workflow="simple", model=Model()
    )
    assert len(result["evidence"]) == 1
    context = json.loads((tmp_path / "evidence/context-001.json").read_text())
    assert context["estimated_tokens"] <= context["token_limit"]
    assert context["evidence"][0]["content"]["text"] == "x" * 60000
    stored = json.loads((tmp_path / "trace/tool-s0.json").read_text())
    assert len(stored["records"][0]["content"]["text"]) == 60000
    assert stored["records"][0]["evidence_id"] == "ev1_big"
