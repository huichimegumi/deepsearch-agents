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
            "AGENT_HARD_MAX_RECURSION_LIMIT": "100",
            "AGENT_HARD_MAX_RUNTIME_SECONDS": "1000",
            "AGENT_PHASE_CLARIFY_RECURSION_LIMIT": "13",
            "AGENT_PHASE_CLARIFY_TIMEOUT_SECONDS": "55",
            "AGENT_PHASE_RESEARCH_RECURSION_LIMIT": "70",
            "AGENT_PHASE_RESEARCH_TIMEOUT_SECONDS": "600",
            "AGENT_PHASE_COMPRESSION_RECURSION_LIMIT": "31",
            "AGENT_PHASE_COMPRESSION_TIMEOUT_SECONDS": "155",
            "AGENT_PHASE_FINAL_REPORT_RECURSION_LIMIT": "45",
            "AGENT_PHASE_FINAL_REPORT_TIMEOUT_SECONDS": "255",
            "TOOL_TIMEOUT_SECONDS": "9.5",
            "DB_TIMEOUT_SECONDS": "7",
            "DB_TABLE_PREVIEW_ROWS": "11",
            "DB_QUERY_PREVIEW_ROWS": "22",
            "DB_MAX_RESULT_CHARS": "3333",
            "RAG_ANSWER_MAX_HITS": "4",
            "RAG_ANSWER_MAX_CONTEXT_CHARS": "5555",
        }
        with patch.dict(os.environ, environment, clear=True):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertEqual(settings.agent_recursion_limit, 12)
        self.assertEqual(settings.agent_max_runtime_seconds, 45.5)
        self.assertEqual(settings.agent_hard_max_recursion_limit, 100)
        self.assertEqual(settings.agent_hard_max_runtime_seconds, 1000)
        self.assertEqual(settings.agent_phase_clarify_recursion_limit, 13)
        self.assertEqual(settings.agent_phase_clarify_timeout_seconds, 55)
        self.assertEqual(settings.agent_phase_research_recursion_limit, 70)
        self.assertEqual(settings.agent_phase_research_timeout_seconds, 600)
        self.assertEqual(settings.agent_phase_compression_recursion_limit, 31)
        self.assertEqual(settings.agent_phase_compression_timeout_seconds, 155)
        self.assertEqual(settings.agent_phase_final_report_recursion_limit, 45)
        self.assertEqual(settings.agent_phase_final_report_timeout_seconds, 255)
        self.assertEqual(settings.tool_timeout_seconds, 9.5)
        self.assertEqual(settings.db_timeout_seconds, 7)
        self.assertEqual(settings.db_table_preview_rows, 11)
        self.assertEqual(settings.db_query_preview_rows, 22)
        self.assertEqual(settings.db_max_result_chars, 3333)
        self.assertEqual(settings.rag_answer_max_hits, 4)
        self.assertEqual(settings.rag_answer_max_context_chars, 5555)

    def test_phase_budget_applies_profile_multiplier_and_hard_caps(self):
        settings = AppSettings(
            llm_name="qwen-max",
            openai_api_key="test-key",
            openai_base_url=None,
            cors_origins=(),
            agent_hard_max_recursion_limit=120,
            agent_hard_max_runtime_seconds=1000,
            agent_phase_research_recursion_limit=90,
            agent_phase_research_timeout_seconds=900,
        )

        budget = settings.agent_phase_budget("supervisor_research", "deep_report")

        self.assertEqual(budget.recursion_limit, 120)
        self.assertEqual(budget.timeout_seconds, 1000)

    def test_phase_budget_keeps_legacy_fallback_for_unknown_phase(self):
        settings = AppSettings(
            llm_name="qwen-max",
            openai_api_key="test-key",
            openai_base_url=None,
            cors_origins=(),
            agent_recursion_limit=12,
            agent_max_runtime_seconds=45.5,
        )

        budget = settings.agent_phase_budget("custom_phase")

        self.assertEqual(budget.recursion_limit, 12)
        self.assertEqual(budget.timeout_seconds, 45.5)

    def test_run_budget_profiles_define_interactive_slos(self):
        settings = AppSettings(
            llm_name="qwen-max",
            openai_api_key="test-key",
            openai_base_url=None,
            cors_origins=(),
        )

        self.assertEqual(settings.research_budget_limits("quick").total_seconds, 60)
        self.assertEqual(settings.research_budget_limits("standard").total_seconds, 180)
        deep = settings.research_budget_limits("deep_report")
        self.assertEqual(deep.total_seconds, 300)
        self.assertEqual(deep.max_search_queries, 12)
        self.assertEqual(deep.max_llm_calls, 12)
        self.assertEqual(deep.writer_reserved_seconds, 75)

    def test_run_budget_respects_hard_runtime_cap(self):
        settings = AppSettings(
            llm_name="qwen-max",
            openai_api_key="test-key",
            openai_base_url=None,
            cors_origins=(),
            agent_hard_max_runtime_seconds=120,
        )

        limits = settings.research_budget_limits("deep_report")

        self.assertEqual(limits.total_seconds, 120)
        self.assertEqual(limits.writer_reserved_seconds, 30)
