"""Model adapter behavior for OpenAI-compatible providers."""

import os
from unittest.mock import patch

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.agent.llm import DeepSeekChatOpenAI, get_model
from app.config import get_settings


class SampleResult(BaseModel):
    answer: int


def test_deepseek_structured_output_uses_tool_calling():
    model = DeepSeekChatOpenAI(
        model="deepseek-flash",
        api_key="test-key",
        base_url="https://api.deepseek.com",
    )
    with patch.object(ChatOpenAI, "with_structured_output") as structured:
        model.with_structured_output(SampleResult, include_raw=True)

    structured.assert_called_once_with(
        SampleResult,
        include_raw=True,
        method="function_calling",
    )


def test_deepseek_model_disables_thinking_for_forced_tool_calls():
    with patch.dict(
        os.environ,
        {"LLM_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "test-key"},
        clear=True,
    ):
        get_settings.cache_clear()
        get_model.cache_clear()
        model = get_model()

    get_model.cache_clear()
    get_settings.cache_clear()
    assert isinstance(model, DeepSeekChatOpenAI)
    assert model.model_name == "deepseek-flash"
    assert model._default_params["extra_body"] == {"thinking": {"type": "disabled"}}


def test_evaluation_disables_opaque_sdk_retries():
    with patch.dict(
        os.environ,
        {
            "LLM_PROVIDER": "deepseek",
            "DEEPSEEK_API_KEY": "test-key",
            "EVAL_DISABLE_SDK_RETRIES": "1",
        },
        clear=True,
    ):
        get_settings.cache_clear()
        get_model.cache_clear()
        model = get_model()

    get_model.cache_clear()
    get_settings.cache_clear()
    assert model.max_retries == 0


def test_deepseek_translates_output_token_cap_to_provider_field():
    model = DeepSeekChatOpenAI(
        model="deepseek-flash",
        api_key="test-key",
        base_url="https://api.deepseek.com",
    )
    payload = model._get_request_payload([HumanMessage(content="hi")], max_tokens=3500)
    assert payload["max_tokens"] == 3500
    assert "max_completion_tokens" not in payload


def test_evaluation_temperature_is_explicit():
    with patch.dict(
        os.environ,
        {
            "LLM_PROVIDER": "deepseek",
            "DEEPSEEK_API_KEY": "test-key",
            "EVAL_TEMPERATURE": "0",
        },
        clear=True,
    ):
        get_settings.cache_clear()
        get_model.cache_clear()
        model = get_model()
    get_model.cache_clear()
    get_settings.cache_clear()
    assert model.temperature == 0
