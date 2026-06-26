"""Tests for application environment configuration."""

import os
import unittest
from unittest.mock import patch

from app.config import AppSettings, get_settings


class AppSettingsTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_settings.cache_clear()

    def test_llm_validation_accepts_complete_configuration(self):
        settings = AppSettings(
            llm_name="qwen-max",
            openai_api_key="test-key",
            openai_base_url="https://example.test/v1",
            cors_origins=("http://localhost:5173",),
        )

        settings.validate_llm()

    def test_llm_validation_reports_missing_values(self):
        settings = AppSettings(
            llm_name="",
            openai_api_key="你的大模型_API_KEY",
            openai_base_url=None,
            cors_origins=(),
        )

        with self.assertRaisesRegex(RuntimeError, "LLM_NAME, OPENAI_API_KEY"):
            settings.validate_llm()

    def test_settings_parse_cors_origins(self):
        environment = {
            "LLM_NAME": "qwen-max",
            "OPENAI_API_KEY": "test-key",
            "CORS_ORIGINS": "https://one.example, https://two.example",
        }
        with patch.dict(os.environ, environment, clear=True):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertEqual(
            settings.cors_origins,
            ("https://one.example", "https://two.example"),
        )

    def test_settings_accept_dashscope_host_variable(self):
        environment = {
            "LLM_NAME": "qwen-max",
            "DASHSCOPE_API_KEY": "sk-dashscope-test",
        }
        with patch.dict(os.environ, environment, clear=True):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertEqual(settings.openai_api_key, "sk-dashscope-test")

    def test_settings_ignore_variable_name_placeholder(self):
        environment = {
            "LLM_NAME": "qwen-max",
            "OPENAI_API_KEY": "DASHSCOPE_API_KEY",
            "DASHSCOPE_API_KEY": "sk-dashscope-test",
        }
        with patch.dict(os.environ, environment, clear=True):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertEqual(settings.openai_api_key, "sk-dashscope-test")

    def test_settings_parse_reliability_limits(self):
        environment = {
            "LLM_NAME": "qwen-max",
            "OPENAI_API_KEY": "test-key",
            "AGENT_RECURSION_LIMIT": "12",
            "AGENT_MAX_RUNTIME_SECONDS": "45.5",
            "LLM_TIMEOUT_SECONDS": "30.5",
            "TOOL_TIMEOUT_SECONDS": "9.5",
            "DB_TIMEOUT_SECONDS": "7",
        }
        with patch.dict(os.environ, environment, clear=True):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertEqual(settings.agent_recursion_limit, 12)
        self.assertEqual(settings.agent_max_runtime_seconds, 45.5)
        self.assertEqual(settings.llm_timeout_seconds, 30.5)
        self.assertEqual(settings.tool_timeout_seconds, 9.5)
        self.assertEqual(settings.db_timeout_seconds, 7)
