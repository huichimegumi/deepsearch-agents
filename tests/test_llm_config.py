"""Tests for shared LLM client configuration."""

import os
from unittest.mock import patch

from app.agent.llm import get_model
from app.config import get_settings


def teardown_function():
    get_model.cache_clear()
    get_settings.cache_clear()


def test_get_model_passes_llm_timeout_to_chat_client():
    environment = {
        "LLM_NAME": "qwen-max",
        "OPENAI_API_KEY": "test-key",
        "OPENAI_BASE_URL": "https://example.test/v1",
        "LLM_TIMEOUT_SECONDS": "42.5",
        "TOOL_TIMEOUT_SECONDS": "12.5",
    }
    with patch.dict(os.environ, environment, clear=True):
        get_model.cache_clear()
        get_settings.cache_clear()
        with patch("app.agent.llm.init_chat_model", return_value="model") as init_chat_model:
            assert get_model() == "model"

    init_chat_model.assert_called_once_with(
        model="qwen-max",
        model_provider="openai",
        api_key="test-key",
        base_url="https://example.test/v1",
        timeout=42.5,
    )
