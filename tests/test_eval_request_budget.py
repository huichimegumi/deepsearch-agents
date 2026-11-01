"""Model reservations are durable and occur before provider transport."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from langchain_core.messages import HumanMessage

from app.agent.llm import EvaluationBudgetedChatOpenAI, get_model
from app.config import get_settings
from evals.request_budget import EvaluationBudgetExceeded, admit_request, usage


def test_budget_blocks_third_request_without_persisting_prompt(tmp_path: Path) -> None:
    ledger = tmp_path / "model_requests.jsonl"
    payload = {
        "model": "test",
        "messages": [{"role": "user", "content": "private task"}],
        "max_tokens": 5,
    }
    with patch.dict(
        os.environ,
        {
            "EVAL_LEDGER_PATH": str(ledger),
            "EVAL_MAX_REQUESTS": "2",
            "EVAL_MAX_RESERVED_TOKENS": "10000",
        },
    ):
        admit_request(payload)
        admit_request(payload)
        with pytest.raises(EvaluationBudgetExceeded, match="request_limit"):
            admit_request(payload)
    assert usage(ledger)["requests"] == 2
    assert "private task" not in ledger.read_text()
    assert [json.loads(line)["event"] for line in ledger.read_text().splitlines()] == [
        "admitted",
        "admitted",
        "blocked",
    ]


def test_token_reservation_blocks_before_first_request(tmp_path: Path) -> None:
    ledger = tmp_path / "model_requests.jsonl"
    with patch.dict(
        os.environ,
        {
            "EVAL_LEDGER_PATH": str(ledger),
            "EVAL_MAX_REQUESTS": "2",
            "EVAL_MAX_RESERVED_TOKENS": "1",
        },
    ):
        with pytest.raises(EvaluationBudgetExceeded, match="token_reservation_limit"):
            admit_request({"model": "test", "messages": [{"role": "user", "content": "hello"}]})
    assert usage(ledger) == {"requests": 0, "reserved_tokens": 0}


def test_incomplete_ledger_tail_does_not_create_phantom_spend(tmp_path: Path) -> None:
    ledger = tmp_path / "model_requests.jsonl"
    ledger.write_text('{"event":"admitted","reserved_tokens":10}\n{"event":"admitted"')
    assert usage(ledger) == {"requests": 1, "reserved_tokens": 10}


def test_qwen_model_uses_pre_dispatch_budget_boundary(tmp_path: Path) -> None:
    ledger = tmp_path / "model_requests.jsonl"
    with patch.dict(
        os.environ,
        {
            "LLM_PROVIDER": "dashscope",
            "LLM_NAME": "qwen-flash",
            "DASHSCOPE_API_KEY": "test-key",
            "EVAL_LEDGER_PATH": str(ledger),
            "EVAL_MAX_REQUESTS": "1",
            "EVAL_MAX_RESERVED_TOKENS": "10000",
            "EVAL_DEFAULT_MAX_OUTPUT_TOKENS": "100",
        },
        clear=True,
    ):
        get_settings.cache_clear()
        get_model.cache_clear()
        model = get_model()
        assert isinstance(model, EvaluationBudgetedChatOpenAI)
        model._get_request_payload([HumanMessage(content="hello")])
        with pytest.raises(EvaluationBudgetExceeded, match="request_limit"):
            model._get_request_payload([HumanMessage(content="again")])
    get_model.cache_clear()
    get_settings.cache_clear()
    assert usage(ledger)["requests"] == 1
