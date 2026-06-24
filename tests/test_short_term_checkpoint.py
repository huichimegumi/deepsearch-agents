"""Tests for short-term checkpoint configuration helpers."""

import os
import unittest
from unittest.mock import patch

from app.memory.checkpoint import _checkpoint_conninfo, _normalize_backend
from app.rag.config import get_rag_settings


class ShortTermCheckpointTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_rag_settings.cache_clear()

    def test_checkpoint_conninfo_removes_sqlalchemy_driver(self):
        self.assertEqual(
            _checkpoint_conninfo("postgresql+psycopg://user:pass@localhost:5432/db"),
            "postgresql://user:pass@localhost:5432/db",
        )

    def test_backend_normalization_defaults_to_postgres(self):
        self.assertEqual(_normalize_backend(""), "postgres")
        self.assertEqual(_normalize_backend("auto"), "postgres")
        self.assertEqual(_normalize_backend("in-memory"), "memory")

    def test_short_term_settings_parse_environment(self):
        environment = {
            "SHORT_TERM_MEMORY_BACKEND": "memory",
            "SHORT_TERM_MEMORY_DATABASE_URL": "postgresql://example/db",
            "SHORT_TERM_MEMORY_POOL_SIZE": "3",
            "SHORT_TERM_MEMORY_FALLBACK_ENABLED": "false",
        }
        with patch.dict(os.environ, environment, clear=True):
            get_rag_settings.cache_clear()
            settings = get_rag_settings()

        self.assertEqual(settings.short_term_memory_backend, "memory")
        self.assertEqual(settings.short_term_memory_database_url, "postgresql://example/db")
        self.assertEqual(settings.short_term_memory_pool_size, 3)
        self.assertFalse(settings.short_term_memory_fallback_enabled)


if __name__ == "__main__":
    unittest.main()
